"""
SSRF-hardened HTTPS fetcher for universal source intake.

Every remote source (GitHub/GitLab codeload archives, PyPI sdists, npm
tarballs, or any market-standard HTTPS URL) is downloaded through this
module, never through a bare ``httpx.get``.  The policy:

* HTTPS only - plain HTTP is rejected unless ``allow_loopback_fetch`` is
  set (a test-only escape hatch, never for production).
* No userinfo (``https://user:pass@host``) - credentials in URLs leak into
  logs and caches.
* Host allowlist - the built-in market-standard hosts (GitHub, GitLab,
  PyPI, npm) plus ``CAUVERIS_URL_ALLOWED_HOSTS``; wildcard suffixes like
  ``*.example.com`` are supported.  ``CAUVERIS_URL_ALLOW_ANY_PUBLIC_HOST``
  widens to any host, but the DNS check below still applies.
* DNS validation - every address ``getaddrinfo`` returns for the host is
  checked against loopback / private / link-local (incl. the cloud
  metadata endpoint 169.254.169.254) / CGNAT / multicast / reserved
  ranges before connecting.  A hostname that resolves to *any* blocked
  address is refused, so a single poisoned A record cannot slip through.
* Redirects are followed manually, one hop at a time, and every
  redirect target is put through the same URL + DNS validation.
* Streaming with a hard byte cap (``CAUVERIS_MAX_DOWNLOAD_SIZE``, falling
  back to ``CAUVERIS_MAX_UPLOAD_SIZE``) enforced while reading, plus an
  early ``Content-Length`` check - a lying server cannot make us buffer
  more than the cap.
* Optional outbound proxy (``CAUVERIS_URL_FETCH_PROXY``) and per-host
  bearer tokens (``CAUVERIS_GITHUB_TOKEN`` / ``CAUVERIS_GITLAB_TOKEN``).
  Tokens are attached only to the matching host family and are never
  logged or stored in provenance.

The HTTP call itself goes through ``_open_stream`` so tests can inject a
fake transport without touching the network.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from cauveris.config import Settings, get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "SourceFetchError",
    "SSRFBlockedError",
    "FetchedFile",
    "BUILTIN_ALLOWED_HOSTS",
    "host_is_allowed",
    "validate_url",
    "resolve_and_validate_host",
    "fetch_to_file",
]


class SourceFetchError(Exception):
    """A remote source could not be fetched (network, policy, or size)."""


class SSRFBlockedError(SourceFetchError):
    """A URL failed the SSRF policy checks and was refused."""


#: Market-standard hosts that are always allowed when URL intake is on.
BUILTIN_ALLOWED_HOSTS = {
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "gitlab.com",
    "api.gitlab.com",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "repo1.maven.org",
    "repo.maven.apache.org",
    "crates.io",
    "static.crates.io",
    "proxy.golang.org",
    "api.nuget.org",
    "rubygems.org",
}

#: Address ranges that must never be dialed for a user-supplied URL.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",  # CGNAT shared address space
        "127.0.0.0/8",
        "169.254.0.0/16",  # link-local, incl. cloud metadata 169.254.169.254
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",  # TEST-NET-1
        "192.168.0.0/16",
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved
        "::1/128",
        "::/128",
        "fc00::/7",  # ULA
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)

USER_AGENT = "Cauveris/0.1 (+https://github.com/cauveris; source-ingestion)"


@dataclass
class FetchedFile:
    """A downloaded payload staged on disk."""

    path: Path
    requested_url: str
    final_url: str
    size_bytes: int
    sha256: str
    content_type: str
    status_code: int


def _normalise_host(host: str) -> str:
    return host.strip().rstrip(".").lower()


def host_is_allowed(host: str, settings: Settings) -> bool:
    """Whether a host passes the allowlist (exact or ``*.suffix`` wildcard)."""
    host = _normalise_host(host)
    if not host:
        return False
    if settings.url_allow_any_public_host:
        return True
    allowed = set(BUILTIN_ALLOWED_HOSTS)
    for entry in (settings.url_allowed_hosts or "").split(","):
        entry = entry.strip().lower()
        if entry:
            allowed.add(entry)
    for entry in allowed:
        if entry.startswith("*."):
            suffix = entry[1:]  # ".example.com"
            if host.endswith(suffix) and host != suffix.lstrip("."):
                return True
        elif host == entry:
            return True
    return False


def _is_blocked_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(ip in net for net in _BLOCKED_NETWORKS)


def resolve_and_validate_host(host: str, port: int, settings: Settings) -> List[str]:
    """
    Resolve a host and reject it if ANY answer is a blocked address.

    Returns the list of resolved IP strings when every answer is public.
    Raises :class:`SSRFBlockedError` otherwise.  When
    ``allow_loopback_fetch`` is set (tests only) the address-range check is
    skipped but the host allowlist still applies.
    """
    host = _normalise_host(host)
    if not settings.allow_loopback_fetch and _looks_like_blocked_literal(host):
        raise SSRFBlockedError(f"URL host {host!r} is a blocked address literal")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Cannot resolve host {host!r}: {exc}") from exc
    ips: List[str] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFBlockedError(f"Unparseable DNS answer {ip_str!r} for {host!r}")
        if not settings.allow_loopback_fetch and _is_blocked_address(addr):
            raise SSRFBlockedError(
                f"Host {host!r} resolves to blocked address {ip_str} "
                "(loopback/private/link-local/metadata range)"
            )
        ips.append(ip_str)
    if not ips:
        raise SSRFBlockedError(f"Host {host!r} resolved to no addresses")
    return ips


def _looks_like_blocked_literal(host: str) -> bool:
    """Block obvious IP literals without DNS (e.g. http://169.254.169.254/)."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return _is_blocked_address(addr)


def validate_url(url: str, settings: Settings) -> Dict[str, str]:
    """
    Validate a URL against the SSRF policy and return its split parts.

    Raises :class:`SSRFBlockedError` for scheme/userinfo/allowlist/DNS
    violations.  Does not connect anywhere.
    """
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise SSRFBlockedError(f"Malformed URL: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme == "http" and not settings.allow_loopback_fetch:
        raise SSRFBlockedError("Only HTTPS URLs may be fetched (http is refused)")
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(
            f"Unsupported URL scheme {parts.scheme!r}; use https://, github:, pypi:, npm:, or a local path"
        )
    if parts.username or parts.password:
        raise SSRFBlockedError("URLs with embedded credentials (userinfo) are refused")
    host = _normalise_host(parts.hostname or "")
    if not host:
        raise SSRFBlockedError("URL has no host")
    if not host_is_allowed(host, settings):
        raise SSRFBlockedError(
            f"Host {host!r} is not in the URL allowlist "
            "(set CAUVERIS_URL_ALLOWED_HOSTS or CAUVERIS_URL_ALLOW_ANY_PUBLIC_HOST=true)"
        )
    port = parts.port or (443 if scheme == "https" else 80)
    resolve_and_validate_host(host, port, settings)
    return {"scheme": scheme, "host": host, "port": str(port), "path": parts.path or "/"}


def _auth_headers_for_host(host: str, settings: Settings) -> Dict[str, str]:
    """Attach a configured token only to the host family it belongs to."""
    host = _normalise_host(host)
    headers: Dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if settings.github_token and (
        host == "github.com" or host.endswith(".github.com") or host.endswith(".githubusercontent.com")
    ):
        headers["Authorization"] = f"Bearer {settings.github_token}"
    elif settings.gitlab_token and (host == "gitlab.com" or host.endswith(".gitlab.com")):
        headers["PRIVATE-TOKEN"] = settings.gitlab_token
    return headers


async def _open_stream(
    client: httpx.AsyncClient, method: str, url: str, headers: Dict[str, str]
) -> httpx.Response:
    """Single request, no automatic redirects (we re-validate each hop)."""
    return await client.send(
        httpx.Request(method, url, headers=headers), stream=True, follow_redirects=False
    )


async def _aclose_response(response: httpx.Response) -> None:
    """Close a streaming response (async stream -> aclose; sync fallback)."""
    try:
        await response.aclose()
    except RuntimeError:
        response.close()


async def fetch_to_file(
    url: str,
    dest_dir: Path,
    settings: Optional[Settings] = None,
    *,
    filename: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> FetchedFile:
    """
    Download ``url`` to a file under ``dest_dir`` with the full SSRF policy.

    The response is streamed to disk and aborted the moment the byte cap
    (``settings.effective_max_download_size``) is exceeded, so a hostile
    server cannot exhaust memory.  Redirects are followed manually up to
    ``settings.url_max_redirects`` hops, each re-validated.
    """
    settings = settings or get_settings()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    requested_url = url
    current = url
    max_redirects = max(0, int(settings.url_max_redirects))
    redirects = 0

    owned_client = client is None
    if owned_client:
        try:
            client = httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(settings.url_fetch_timeout_seconds),
                proxy=settings.url_fetch_proxy or None,
            )
        except TypeError:  # older httpx used `proxies=`
            legacy_proxy_kwargs: Dict[str, Any] = {"proxies": settings.url_fetch_proxy or None}
            client = httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(settings.url_fetch_timeout_seconds),
                **legacy_proxy_kwargs,
            )
    assert client is not None

    try:
        while True:
            validate_url(current, settings)
            host = _normalise_host(urlsplit(current).hostname or "")
            headers = _auth_headers_for_host(host, settings)
            if extra_headers:
                # Caller-supplied headers (e.g. Accept for API JSON) merge in,
                # but never override the auth headers we attach.
                for k, v in extra_headers.items():
                    headers.setdefault(k, v)
            try:
                response = await _open_stream(client, "GET", current, headers)
            except SSRFBlockedError:
                raise
            except httpx.HTTPError as exc:
                raise SourceFetchError(f"HTTP fetch failed for {current!r}: {exc}") from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                await _aclose_response(response)
                if not location:
                    raise SourceFetchError(f"Redirect without Location header from {current!r}")
                redirects += 1
                if redirects > max_redirects:
                    raise SSRFBlockedError(f"Too many redirects (>{max_redirects}) fetching {requested_url!r}")
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                snippet = ""
                try:
                    snippet = (await response.aread())[:200].decode("utf-8", "ignore")
                except Exception:
                    pass
                await _aclose_response(response)
                raise SourceFetchError(
                    f"GET {current!r} returned HTTP {response.status_code} {snippet!r}"
                )

            # Early Content-Length check, then stream with a hard cap.
            cap = int(settings.effective_max_download_size)
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > cap:
                        await _aclose_response(response)
                        raise SourceFetchError(
                            f"Remote resource is {int(content_length)} bytes, exceeding the "
                            f"{cap}-byte download cap (CAUVERIS_MAX_DOWNLOAD_SIZE)"
                        )
                except ValueError:
                    pass

            name = filename or Path(urlsplit(current).path).name or "download.bin"
            name = name.replace("\\", "/").split("/")[-1] or "download.bin"
            dest = dest_dir / name
            if dest.exists():
                # Never clobber an existing staged file: a same-named second
                # download would silently overwrite the first (metadata vs
                # payload, or two concurrent jobs sharing a dir).
                await _aclose_response(response)
                raise SourceFetchError(
                    f"Refusing to overwrite existing file {dest} "
                    "(each fetch must target a unique destination)"
                )
            hasher = hashlib.sha256()
            size = 0
            try:
                with open(dest, "wb") as out:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        size += len(chunk)
                        if size > cap:
                            raise SourceFetchError(
                                f"Download exceeded the {cap}-byte cap (CAUVERIS_MAX_DOWNLOAD_SIZE)"
                            )
                        hasher.update(chunk)
                        out.write(chunk)
            except BaseException:
                try:
                    if dest.exists():
                        dest.unlink()
                except OSError:
                    pass
                raise
            finally:
                await _aclose_response(response)

            return FetchedFile(
                path=dest,
                requested_url=requested_url,
                final_url=current,
                size_bytes=size,
                sha256=hasher.hexdigest(),
                content_type=response.headers.get("content-type", "application/octet-stream"),
                status_code=response.status_code,
            )
    finally:
        if owned_client:
            await client.aclose()
