"""
URL safety validation to prevent SSRF (Server-Side Request Forgery).
Blocks requests to private/internal networks, cloud metadata endpoints,
and other dangerous destinations.
"""
import ipaddress
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Cloud metadata endpoints (AWS, GCP, Azure, etc.)
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",  # Alibaba Cloud metadata
}

_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/reserved range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        return False


def validate_url_safe(url: str) -> str:
    """Validate that a URL is safe to fetch (not targeting internal resources).

    Returns the validated URL string.
    Raises ValueError if the URL is unsafe.
    """
    if not url or not url.strip():
        raise ValueError("URL 不能为空")

    parsed = urlparse(url.strip())

    # Scheme check
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        raise ValueError(f"不允许的 URL 协议: {scheme}")
    if scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https 协议，当前: {scheme or '(空)'}")

    # Host check
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL 缺少主机名")

    # Block known metadata endpoints
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"不允许访问的地址: {hostname}")

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("不允许访问本地地址")

    # Block IP addresses in private ranges
    if _is_private_ip(hostname):
        raise ValueError(f"不允许访问内网地址: {hostname}")

    # Block IPv6 addresses in brackets (e.g., [::1], [::ffff:192.168.1.1])
    ipv6_str = None
    bracket_match = re.search(r'\[([^\]]+)\]', hostname)
    if bracket_match:
        ipv6_str = bracket_match.group(1)
    else:
        # Try parsing as bare IPv6 (use ipaddress for robust validation, not regex)
        try:
            ipaddress.IPv6Address(hostname)
            ipv6_str = hostname
        except ValueError:
            pass
    if ipv6_str and _is_private_ip(ipv6_str):
        raise ValueError(f"不允许访问内网 IPv6 地址: {hostname}")

    # Block hostnames that resolve to private IPs via DNS rebinding pattern
    # (e.g., 10.0.0.1.nip.io) — check for embedded IP patterns
    ip_pattern = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', hostname)
    if ip_pattern and _is_private_ip(ip_pattern.group(1)):
        raise ValueError(f"主机名包含内网 IP 地址: {hostname}")

    return url.strip()
