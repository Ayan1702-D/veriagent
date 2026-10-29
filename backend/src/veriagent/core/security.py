"""Security controls: input sanitization, prompt-injection defense, and SSRF guard."""

import ipaddress
import socket
from urllib.parse import urlparse

from veriagent.core.errors import SecurityViolationError

_BLOCKED_SCHEMES: frozenset[str] = frozenset({"file", "ftp", "gopher", "data", "ldap"})


def is_ip_blocked(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP is private, loopback, link-local, multicast, or reserved."""
    return (
        ip_addr.is_private
        or ip_addr.is_loopback
        or ip_addr.is_link_local
        or ip_addr.is_multicast
        or ip_addr.is_reserved
        or ip_addr.is_unspecified
    )


def validate_and_resolve_url(
    url: str,
    resolver: type[socket.getaddrinfo] = socket.getaddrinfo,
) -> str:
    """Validate URL scheme and resolve target host to verify it is public, else raise."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SecurityViolationError(f"Prohibited URL scheme: {scheme!r}")

    host = parsed.hostname
    if not host:
        raise SecurityViolationError("URL has empty hostname")

    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        addr_info = resolver(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SecurityViolationError(f"DNS resolution failure for host {host!r}") from exc

    if not addr_info:
        raise SecurityViolationError(f"No IP addresses resolved for host {host!r}")

    for _family, _, _, _, sockaddr in addr_info:
        raw_ip = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise SecurityViolationError(f"Invalid resolved IP: {raw_ip}") from exc

        if is_ip_blocked(ip_obj):
            raise SecurityViolationError(
                f"SSRF violation: Host {host!r} resolved to restricted IP: {raw_ip}"
            )

    return url
