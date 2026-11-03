"""Webhook URL safety (SSRF guard).

A webhook URL is chosen by a business, and FOID's server is the one that calls it — so without a
guard, a business could point it at FOID's own network (cloud metadata at 169.254.169.254, Redis,
the database, admin ports) and use FOID as a proxy.

Rules:
- Live: https only. Test: http or https.
- Never to private, link-local, carrier-grade NAT, reserved, multicast or unspecified addresses,
  or internal-looking hostnames (single label, *.internal, *.local, …).
- Loopback (localhost, 127.0.0.0/8, ::1) only for **test** endpoints and only while
  WEBHOOK_ALLOW_LOCALHOST is on (default: on outside production) — that's what lets a developer
  receive webhooks on their own machine.

Checked twice: when the URL is saved (clear error in the console) and at every delivery, where
the hostname is resolved, every address is checked, and the request goes to that checked address
(Host header + TLS SNI keep the original name), so DNS can't be switched to an internal address
between the check and the connection (DNS rebinding).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.config import get_settings
from app.core.api_errors import ApiError

IP = ipaddress.IPv4Address | ipaddress.IPv6Address
_INTERNAL_SUFFIXES = (".internal", ".local", ".localdomain", ".lan", ".home", ".corp", ".intranet", ".home.arpa")


class BlockedUrl(ValueError):
    pass


def allow_loopback(env: str) -> bool:
    s = get_settings()
    allowed = s.WEBHOOK_ALLOW_LOCALHOST if s.WEBHOOK_ALLOW_LOCALHOST is not None else s.ENV != "production"
    return env == "test" and allowed


def _ip(host: str) -> IP | None:
    try:
        ip = ipaddress.ip_address(host.strip("[]").split("%")[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:   # ::ffff:127.0.0.1 is 127.0.0.1
        return ip.ipv4_mapped
    return ip


def _check_ip(ip: IP, env: str) -> None:
    if ip.is_loopback:
        if allow_loopback(env):
            return
        raise BlockedUrl("Webhooks can't be sent to localhost" +
                         (" in live mode" if env == "live" else " on this server"))
    if not ip.is_global or ip.is_multicast or ip.is_unspecified:
        raise BlockedUrl(f"Webhooks can't be sent to a private or reserved address ({ip})")


def _check_static(url: str, env: str) -> tuple[str, str, int]:
    """Everything that can be checked without DNS. Returns (scheme, host, port)."""
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise BlockedUrl("That isn't a valid URL")
    scheme, host = p.scheme.lower(), (p.hostname or "").lower().rstrip(".")
    if scheme not in ("http", "https"):
        raise BlockedUrl("Use an http(s) URL")
    if env == "live" and scheme != "https":
        raise BlockedUrl("Live webhooks must use https")
    if p.username or p.password:
        raise BlockedUrl("Don't put a username or password in the URL — verify the FOID-Signature instead")
    if not host:
        raise BlockedUrl("The URL has no host")
    ip = _ip(host)
    if ip is not None:
        _check_ip(ip, env)
    elif host == "localhost" or host.endswith(".localhost"):
        _check_ip(ipaddress.ip_address("127.0.0.1"), env)
    elif "." not in host or host.endswith(_INTERNAL_SUFFIXES):
        raise BlockedUrl("Use a public hostname — internal network names can't receive webhooks")
    return scheme, host, port or (443 if scheme == "https" else 80)


def check_url(url: str, env: str) -> str:
    """For create/update: the URL, or a 400 the console can show next to the field."""
    try:
        _check_static(url, env)
    except BlockedUrl as e:
        raise ApiError(400, "invalid_webhook_url", str(e), "url")
    return url


async def resolve(host: str, port: int) -> list[str]:
    """All addresses for host (tests replace this so they never touch real DNS)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(i[4][0]) for i in infos))


@dataclass
class Target:
    url: str                 # with the checked IP in place of the hostname
    host_header: str | None
    sni_hostname: str | None


async def safe_target(url: str, env: str) -> Target:
    """For delivery: resolve, check every address, and pin the connection to a checked one."""
    scheme, host, port = _check_static(url, env)
    if _ip(host) is not None:
        return Target(url, None, None)
    try:
        addrs = await resolve(host, port)
    except OSError as e:
        raise BlockedUrl(f"Couldn't resolve {host}: {e}")
    if not addrs:
        raise BlockedUrl(f"Couldn't resolve {host}")
    for a in addrs:                       # one bad record is enough to refuse (rebinding tricks)
        ip = _ip(a)
        if ip is None:
            raise BlockedUrl(f"{host} resolved to an unexpected address")
        _check_ip(ip, env)
    ip = _ip(addrs[0])
    assert ip is not None
    p = urlsplit(url)
    literal = f"[{ip}]" if ip.version == 6 else str(ip)
    netloc = f"{literal}:{p.port}" if p.port else literal
    return Target(urlunsplit((p.scheme, netloc, p.path, p.query, "")),
                  host_header=p.netloc.rsplit("@", 1)[-1],
                  sni_hostname=host if scheme == "https" else None)
