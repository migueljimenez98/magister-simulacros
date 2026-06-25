"""Shared slowapi rate-limiter instance.

Imported by main.py (for app wiring) and by individual routers that
need a non-default limit. All other routes pick up the global default
via the middleware registered in main.py.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    # 60 requests/minute is the default for all non-sensitive routes.
    # Specific endpoints override this with @limiter.limit(...).
    default_limits=["60/minute"],
)
