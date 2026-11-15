"""
Thin, in-process adapters from M4 to the other CropCompass modules.

Rules
-----
* Providers call the other modules' SERVICE-LAYER functions, never their
  FastAPI route handlers, and never re-implement their logic.
* Upstream modules are imported lazily inside each call, so a broken or
  missing dependency in another module degrades to status="unavailable"
  instead of preventing M4 from importing.
* Every provider returns a ProviderResult and never raises.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from intelligenceM4.schemas import ModuleStatus, ProviderResult

_MAX_ERROR_CHARS = 500


def describe_error(exc: BaseException) -> str:
    message = f"{type(exc).__name__}: {exc}"
    return message[:_MAX_ERROR_CHARS]


def provider_timeout_seconds() -> float:
    """Timeout for async upstream calls (env M4_PROVIDER_TIMEOUT_SECONDS)."""
    try:
        return float(os.getenv("M4_PROVIDER_TIMEOUT_SECONDS", "90"))
    except ValueError:
        return 90.0


def _finish(
    module: str,
    called: str,
    data: Any,
    status_fn: Callable[[Any], ModuleStatus] | None,
) -> ProviderResult:
    try:
        status = status_fn(data) if status_fn else "ok"
    except Exception as exc:  # a bad status flag must not crash the analysis
        return ProviderResult(
            module=module, status="unavailable", called=called,
            error=f"Could not read upstream status flags: {describe_error(exc)}",
        )
    return ProviderResult(module=module, status=status, data=data, called=called)


def safe_call(
    module: str,
    called: str,
    fn: Callable[[], Any],
    status_fn: Callable[[Any], ModuleStatus] | None = None,
) -> ProviderResult:
    """Run a synchronous upstream call; convert any failure into a status."""
    try:
        data = fn()
    except Exception as exc:
        return ProviderResult(
            module=module, status="unavailable", called=called,
            error=describe_error(exc),
        )
    return _finish(module, called, data, status_fn)


async def safe_call_async(
    module: str,
    called: str,
    fn: Callable[[], Awaitable[Any]],
    status_fn: Callable[[Any], ModuleStatus] | None = None,
    timeout: float | None = None,
) -> ProviderResult:
    """Run an async upstream call with a timeout; convert failure into a status."""
    limit = provider_timeout_seconds() if timeout is None else timeout
    try:
        data = await asyncio.wait_for(fn(), timeout=limit)
    except asyncio.TimeoutError:
        return ProviderResult(
            module=module, status="unavailable", called=called,
            error=f"TimeoutError: no response within {limit:g}s",
        )
    except Exception as exc:
        return ProviderResult(
            module=module, status="unavailable", called=called,
            error=describe_error(exc),
        )
    return _finish(module, called, data, status_fn)


def not_implemented(module: str, called: str, reason: str) -> ProviderResult:
    return ProviderResult(
        module=module, status="not_implemented", called=called, error=reason,
    )
