"""Background work started with fire-and-forget must survive and be observable.

``asyncio.create_task`` returns the only strong reference to a task — the event
loop keeps a weak one. A broadcast started as ``asyncio.create_task(run(...))``
with the result thrown away can therefore be collected mid-run, and any
exception inside it surfaces (if at all) only when the task object is finalised.
That is how a broadcast ends up stuck at ``status='running'`` with nothing in the
log. ``spawn`` holds the reference until completion and logs failures.
"""
import asyncio
import logging

from app.utils import tasks


async def test_spawned_task_is_held_until_it_finishes():
    release = asyncio.Event()

    async def work():
        await release.wait()
        return "done"

    task = tasks.spawn(work(), name="held")
    assert task in tasks.pending(), "a running task must keep a strong reference"

    release.set()
    assert await task == "done"
    assert task not in tasks.pending(), "finished tasks must not leak"


async def test_failure_is_logged_with_the_task_name(caplog):
    async def boom():
        raise RuntimeError("provisioning blew up")

    with caplog.at_level(logging.ERROR):
        task = tasks.spawn(boom(), name="broadcast-42")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)  # let the done-callback run

    assert "broadcast-42" in caplog.text
    assert "provisioning blew up" in caplog.text


async def test_cancellation_is_not_reported_as_a_failure(caplog):
    async def forever():
        await asyncio.Event().wait()

    with caplog.at_level(logging.ERROR):
        task = tasks.spawn(forever(), name="cancelled-one")
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert "cancelled-one" not in caplog.text, "shutdown is not an error"
