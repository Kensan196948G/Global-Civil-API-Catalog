"""SSRF guard for catalog endpoint URLs.

The weekly verification job fetches ``sample_endpoint``/``endpoint_template``
values over HTTP, and since the write API (PR #60) those fields are editable
by authenticated editors. Without validation an editor could point them at
loopback/LAN/cloud-metadata addresses and turn the verifier into an SSRF
proxy (external evaluation 2026-07-23, P0 finding).

Defence layers:

* write API (``web/api_v1.py``): scheme/format and IP-literal checks at
  save time (``validate_public_url(resolve=False)`` — cheap, deterministic);
* verifier (``scripts/run_verification.py``): ``fetch_public_url`` resolves
  the hostname once, validates every A/AAAA record, then **pins the TCP
  connection to the validated address** (TLS SNI/certificate checks still
  use the hostname). This closes the DNS-rebinding window between check and
  connect. Redirects are followed manually and each hop passes the same
  validate-resolve-pin cycle.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse

ALLOWED_SCHEMES = {"http", "https"}
_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # RFC 6598 shared address space


class URLPolicyError(Exception):
    """Raised when a URL (or one of its redirect hops) violates the policy."""


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT)
    )


def validate_public_url(url: str, *, resolve: bool = True) -> str | None:
    """Return None when the URL is acceptable, else a human-readable reason."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return "unparsable URL"
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return f"scheme '{parsed.scheme}' not allowed (http/https only)"
    if not parsed.hostname:
        return "missing hostname"
    if "@" in (parsed.netloc or ""):
        return "userinfo in URL not allowed"

    host = parsed.hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _blocked_ip(ip):
            return f"IP address {ip} is in a blocked range"
        return None

    if not resolve:
        return None
    try:
        _resolve_pinned(host, parsed.port or 443)
    except URLPolicyError as exc:
        return str(exc)
    return None


def _resolve_pinned(host: str, port: int) -> str:
    """Resolve host, validate every record, return the address to pin."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise URLPolicyError(f"hostname does not resolve ({exc})") from exc
    pinned: str | None = None
    for info in infos:
        resolved = ipaddress.ip_address(info[4][0])
        if _blocked_ip(resolved):
            raise URLPolicyError(f"hostname resolves to blocked address {resolved}")
        if pinned is None:
            pinned = str(resolved)
    if pinned is None:
        raise URLPolicyError("hostname does not resolve")
    return pinned


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that dials a pre-validated IP, not the hostname."""

    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP; SNI/cert use the hostname."""

    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def fetch_public_url(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    user_agent: str,
    max_redirects: int = 5,
) -> tuple[int, bytes, str]:
    """GET a public URL with per-hop validate-resolve-pin (SSRF guard).

    Returns ``(status, body, final_url)``; the body is capped at
    ``max_bytes``. Raises :class:`URLPolicyError` for policy violations and
    ``OSError`` family exceptions for ordinary network failures.
    """
    for _ in range(max_redirects + 1):
        reason = validate_public_url(url, resolve=False)
        if reason is not None:
            raise URLPolicyError(reason)
        parts = urllib.parse.urlsplit(url)
        scheme = parts.scheme.lower()
        host = parts.hostname or ""
        port = parts.port or (443 if scheme == "https" else 80)
        try:
            ipaddress.ip_address(host)
            pinned = host  # already validated public literal
        except ValueError:
            pinned = _resolve_pinned(host, port)
        conn_cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
        conn = conn_cls(host, port, pinned_ip=pinned, timeout=timeout)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        try:
            conn.request(
                "GET", path, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"}
            )
            response = conn.getresponse()
            if response.status in _REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    return response.status, b"", url
                url = urllib.parse.urljoin(url, location)
                continue
            return response.status, response.read(max_bytes), url
        finally:
            conn.close()
    raise URLPolicyError(f"too many redirects (>{max_redirects})")
