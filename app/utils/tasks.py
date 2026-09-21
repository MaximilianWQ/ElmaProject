"""Fire-and-forget background work that doesn't vanish or fail silently.

``asyncio.create_task`` hands back the only *strong* reference to the task; the
event loop itself keeps a weak one. Dropping that reference — the classic
``asyncio.create_task(run_broadcast(...))`` one-liner — lets the garbage
collector finalise a task while it is still running, and any exception it raised
is reported only when the object is collected, if ever.

Both matter here: a broadcast is a long-lived detached task that writes its own
completion row, so losing it (or losing its traceback) leaves a run stuck at
``status='running'`` with nothing in the log to explain it.
"""
import asyncio
import logging
from typing import Any, Coroutine

logger = logging.getLogger(__name__)

# Strong references to everything currently in flight.
_running: set[asyncio.Task] = set()


def pending() -> frozenset[asyncio.Task]:
    """Tasks still in flight (a snapshot — mainly for tests and diagnostics)."""
    return frozenset(_running)


def _report(task: asyncio.Task) -> None:
    _running.discard(task)
    if task.cancelled():
        return  # shutdown, not a failure
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %r failed: %s", task.get_name(), exc, exc_info=exc
        )


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task:
    """Run ``coro`` in the background, keeping it alive and logging failures."""
    task = asyncio.create_task(coro, name=name)
    _running.add(task)
    task.add_done_callback(_report)
    return task
