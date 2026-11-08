"""Refuse other hosts and other origins: the guard every local companion app uses.

A companion app listens on this machine only. A web page you visit can still reach it: by
DNS rebinding (its own name pointing at 127.0.0.1, so the `Host` header names another site) or
directly, as a cross-site request or WebSocket (the browser sends its `Origin`). These checks
refuse both. Programs that aren't browsers send no `Origin`, so they pass with a local `Host`.
See docs/api/app_kit.md#local_guard.
"""

from __future__ import annotations

from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def require_loopback(host: str) -> str:
    """`host` if it's this machine's own address; a `ValueError` for any other (a companion app
    never listens on the network)."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"listens on this machine only (127.0.0.1, localhost or ::1), not {host!r}")
    return host


def _hostname(netloc: str) -> str | None:
    try:
        return urlsplit(f"//{netloc}").hostname
    except ValueError:
        return None


def local_request(host: str | None, origin: str | None) -> bool:
    """Whether a request may be served: its `Host` header names this machine, and, if a browser
    sent it (an `Origin` header), it comes from a page of the same app (same scheme-less host
    and port as `Host`). A missing `Host`, a foreign one, an `Origin` of `null` or another site:
    refused."""
    if not host or _hostname(host) not in LOOPBACK_HOSTS:
        return False
    if origin is None:
        return True
    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and parts.netloc.lower() == host.lower()
