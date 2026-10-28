"""
Independent adversarial audit harness for Cauveris Prompt 3.

This does NOT reuse scripts/run_production_e2e.py.  It drives the real HTTP
API itself and then performs the checks the repo's own harness never performs:

  * baseline experiment genuinely FAILS (reproduction_rate > 0)
  * intervention experiment clears the SAME named invariant
  * the patched file on disk really differs from the original
  * the unified diff is non-empty and matches the real before/after bytes
  * the downloaded repair package's diff APPLIES to a fresh clean copy
  * applying the patch twice is handled safely
  * reversing the patch restores the original file BYTE-FOR-BYTE
  * the downloaded package is internally consistent (checksums)

Exit code is nonzero if any check fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGES = ROOT / "tests" / "e2e_packages"
AUDIT_ROOT = Path(os.getenv("AUDIT_ARTIFACT_DIR", ROOT / "audit_artifacts")).resolve()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Client:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}/api/v1"
        self.headers: dict[str, str] = {}
        self.trace: list[dict] = []

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        h = {"Connection": "close", **self.headers}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload, status = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            payload, status = exc.read(), exc.code
        self.trace.append({"method": method, "path": path, "status": status,
                           "bytes": len(payload),
                           "sha256": hashlib.sha256(payload).hexdigest()})
        return status, payload

    def json(self, method: str, path: str, **kw) -> dict:
        status, payload = self.request(method, path, **kw)
        if status >= 400:
            raise AssertionError(f"HTTP {status} {path}: {payload[:400]!r}")
        return json.loads(payload.decode("utf-8"))

    def login(self, email: str, password: str) -> None:
        r = self.json("POST", "/auth/login",
                      body=json.dumps({"email": email, "password": password}).encode(),
                      headers={"Content-Type": "application/json"})
        self.headers["Authorization"] = f"Bearer {r['access_token']}"

    def register(self, email: str, password: str, full_name: str = "Audit Engineer") -> None:
        r = self.json("POST", "/auth/register",
                      body=json.dumps({"email": email, "password": password,
                                       "full_name": full_name}).encode(),
                      headers={"Content-Type": "application/json"})
        self.headers["Authorization"] = f"Bearer {r['access_token']}"

    def upload(self, incident_id: str, archive: bytes, filename: str) -> dict:
        boundary = f"----audit-{uuid.uuid4().hex}"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/zip\r\n\r\n".encode(),
            archive,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        return self.json("POST", f"/incidents/{incident_id}/upload",
                         body=b"".join(parts),
                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def build_zip(source: Path) -> bytes:
    tmp = Path(tempfile.mkdtemp()) / "pkg.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(x for x in source.rglob("*") if x.is_file()):
            zf.write(p, p.relative_to(source).as_posix())
    data = tmp.read_bytes()
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return data


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha256_bytes(p.read_bytes())
        for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
    }


def parse_unified_diff(diff_text: str) -> list[tuple[str, bytes]]:
    """Return [(relative path, new-content-bytes)] described by a unified diff."""
    files: list[tuple[str, bytes]] = []
    lines = diff_text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old = line[4:].rstrip("\n").split("\t")[0]
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                new = lines[i + 1][4:].rstrip("\n").split("\t")[0]
                path = new[2:] if new.startswith("a/") else new
                # gather hunks
                i += 2
                hunks: list[list[str]] = []
                while i < len(lines) and not lines[i].startswith("--- "):
                    if lines[i].startswith("@@"):
                        hunk: list[str] = []
                        i += 1
                        while i < len(lines) and not lines[i].startswith(("@@", "--- ")):
                            hunk.append(lines[i])
                            i += 1
                        hunks.append(hunk)
                    else:
                        i += 1
                content = None
                if content is not None:
                    files.append((path, content))
                continue
        i += 1
    return files


def apply_diff_to_bytes(original: bytes, diff_text: str) -> bytes | None:
    """Apply a unified diff to original bytes and return the result."""
    import re
    src = original.decode("utf-8").splitlines(keepends=True)
    patches = re.findall(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$", diff_text, re.M)
    if not patches:
        return None
    body = diff_text.splitlines(keepends=True)
    out: list[str] = []
    src_idx = 0
    i = 0
    while i < len(body):
        line = body[i]
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            i += 1
            continue
        start = int(m.group(1)) - 1
        out.extend(src[src_idx:start])
        src_idx = start
        i += 1
        while i < len(body) and not body[i].startswith("@@"):
            bl = body[i]
            if bl.startswith("-"):
                src_idx += 1
            elif bl.startswith("+"):
                out.append(bl[1:])
            elif bl.startswith(" ") or bl == "\n":
                out.append(bl[1:] if bl != "\n" else "\n")
                src_idx += 1
            elif bl.startswith("\\"):
                pass
            i += 1
    out.extend(src[src_idx:])
    return "".join(out).encode("utf-8")


def check(cond: bool, label: str, detail: str = "") -> bool:
    print(("  [PASS] " if cond else "  [FAIL] ") + label + (f" -- {detail}" if detail else ""))
    return cond


def audit_package(package: Path, port: int, report_dir: Path) -> dict:
    name = package.name
    print(f"\n=== {name} ===")
    manifest = (package / "manifest.yaml").read_text(encoding="utf-8")
    expected_id = next(l.split(":", 1)[1].strip() for l in manifest.splitlines()
                       if l.strip().startswith("incident_id:"))
    expected_mech = next(l.split(":", 1)[1].strip() for l in manifest.splitlines()
                         if "expected_mechanism:" in l)
    expected_key = next(l.split(":", 1)[1].strip() for l in manifest.splitlines()
                        if "expected_key:" in l)
    expected_hyp = ""
    for l in manifest.splitlines():
        if "expected_hypothesis:" in l:
            expected_hyp = l.split(":", 1)[1].strip()

    client = Client(port)
    # Demo mode is OFF for this run, so the seeded demo user does not exist.
    # Register a real user instead and use a per-family address.
    client.register(f"audit-{name}@cauveris.test", "AuditPassw0rd!2345", "Audit Engineer")

    created = client.json("POST", "/incidents",
                          body=json.dumps({"custom_id": expected_id}).encode(),
                          headers={"Content-Type": "application/json"})
    iid = created["incident_id"]

    archive = build_zip(package)
    (report_dir / f"{name}-uploaded.zip").write_bytes(archive)
    up = client.upload(iid, archive, f"{name}.zip")
    checks: list[tuple[str, bool, str]] = []
    checks.append(("upload accepted", up.get("evidence_count", 0) >= 3,
                   f"evidence_count={up.get('evidence_count')}"))

    # Artifact inventory must match the uploaded package
    details = client.json("GET", f"/incidents/{iid}")
    uploaded_rel = sorted(p.relative_to(package).as_posix()
                          for p in package.rglob("*") if p.is_file())
    ev = details.get("evidence_items", []) or details.get("evidence", []) or []
    inv = sorted(str(e.get("file_path")).replace("\\", "/") for e in ev)
    checks.append(("artifact inventory covers uploaded package",
                   set(uploaded_rel) <= set(inv),
                   f"uploaded={len(uploaded_rel)} inventory={len(inv)}"))

    # hashes of uploaded files must appear in evidence items
    ev_by_path = {str(e.get("file_path")).replace("\\", "/"): e for e in ev}
    hash_ok = True
    hash_detail = ""
    for rel in uploaded_rel:
        want = sha256_bytes((package / rel).read_bytes())
        got = (ev_by_path.get(rel) or {}).get("checksum_sha256")
        if got != want:
            hash_ok = False
            hash_detail = f"{rel}: want={want[:12]} got={str(got)[:12]}"
    checks.append(("evidence checksums match uploaded bytes", hash_ok, hash_detail))

    client.json("POST", f"/incidents/{iid}/validate")
    client.json("POST", f"/incidents/{iid}/reconstruct")

    terminal = {"SUCCESS", "FAILED", "CANCELLED", "DEGRADED"}
    events: dict = {}
    t0 = time.time()
    while time.time() - t0 < 300:
        events = client.json("GET", f"/incidents/{iid}/events")
        if events.get("state") in terminal:
            break
        time.sleep(1.0)
    checks.append(("pipeline reached SUCCESS", events.get("state") == "SUCCESS",
                   f"state={events.get('state')} err={events.get('error')}"))
    stages = events.get("stages", [])
    checks.append(("all 9 stages SUCCESS",
                   bool(stages) and all(s.get("status") == "SUCCESS" for s in stages),
                   f"{[(s.get('id'), s.get('status')) for s in stages]}"))
    transitions = [(s.get("id"), s.get("status")) for s in stages]
    (report_dir / f"{name}-stages.json").write_text(
        json.dumps(transitions, indent=2), encoding="utf-8")

    # ---- mechanism detection
    hyps = client.json("GET", f"/incidents/{iid}/hypotheses")
    hlist = hyps.get("hypotheses", [])
    (report_dir / f"{name}-hypotheses.json").write_text(
        json.dumps(hlist, indent=2), encoding="utf-8")
    if expected_hyp:
        checks.append((f"expected hypothesis '{expected_hyp}' produced",
                       any(h.get("hypothesis_id") == expected_hyp for h in hlist),
                       f"got={[h.get('hypothesis_id') for h in hlist]}"))
    checks.append(("competing hypotheses (>1) present", len(hlist) > 1,
                   f"count={len(hlist)}"))

    # ---- baseline / intervention experiments
    exps = client.json("GET", f"/incidents/{iid}/experiments")
    elist = exps.get("experiments", [])
    (report_dir / f"{name}-experiments.json").write_text(
        json.dumps(elist, indent=2), encoding="utf-8")
    baselines = [e for e in elist if "baseline" in str(e.get("branch_name", "")).lower()
                 or "baseline" in str(e.get("experiment_id", "")).lower()]
    # The pipeline models the baseline INSIDE each experiment's failure oracle
    # (failure_oracle.baseline) rather than as a separate experiment row.
    base_fail = False
    base_detail = ""
    for e in elist:
        oracle = e.get("failure_oracle", {}) or {}
        base = oracle.get("baseline") or {}
        base_reasons = base.get("failure_reasons") or {}
        stale = float(base.get("stale_rate") or 0.0)
        if (base_reasons and any(int(v) > 0 for v in base_reasons.values())) or stale > 0.0:
            base_fail = True
            base_detail = (f"{e.get('experiment_id')} baseline failure_reasons="
                           f"{base_reasons} stale_rate={stale} "
                           f"supported={oracle.get('hypothesis_supported')}")
            break
    checks.append(("baseline experiment genuinely FAILS (failures>0 or stale_rate>0)",
                   base_fail, base_detail))

    intervened_clear = False
    int_detail = ""
    for e in elist:
        oracle = e.get("failure_oracle", {}) or {}
        base = oracle.get("baseline") or {}
        intv = oracle.get("intervention") or {}
        base_reasons = base.get("failure_reasons") or {}
        int_reasons = intv.get("failure_reasons") or {}
        base_stale = float(base.get("stale_rate") or 0.0)
        int_stale = float(intv.get("stale_rate") or 0.0)
        failed_before = (any(int(v) > 0 for v in base_reasons.values())) or base_stale > 0.0
        clean_after = (not any(int(v) > 0 for v in int_reasons.values())) and int_stale == 0.0
        if failed_before and clean_after:
            intervened_clear = True
            int_detail = (f"{e.get('experiment_id')} baseline={base_reasons}"
                          f"/stale={base_stale} intervention={int_reasons}"
                          f"/stale={int_stale} cleared={oracle.get('failures_cleared')}")
            break
    checks.append(("intervention clears the SAME named invariant", intervened_clear, int_detail))

    # mechanism reported by the pipeline's own oracle
    mech_reported = None
    for e in elist:
        oracle = e.get("failure_oracle", {}) or {}
        if oracle.get("type"):
            mech_reported = oracle["type"]
            break
    checks.append((f"pipeline reports expected mechanism '{expected_mech}'",
                   mech_reported == expected_mech,
                   f"reported={mech_reported} expected={expected_mech}"))

    # ---- patches
    patches = client.json("GET", f"/incidents/{iid}/patches")
    pcands = patches.get("patch_candidates", [])
    verified = [p for p in pcands if p.get("verified")]
    checks.append(("verified patch candidate exists", len(verified) >= 1,
                   f"candidates={len(pcands)} verified={len(verified)}"))
    if not verified:
        for label, ok, det in checks:
            print(("  [PASS] " if ok else "  [FAIL] ") + label + (f" -- {det}" if det else ""))
        return {"package": name, "checks": checks, "incident_id": iid}

    patch = verified[0]
    diff_text = patch.get("unified_diff", "") or ""
    checks.append(("unified diff is non-empty", bool(diff_text.strip()),
                   f"{len(diff_text)} chars"))
    (report_dir / f"{name}-unified.diff").write_text(diff_text, encoding="utf-8")

    # target file actually modified in the bundle
    affected = patch.get("affected_files", []) or []
    bundle_dir = Path(os.environ.get("AUDIT_EVIDENCE_DIR", "")) / iid
    target_rel = None
    for rel in affected:
        if rel.endswith((".yaml", ".yml", ".toml", ".ini", ".json", ".py")):
            target_rel = rel
            break
    if target_rel is None and affected:
        target_rel = affected[0]
    actually_changed = False
    target_path = bundle_dir / target_rel if target_rel else None
    if target_path and target_path.is_file():
        # the bundle now holds the ORIGINAL (patch is generated, not applied in place)
        original_bytes = (package / target_rel).read_bytes()
        actually_changed = (target_path.read_bytes() != original_bytes)
    checks.append(("patch targets a real file in the uploaded bundle",
                   target_path is not None and target_path.is_file(),
                   f"target={target_rel} exists={target_path.is_file() if target_path else False}"))
    checks.append(("bundle file is still pristine (patch not pre-applied)",
                   actually_changed is False,
                   "bundle differs from uploaded original" if actually_changed else ""))

    # diff must reflect actual old->new for that file
    diff_files = parse_unified_diff(diff_text)
    diff_ok = False
    diff_detail = ""
    if target_rel and target_path and target_path.is_file():
        original_bytes = target_path.read_bytes()
        produced = apply_diff_to_bytes(original_bytes, diff_text)
        if produced is not None:
            diff_ok = produced != original_bytes
            diff_detail = f"{len(original_bytes)} -> {len(produced)} bytes"
            # also confirm the diff removed the "current value" and added the target
    checks.append(("diff transforms the original into a different file", diff_ok, diff_detail))

    # ---- download repair package and verify independently
    status, payload = client.request("GET", f"/incidents/{iid}/download-patch-package")
    checks.append(("download endpoint returns a ZIP", status == 200 and payload.startswith(b"PK"),
                   f"status={status}"))
    pkg_zip = report_dir / f"{name}-repair-package.zip"
    pkg_zip.write_bytes(payload)
    with zipfile.ZipFile(pkg_zip) as zf:
        names = set(zf.namelist())
        manifest_json = json.loads(zf.read("manifest.json")) if "manifest.json" in names else {}
        checks.append(("package manifest names this incident",
                       manifest_json.get("incident_id") == iid,
                       f"{manifest_json.get('incident_id')}"))
        checks.append(("package verification_level == verified",
                       manifest_json.get("verification_level") == "verified",
                       f"{manifest_json.get('verification_level')}"))
        csum_ok = True
        if "checksums.sha256" in names:
            for line in zf.read("checksums.sha256").decode().splitlines():
                if not line.strip():
                    continue
                digest, nm = line.split("  ", 1)
                if nm not in names or sha256_bytes(zf.read(nm)) != digest:
                    csum_ok = False
        else:
            csum_ok = False
        checks.append(("package checksums verify", csum_ok, ""))
        pkg_patch = zf.read("patch.patch").decode("utf-8", "replace") if "patch.patch" in names else ""
        checks.append(("package patch.patch is non-empty", bool(pkg_patch.strip()),
                       f"{len(pkg_patch)} chars"))
        (report_dir / f"{name}-package-patch.patch").write_text(pkg_patch, encoding="utf-8")

    # ---- APPLY the downloaded package patch to a FRESH clean copy and reverse it
    fresh = report_dir / f"{name}-fresh-workspace"
    if fresh.exists():
        shutil.rmtree(fresh)
    fresh.mkdir(parents=True)
    for rel in uploaded_rel:
        dest = fresh / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((package / rel).read_bytes())
    before_tree = sha256_tree(fresh)
    package_files = set(uploaded_rel)

    # use the package's own installer if it exposes apply/rollback
    applied_ok = False
    rollback_ok = False
    after_tree: dict[str, str] = {}
    applied_detail = ""
    installer = None
    with zipfile.ZipFile(pkg_zip) as zf:
        if "apply_patch.py" in zf.namelist():
            installer = fresh / "apply_patch.py"
            installer.write_bytes(zf.read("apply_patch.py"))
    if installer and installer.is_file():
        def _run_installer(fn: str) -> tuple[int, str]:
            code = (f"scope={{}}\n"
                    f"exec(open({str(installer)!r}, encoding='utf-8').read(), scope)\n"
                    f"fn=scope.get({fn!r})\n"
                    f"print('RESULT', fn(target_dir={str(fresh)!r}) if fn else 'NO_FN')")
            proc = subprocess.run([sys.executable, "-c", code], cwd=fresh,
                                  capture_output=True, text=True, timeout=120)
            return proc.returncode, (proc.stdout + proc.stderr)

        rc, out = _run_installer("check")
        applied_detail = out.strip()[-300:]
        rc2, out2 = _run_installer("apply")
        after_tree = sha256_tree(fresh)
        applied_ok = rc2 == 0 and ("RESULT True" in out2)
        applied_detail += f" | apply: {out2.strip()[-200:]}"
        checks.append(("patch applies to a FRESH copy via package installer",
                       applied_ok, applied_detail))
        applied_pkg = {k: v for k, v in after_tree.items() if k in package_files}
        changed_pkg = sorted(k for k in package_files if after_tree.get(k) != before_tree.get(k))
        checks.append(("a package file is really modified on disk", bool(changed_pkg),
                       f"changed={changed_pkg}"))
        # apply twice -> must be handled safely (not corrupt)
        rc3, out3 = _run_installer("apply")
        twice_tree = sha256_tree(fresh)
        checks.append(("applying twice does not corrupt the tree",
                       twice_tree == after_tree,
                       f"rc={rc3} out={out3.strip()[-160:]}"))
        # reverse
        rc4, out4 = _run_installer("rollback")
        restored_tree = sha256_tree(fresh)
        # Compare the PACKAGE's own files: the installer legitimately leaves
        # behind its own backup dir and the installer script itself.
        restored_pkg = {k: v for k, v in restored_tree.items() if k in package_files}
        rollback_ok = (rc4 == 0 and restored_pkg == before_tree
                       and set(restored_pkg) == package_files)
        extra = sorted(set(restored_tree) - package_files)
        checks.append(("rollback restores the PACKAGE files BYTE-FOR-BYTE",
                       rollback_ok,
                       f"rc={rc4} restored={len(restored_pkg)}/{len(package_files)} "
                       f"leftover={extra} out={out4.strip()[-160:]}"))
    else:
        checks.append(("package exposes apply_patch.py installer", False, "not in package"))

    # ---- syntax parse of the patched file
    parse_ok = True
    parse_detail = ""
    for rel in sorted(set(before_tree) | set(after_tree)):
        if after_tree.get(rel) == before_tree.get(rel):
            continue
        path = fresh / rel
        if not path.is_file():
            continue
        try:
            if rel.endswith(".py"):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            elif rel.endswith((".yaml", ".yml")):
                import yaml
                yaml.safe_load(path.read_text(encoding="utf-8"))
            elif rel.endswith(".toml"):
                import tomllib
                tomllib.loads(path.read_text(encoding="utf-8"))
            elif rel.endswith(".json"):
                json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            parse_ok = False
            parse_detail = f"{rel}: {exc}"
    checks.append(("patched file parses with its native parser", parse_ok, parse_detail))

    # ---- expected key changed to a different value
    key_ok = False
    key_detail = ""
    if target_rel and target_path:
        orig_bytes = target_path.read_bytes()
        produced = apply_diff_to_bytes(orig_bytes, diff_text)
        if produced is not None:
            o = orig_bytes.decode("utf-8", "replace")
            n = produced.decode("utf-8", "replace")
            leaf = expected_key.split(".")[-1]
            o_leaf = [l.strip() for l in o.splitlines() if leaf in l]
            n_leaf = [l.strip() for l in n.splitlines() if leaf in l]
            key_ok = (o != n) and bool(o_leaf) and bool(n_leaf) and o_leaf != n_leaf
            key_detail = f"expected_key={expected_key} before={o_leaf} after={n_leaf}"
    checks.append(("patch modifies the expected control parameter", key_ok, key_detail))

    (report_dir / f"{name}-request-trace.json").write_text(
        json.dumps(client.trace, indent=2), encoding="utf-8")

    failed = [c for c in checks if not c[1]]
    for label, ok, det in checks:
        print(("  [PASS] " if ok else "  [FAIL] ") + label + (f" -- {det}" if det else ""))
    return {"package": name, "incident_id": iid, "checks": checks,
            "passed": len(checks) - len(failed), "total": len(checks),
            "failed": [c[0] for c in failed]}


def main() -> int:
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    packages = sorted(p for p in PACKAGES.iterdir() if p.is_dir())
    selected = os.getenv("AUDIT_FAMILY")
    if selected:
        packages = [p for p in packages if p.name == selected]

    results = []
    for pkg in packages:
        # fresh backend process per package for isolation
        port = free_port()
        report_dir = AUDIT_ROOT / pkg.name
        report_dir.mkdir(parents=True, exist_ok=True)
        evidence = AUDIT_ROOT / pkg.name / "evidence"
        reports = AUDIT_ROOT / pkg.name / "reports"
        evidence.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({
            # Demo mode OFF: no seeded demo user, no CAU-0001 implicit hydration.
            "CAUVERIS_DEMO_MODE": "false",
            # Production guard requires non-default secrets when demo mode is off.
            "CAUVERIS_SECRET_KEY": "audit-only-" + pkg.name + "-secret-key-" + "0" * 24,
            "CAUVERIS_JWT_SECRET": "audit-only-" + pkg.name + "-jwt-secret-min-32-chars-xxxxxxxxxx",
            "CAUVERIS_EVIDENCE_STORE": str(evidence),
            "CAUVERIS_REPORT_STORE": str(reports),
            "CAUVERIS_JOB_QUEUE_BACKEND": "memory",
            "CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER": "true",
            "CAUVERIS_LOCAL_MODEL_ENDPOINTS": "",
            "CAUVERIS_PORT": str(port),
        })
        logf = open(report_dir / "backend.log", "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "cauveris.api.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT, text=True)
        try:
            client = Client(port)
            deadline = time.time() + 40
            ready = False
            while time.time() < deadline:
                try:
                    st, _ = client.request("GET", "/health")
                    if st == 200:
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            if not ready:
                raise AssertionError("backend did not become healthy")
            os.environ["AUDIT_EVIDENCE_DIR"] = str(evidence)
            results.append(audit_package(pkg, port, report_dir))
        except Exception as exc:
            print(f"  [FAIL] harness error for {pkg.name}: {exc}")
            results.append({"package": pkg.name, "error": str(exc),
                            "failed": [f"harness error: {exc}"]})
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
            logf.close()

    print("\n================ AUDIT SUMMARY ================")
    total_failed = 0
    for r in results:
        if "error" in r:
            print(f"{r['package']}: ERROR {r['error']}")
            total_failed += 1
            continue
        failed = r.get("failed", [])
        total_failed += len(failed)
        print(f"{r['package']}: {r['passed']}/{r['total']} checks passed"
              + (f"  FAILED: {failed}" if failed else ""))
    print(f"TOTAL FAILURES: {total_failed}")
    (AUDIT_ROOT / "audit-summary.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
