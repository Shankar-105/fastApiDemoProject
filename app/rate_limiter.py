"""Compatibility shim: keep `app.rate_limiter` available while
the implementation lives under `app.services.rate_limit_service`.

This module re-exports names from the service module so existing
imports (including tests) continue to work after the refactor.
"""

from app.services.rate_limit_service import *  # noqa: F401,F403
