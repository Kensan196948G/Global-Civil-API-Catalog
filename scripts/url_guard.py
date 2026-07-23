"""SSRF guard for catalog endpoint URLs.

The weekly verification job fetches ``sample_endpoint``/``endpoint_template``
values with urllib, and since the write API (PR #60) those fields are
editable by authenticated editors. Without validation an editor could point
them at loopback/LAN/cloud-metadata addresses and turn the verifier into an
SSRF proxy (external evaluation 2026-07-23, P0 finding).

Two layers use this module:

* write API (``web/api_v1.py``): scheme/format and IP-literal checks at
  save time (``resolve=False`` — cheap, deterministic);
* verifier (``scripts/run_verification.py``): full check including DNS
  resolution of every A/AAAA record and re-validation of each redirect hop
  (``resolve=True`` + ``SafeRedirectHandler``).

Known limitation (documented): validate-then-fetch cannot fully rule out
DNS rebinding without socket-level IP pinning; the redirect re-check plus
resolution of all records covers the realistic catalog-editing threat.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_SCHEMES = {"http", "https"}


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
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
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        return f"hostname does not resolve ({exc})"
    for info in infos:
        resolved = ipaddress.ip_address(info[4][0])
        if _blocked_ip(resolved):
            return f"hostname resolves to blocked address {resolved}"
    return None


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect target before it is followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reason = validate_public_url(newurl, resolve=True)
        if reason is not None:
            raise urllib.error.URLError(f"redirect blocked by URL policy: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_safe_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(SafeRedirectHandler())
