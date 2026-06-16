"""Per-process persistent event loop for Celery tasks.

Why this exists: the obvious `asyncio.new_event_loop()` + `run_until_complete()` +
`loop.close()` pattern, repeated in each task module, was the root cause of the
"got Future attached to a different loop" failures that took out the worker
after a deploy. SQLAlchemy's async engine caches asyncpg connections that are
bound to the loop they were created on; once that loop closes, the next task
opens a fresh loop, fetches the cached engine, and the pooled connections
explode on use.

The fix is to reuse a single asyncio loop for the lifetime of each Celery
worker process. Each prefork child gets its own loop on first use, and every
task inside that process runs on it — so the engine, the pool, and the
connections all stay on the same loop. `pool_pre_ping` + `pool_recycle` (set
in `database.py`) cover stale-connection cleanup.

Anything that needs to invoke an async coroutine from a sync Celery task
should import `run_async` from this module.
"""
import asyncio
from typing import Any, Coroutine

_loop: asyncio.AbstractEventLoop | None = None


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine on this process's persistent event loop.

    Safe to call repeatedly from a Celery task — successive calls reuse the
    same loop so SQLAlchemy's connection pool stays valid.
    """
    return _get_or_create_loop().run_until_complete(coro)
