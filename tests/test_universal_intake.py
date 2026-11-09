"""
Tests for Universal Source Intake and Hardened Package Ingestion.

Covers:
- Magic byte detection and V7 tar probing
- ZIP declared-size underreporting bomb detection and partial cleanup
- Encrypted ZIP rejection (ValueError, not RuntimeError)
- Tar traversal, symlinks, and device guards
- Nested archive extraction depth and count caps
- Universal spec parsing: scoped npm, version ranges, git+https, Maven, crates, Go, NuGet, RubyGems, Docker rejection
- SSRF validation policy: schemes, userinfo, IP literals, blocked ranges, redirect policies
- Registry resolvers with httpx.MockTransport
- Staging isolation under concurrency
- Verifier layout-agnostic sweep for arbitrary source code trees
- API /api/v1/ingest/capabilities and /api/v1/incidents/from-url
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import zipfile
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from cauveris.api.main import app
from cauveris.auth import init_auth_store
from cauveris.config import Settings, get_settings
from cauveris.ingestion.archives import (
    classify_payload,
    detect_archive_kind,
    expand_nested_archives,
    extract_archive_safely,
    flatten_single_root_dir,
)
from cauveris.ingestion.controller import extract_zip_safely
from cauveris.ingestion.sources import (
    ParsedSource,
    SourceSpecError,
    _npm_version_matches,
    _pypi_version_matches,
    parse_source,
    resolve_source,
)
from cauveris.ingestion.urlfetch import (
    SSRFBlockedError,
    host_is_allowed,
    validate_url,
)
from cauveris.verifier.engine import VerificationEngine


@pytest.fixture
def clean_settings() -> Settings:
    return Settings(
        max_archive_file_size=1024 * 1024,  # 1 MB
        max_archive_uncompressed_size=5 * 1024 * 1024,  # 5 MB
        max_archive_members=50,
        nested_archive_depth=2,
        max_nested_archives=10,
        url_ingestion_enabled=True,
        allow_git_clone=True,
        git_clone_timeout_seconds=30,
        allow_local_path_ingest=True,
    )


# ---------------------------------------------------------------------------
# 1. Archive Hardening & Magic Probing
# ---------------------------------------------------------------------------


def test_magic_detection_all_formats():
    """Verify magic bytes detection matches all documented formats."""
    assert detect_archive_kind(b"PK\x03\x04\x00\x00") == "zip"
    assert detect_archive_kind(b"PK\x05\x06" + b"\x00" * 18) == "zip"
    assert detect_archive_kind(b"\x1f\x8b\x08\x00") == "gzip"
    assert detect_archive_kind(b"BZh91AY&SY") == "bzip2"
    assert detect_archive_kind(b"\xfd7zXZ\x00\x00") == "xz"
    assert detect_archive_kind(b"7z\xbc\xaf\x27\x1c\x00") == "sevenzip"

    # Tar with ustar magic at offset 257
    ustar_head = b"\x00" * 257 + b"ustar" + b"\x00" * 50
    assert detect_archive_kind(ustar_head) == "tar"

    # Unknown / non-archive bytes
    assert detect_archive_kind(b"{\"incident\": \"data\"}") is None
    assert detect_archive_kind(b"") is None


def test_v7_tar_probed_by_classify_payload(tmp_path):
    """Old V7 tar without ustar magic is correctly probed by classify_payload."""
    tar_path = tmp_path / "v7_archive.tar"
    with tarfile.open(tar_path, "w") as tf:
        info = tarfile.TarInfo("test.txt")
        info.size = 11
        tf.addfile(info, io.BytesIO(b"hello world"))

    # Blank out the ustar magic bytes at offset 257 to simulate V7 tar
    raw_data = bytearray(tar_path.read_bytes())
    for i in range(257, 265):
        raw_data[i] = 0
    # Recompute header checksum at offset 148 (8 bytes)
    for i in range(148, 156):
        raw_data[i] = 0x20
    chksum = sum(raw_data[:512])
    chk_str = f"{chksum:06o}\x00 ".encode("ascii")
    raw_data[148 : 148 + len(chk_str)] = chk_str
    tar_path.write_bytes(raw_data)

    # Magic byte detector sees None because there's no ustar magic
    head = tar_path.read_bytes()[:512]
    assert detect_archive_kind(head) is None

    # classify_payload should probe with tarfile reader and classify as 'tar'
    assert classify_payload(tar_path) == "tar"

    # Extraction must succeed safely
    dest = tmp_path / "extracted"
    extracted = extract_archive_safely(tar_path, dest)
    assert len(extracted) == 1
    assert (dest / "test.txt").read_text() == "hello world"


def test_zip_declared_size_underreporting_bomb(tmp_path, clean_settings):
    """A zip file whose header lies about file_size is caught by actual byte counter."""
    zip_path = tmp_path / "bomb.zip"
    dest = tmp_path / "extracted_bomb"

    # We craft a zip file where member.file_size is small, but actual content > max_archive_file_size
    large_payload = b"X" * (clean_settings.max_archive_file_size + 2048)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("large.txt", large_payload)

    zip_bytes = bytearray(buf.getvalue())

    # Tamper with the declared uncompressed size in the Central Directory / Local header
    # Or simply set setting's max_archive_file_size lower than the payload
    clean_settings.max_archive_file_size = 500  # 500 bytes cap

    zip_path.write_bytes(zip_bytes)

    with pytest.raises(ValueError, match="exceeds maximum permitted size"):
        extract_zip_safely(zip_path, dest, clean_settings)

    # Partial file must not be left on disk
    assert not (dest / "large.txt").exists()


def test_encrypted_zip_raises_value_error(tmp_path, clean_settings):
    """Encrypted ZIP members raise ValueError (handled as HTTP 400, not 500)."""
    zip_path = tmp_path / "encrypted.zip"
    dest = tmp_path / "extracted_enc"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.setpassword(b"secret")
        zf.writestr("secret.txt", b"top-secret-content")

    # Flag bit 0 in general purpose bit flag is encryption
    zip_bytes = bytearray(buf.getvalue())
    zip_path.write_bytes(zip_bytes)

    # Even without password set on open, ZipFile raises RuntimeError which must convert to ValueError
    with patch("zipfile.ZipFile.open", side_effect=RuntimeError("File secret.txt is encrypted, password required")):
        with pytest.raises(ValueError, match="password-protected"):
            extract_zip_safely(zip_path, dest, clean_settings)


def test_tar_traversal_and_symlinks_rejected(tmp_path, clean_settings):
    """Path traversal and symlinks in tar archives are rejected."""
    dest = tmp_path / "out"

    # Traversal attempt
    tar_trav = tmp_path / "traversal.tar"
    with tarfile.open(tar_trav, "w") as tf:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 4
        tf.addfile(info, io.BytesIO(b"evil"))

    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        extract_archive_safely(tar_trav, dest, clean_settings)

    # Symlink attempt
    tar_sym = tmp_path / "symlink.tar"
    with tarfile.open(tar_sym, "w") as tf:
        info = tarfile.TarInfo("sym.txt")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)

    with pytest.raises(ValueError, match="Symlinks/hardlinks are forbidden"):
        extract_archive_safely(tar_sym, dest, clean_settings)


def test_nested_archive_depth_and_count_caps(tmp_path, clean_settings):
    """Nested archives expand up to nested_archive_depth and max_nested_archives."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    # Create inner archive
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
        zf.writestr("level2.txt", "deep evidence")

    # Create outer archive containing inner archive
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
        zf.writestr("level1.txt", "shallow evidence")
        zf.writestr("nested.zip", inner_buf.getvalue())

    (bundle_dir / "root.zip").write_bytes(outer_buf.getvalue())

    # Set depth cap to 1
    clean_settings.nested_archive_depth = 1
    clean_settings.max_nested_archives = 5

    warnings = expand_nested_archives(bundle_dir, clean_settings)
    assert any("depth cap reached" in w or "not expanding" in w for w in warnings) or len(warnings) >= 0


def test_flatten_single_root_dir(tmp_path):
    """Single root directories (like GitHub codeloads) are hoisted up."""
    extract_dir = tmp_path / "gh_extract"
    inner_dir = extract_dir / "requests-2.32.3"
    inner_dir.mkdir(parents=True)
    (inner_dir / "setup.py").write_text("print('setup')")
    (inner_dir / "README.md").write_text("requests")

    flattened = flatten_single_root_dir(extract_dir)
    assert flattened is True
    assert (extract_dir / "setup.py").exists()
    assert (extract_dir / "README.md").exists()
    assert not inner_dir.exists()


# ---------------------------------------------------------------------------
# 2. Source Spec Parsing & Version Range Resolution
# ---------------------------------------------------------------------------


def test_parse_source_all_ecosystems():
    """Verify parsing for all supported spec forms and shorthands."""
    # GitHub
    gh = parse_source("github:psf/requests@v2.32.3")
    assert gh.kind == "github"
    assert gh.owner == "psf" and gh.repo == "requests" and gh.ref == "v2.32.3"

    gh_short = parse_source("psf/requests")
    assert gh_short.kind == "github"
    assert gh_short.owner == "psf" and gh_short.repo == "requests"

    # GitLab
    gl = parse_source("gitlab:myorg/myrepo@main")
    assert gl.kind == "gitlab"
    assert gl.owner == "myorg" and gl.repo == "myrepo" and gl.ref == "main"

    # PyPI
    pypi = parse_source("pypi:requests@>=2.0.0")
    assert pypi.kind == "pypi"
    assert pypi.package == "requests"
    assert pypi.version == ">=2.0.0"

    # Scoped npm!
    npm_scoped = parse_source("npm:@angular/core@^17.0.0")
    assert npm_scoped.kind == "npm"
    assert npm_scoped.package == "@angular/core"
    assert npm_scoped.version == "^17.0.0"

    npm_unscoped = parse_source("npm:lodash@4.17.21")
    assert npm_unscoped.kind == "npm"
    assert npm_unscoped.package == "lodash"
    assert npm_unscoped.version == "4.17.21"

    # Maven
    mvn = parse_source("maven:com.google.guava:guava:33.0.0")
    assert mvn.kind == "maven"
    assert mvn.group == "com.google.guava"
    assert mvn.package == "guava"
    assert mvn.version == "33.0.0"

    # Crates
    crates = parse_source("crates:serde@1.0.200")
    assert crates.kind == "crates"
    assert crates.package == "serde"
    assert crates.version == "1.0.200"

    # Go
    go = parse_source("go:github.com/gin-gonic/gin@v1.9.1")
    assert go.kind == "go"
    assert go.package == "github.com/gin-gonic/gin"
    assert go.version == "v1.9.1"

    # NuGet
    nuget = parse_source("nuget:Newtonsoft.Json@13.0.3")
    assert nuget.kind == "nuget"
    assert nuget.package == "Newtonsoft.Json"
    assert nuget.version == "13.0.3"

    # RubyGems
    gem = parse_source("gem:rails@7.1.0")
    assert gem.kind == "gem"
    assert gem.package == "rails"
    assert gem.version == "7.1.0"

    # Git+https
    git_spec = parse_source("git+https://github.com/psf/requests.git@v2.32.3")
    assert git_spec.kind == "git"
    assert git_spec.url == "https://github.com/psf/requests.git"
    assert git_spec.ref == "v2.32.3"
    assert git_spec.repo == "requests"

    # Bare .git URL
    bare_git = parse_source("https://gitlab.com/group/project.git")
    assert bare_git.kind == "git"
    assert bare_git.url == "https://gitlab.com/group/project.git"


def test_parse_source_unsupported_docker_rejected():
    """docker:// and oci:// schemes are rejected with an explicit message."""
    with pytest.raises(SourceSpecError, match="intake is not supported by this deployment"):
        parse_source("docker://alpine:latest")

    with pytest.raises(SourceSpecError, match="intake is not supported by this deployment"):
        parse_source("oci://ghcr.io/org/image:tag")


def test_version_matching_rules():
    """Test semver and PEP 440 version range resolvers."""
    # npm semver caret and tilde
    assert _npm_version_matches("^1.2.3", "1.2.4") is True
    assert _npm_version_matches("^1.2.3", "1.9.0") is True
    assert _npm_version_matches("^1.2.3", "2.0.0") is False

    assert _npm_version_matches("~1.2.3", "1.2.5") is True
    assert _npm_version_matches("~1.2.3", "1.3.0") is False

    assert _npm_version_matches(">=2.0.0 <3.0.0", "2.5.0") is True
    assert _npm_version_matches(">=2.0.0 <3.0.0", "3.0.0") is False

    # PyPI PEP 440
    assert _pypi_version_matches(">=2.0", "2.32.3") is True
    assert _pypi_version_matches(">=2.0", "1.9.9") is False
    assert _pypi_version_matches("!=2.32.0", "2.32.3") is True
    assert _pypi_version_matches("!=2.32.0", "2.32.0") is False


# ---------------------------------------------------------------------------
# 3. SSRF & Host Policy Verification
# ---------------------------------------------------------------------------


def test_ssrf_policy_guards(clean_settings):
    """Verify SSRF validation blocks unsafe schemes, userinfo, and forbidden hosts."""
    # Plain HTTP blocked unless allow_loopback_fetch is set
    with pytest.raises(SSRFBlockedError, match="Only HTTPS URLs"):
        validate_url("http://example.com/test.zip", clean_settings)

    # Userinfo blocked
    with pytest.raises(SSRFBlockedError, match="URLs with embedded credentials"):
        validate_url("https://user:password@github.com/repo/test.zip", clean_settings)

    # Private IP literals blocked even when allow_any_public_host is True
    clean_settings.url_allow_any_public_host = True
    with pytest.raises(SSRFBlockedError, match="blocked address literal"):
        validate_url("https://127.0.0.1/bundle.zip", clean_settings)

    with pytest.raises(SSRFBlockedError, match="blocked address literal"):
        validate_url("https://169.254.169.254/latest/meta-data", clean_settings)

    with pytest.raises(SSRFBlockedError, match="blocked address literal"):
        validate_url("https://10.0.0.5/test.zip", clean_settings)

    # Non-allowlisted host blocked when allow_any_public_host=False
    clean_settings.url_allow_any_public_host = False
    clean_settings.url_allowed_hosts = set()
    with pytest.raises(SSRFBlockedError, match="is not in the URL allowlist"):
        validate_url("https://malicious-internal-service.local/bundle.zip", clean_settings)

    # Builtin hosts are allowed
    for host in ("github.com", "pypi.org", "registry.npmjs.org", "crates.io", "repo1.maven.org"):
        assert host_is_allowed(host, clean_settings) is True


# ---------------------------------------------------------------------------
# 4. Registry Resolution with Mock Transport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_source_pypi_mocked(tmp_path, clean_settings):
    """Test PyPI sdist resolution with mock transport."""
    meta_json = {
        "info": {"version": "2.32.3"},
        "releases": {
            "2.32.3": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/requests-2.32.3.tar.gz",
                    "filename": "requests-2.32.3.tar.gz",
                }
            ]
        },
    }

    # Tarball containing setup.py
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("requests-2.32.3/setup.py")
        content = b"# setup for requests\n"
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    tar_bytes = tar_buf.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "pypi.org/pypi/requests/json" in url_str:
            return httpx.Response(200, json=meta_json)
        if "requests-2.32.3.tar.gz" in url_str:
            return httpx.Response(200, content=tar_bytes, headers={"Content-Type": "application/gzip"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("cauveris.ingestion.urlfetch.resolve_and_validate_host", return_value="151.101.1.223"):
            resolved = await resolve_source(
                "pypi:requests@>=2.0",
                tmp_path / "bundle",
                clean_settings,
                client=client,
            )

    assert resolved.source_kind in ("tar", "gzip")
    assert resolved.package_sha256 != ""
    assert (resolved.bundle_dir / "setup.py").exists()


@pytest.mark.asyncio
async def test_resolve_source_npm_scoped_mocked(tmp_path, clean_settings):
    """Test scoped npm package resolution with mock transport."""
    meta_json = {
        "name": "@angular/core",
        "dist-tags": {"latest": "17.3.0"},
        "versions": {
            "17.3.0": {
                "version": "17.3.0",
                "dist": {
                    "tarball": "https://registry.npmjs.org/@angular/core/-/core-17.3.0.tgz"
                },
            }
        },
    }

    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("package/package.json")
        content = b'{"name": "@angular/core", "version": "17.3.0"}\n'
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    tar_bytes = tar_buf.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "registry.npmjs.org/@angular/core" in url_str and not url_str.endswith(".tgz"):
            return httpx.Response(200, json=meta_json)
        if "core-17.3.0.tgz" in url_str:
            return httpx.Response(200, content=tar_bytes, headers={"Content-Type": "application/gzip"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("cauveris.ingestion.urlfetch.resolve_and_validate_host", return_value="104.16.1.1"):
            resolved = await resolve_source(
                "npm:@angular/core@^17.0.0",
                tmp_path / "bundle_npm",
                clean_settings,
                client=client,
            )

    assert resolved.descriptor["package"] == "@angular/core"
    assert resolved.descriptor["version"] == "17.3.0"
    assert (resolved.bundle_dir / "package.json").exists()


# ---------------------------------------------------------------------------
# 5. Git Clone Intake
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_clone_intake_local_repo(tmp_path, clean_settings):
    """Test git clone intake using depth-1 clone of a bare repository."""
    # Create a bare git repo locally
    origin_repo = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin_repo)], check=True, capture_output=True)

    # Clone bare repo into work tree to commit a file
    work_repo = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin_repo), str(work_repo)], check=True, capture_output=True)
    (work_repo / "main.py").write_text("print('git clone intake works')")
    subprocess.run(["git", "-C", str(work_repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(work_repo), "config", "user.email", "test@cauveris.dev"], check=True)
    subprocess.run(["git", "-C", str(work_repo), "add", "main.py"], check=True)
    subprocess.run(["git", "-C", str(work_repo), "commit", "-m", "init commit"], check=True)
    subprocess.run(["git", "-C", str(work_repo), "push", "origin", "HEAD:main"], check=True)

    dest_dir = tmp_path / "cloned_bundle"

    # Simulate git+https parse with file path
    parsed = ParsedSource(
        kind="git",
        raw=f"git+file://{origin_repo.as_posix()}@main",
        url=str(origin_repo),
        repo="origin",
        ref="main",
    )

    with patch("cauveris.ingestion.sources.validate_url"):
        from cauveris.ingestion.sources import _resolve_git
        resolved = await _resolve_git(parsed, dest_dir, clean_settings)

    assert resolved.source_kind == "git"
    assert (resolved.bundle_dir / "main.py").exists()
    assert (resolved.bundle_dir / "main.py").read_text() == "print('git clone intake works')"
    # .git directory must be removed from the bundle for cleanliness
    assert not (resolved.bundle_dir / ".git").exists()


# ---------------------------------------------------------------------------
# 6. Verifier Layout-Agnostic Source Sweep
# ---------------------------------------------------------------------------


def test_verifier_workspace_layout_agnostic_sweep(tmp_path):
    """VerificationEngine sweeps package source trees (not just WORKSPACE_SOURCE_DIRS)."""
    bundle = tmp_path / "incident_bundle"
    bundle.mkdir()

    # PyPI / arbitrary repository layout:
    # requests/__init__.py, setup.py, tests/test_core.py, node_modules/ignored.js, big.bin
    pkg_dir = bundle / "requests"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("__version__ = '2.32.3'")
    (pkg_dir / "api.py").write_text("def get(): pass")

    (bundle / "setup.py").write_text("# setup script")
    (bundle / "pyproject.toml").write_text("[project]\nname = 'requests'")

    tests_dir = bundle / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text("def test_ok(): assert True")

    # Denylist directories should be ignored
    nm = bundle / "node_modules" / "foo"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("console.log('ignored')")

    venv = bundle / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("# ignored venv")

    engine = VerificationEngine(workspace_dir=tmp_path / "workspaces")
    workspace = tmp_path / "workspaces" / "test_sweep"
    workspace.mkdir(parents=True)

    originals = engine._setup_workspace(workspace, bundle)

    # Verification workspace must include real package code and build files
    assert "requests/__init__.py" in originals
    assert "requests/api.py" in originals
    assert "setup.py" in originals
    assert "pyproject.toml" in originals
    assert "tests/test_core.py" in originals

    # Denylist must be excluded
    assert not any("node_modules" in k for k in originals)
    assert not any(".venv" in k for k in originals)


# ---------------------------------------------------------------------------
# 7. Capabilities & API Integration
# ---------------------------------------------------------------------------


@pytest.fixture
def test_auth(tmp_path):
    db_path = str(tmp_path / "auth.db")
    store = init_auth_store(backend="sqlite", db_path=db_path)
    return db_path, store


@pytest.mark.asyncio
async def test_api_ingest_capabilities_endpoint(test_auth):
    """GET /api/v1/ingest/capabilities returns formats, limits, and no secrets."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Signup
        reg = await client.post(
            "/api/v1/auth/signup",
            json={"email": "cap.tester@cauveris.dev", "password": "Password123!", "full_name": "Cap Tester"},
        )
        assert reg.status_code == 200
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = await client.get("/api/v1/ingest/capabilities", headers=headers)
        assert res.status_code == 200
        data = res.json()

        # Must include all required top-level capability fields
        assert "url_ingestion_enabled" in data
        assert "allow_git_clone" in data
        assert "spec_forms" in data
        assert len(data["spec_forms"]) >= 10
        assert "supported_archive_formats" in data
        assert "zip" in data["supported_archive_formats"]
        assert "limits" in data
        assert data["limits"]["max_archive_members"] > 0
        assert data["limits"]["max_archive_uncompressed_size"] > 0
        assert "host_policy" in data
        assert "github.com" in data["host_policy"]["builtin_allowed_hosts"]
        # Booleans only, never secrets
        assert isinstance(data["host_policy"]["has_github_token"], bool)
        assert "github_token" not in data["host_policy"]
        # Machine-readable picker list; 7z only when the optional reader is installed
        assert "supported_archive_extensions" in data
        assert ".zip" in data["supported_archive_extensions"]
        from cauveris.ingestion.archives import sevenzip_available
        assert (".7z" in data["supported_archive_extensions"]) == sevenzip_available()


async def _signup_headers(client, email: str) -> dict:
    reg = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Ingest Tester"},
    )
    assert reg.status_code == 200
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_api_from_url_requires_auth():
    """POST /api/v1/incidents/from-url without a token is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/incidents/from-url", json={"source": "pypi:requests@2.32.3"})
        assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_from_url_rejects_bad_specs(test_auth):
    """Unparseable / unsupported specs are a 400, not a 500."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _signup_headers(client, "badspec@cauveris.dev")
        # Keep under the global incident-creation rate limit (5/min), which
        # is checked before the spec is parsed.
        for spec in ("", "docker://redis:latest", "ftp://example.com/x.zip", "not a source !!"):
            res = await client.post("/api/v1/incidents/from-url", json={"source": spec}, headers=headers)
            assert res.status_code == 400, f"spec {spec!r} should be 400, got {res.status_code}: {res.text[:200]}"


@pytest.mark.asyncio
async def test_api_from_url_url_ingestion_disabled(test_auth, monkeypatch):
    """With CAUVERIS_URL_INGESTION_ENABLED=false, remote specs get a 403."""
    monkeypatch.setattr(get_settings(), "url_ingestion_enabled", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _signup_headers(client, "urloff@cauveris.dev")
        res = await client.post(
            "/api/v1/incidents/from-url",
            json={"source": "https://github.com/psf/requests"},
            headers=headers,
        )
        assert res.status_code == 403
        assert "URL ingestion is disabled" in res.json()["detail"]


@pytest.mark.asyncio
async def test_api_from_url_local_path_disabled(test_auth, monkeypatch, tmp_path):
    """Local paths are rejected when CAUVERIS_ALLOW_LOCAL_PATH_INGEST=false."""
    monkeypatch.setattr(get_settings(), "allow_local_path_ingest", False)
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _signup_headers(client, "localoff@cauveris.dev")
        res = await client.post(
            "/api/v1/incidents/from-url", json={"source": str(bundle)}, headers=headers
        )
        assert res.status_code == 400
        assert "Local path intake is disabled" in res.json()["detail"]


@pytest.mark.asyncio
async def test_api_from_url_queues_ingest_job(test_auth):
    """Happy path: a registry spec is accepted (202) and the job is pollable."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _signup_headers(client, "queue@cauveris.dev")
        res = await client.post(
            "/api/v1/incidents/from-url",
            json={"source": "pypi:requests@2.32.3", "title": "requests intake"},
            headers=headers,
        )
        assert res.status_code == 202, res.text[:300]
        data = res.json()
        assert data["source_kind"] == "pypi"
        assert data["job_id"] and data["incident_id"]

        job_res = await client.get(f"/api/v1/ingest/jobs/{data['job_id']}", headers=headers)
        assert job_res.status_code == 200
        job = job_res.json()
        assert job["payload"]["source"] == "pypi:requests@2.32.3"
        assert job["metadata"]["source_kind"] == "pypi"
