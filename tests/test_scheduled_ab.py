"""A scheduled broadcast must carry its A/B variant into the run.

``scheduled_broadcasts`` had no ``text_b`` / ``is_ab`` columns and the scheduler
never passed them on, so a recurring A/B test quietly went out as plain variant
A — the admin saw an A/B broadcast in the wizard and got a single-variant send.
"""
import asyncio

import pytest

from app.services import broadcast_runner as br


class _Stop(Exception):
    """Breaks the scheduler's infinite loop after exactly one iteration."""


@pytest.fixture
def one_tick(monkeypatch):
    state = {"kwargs": None, "advanced": None, "futures": []}
    row = {
        "id": 3,
        "admin_id": 42,
        "segment": "all",
        "text": "вариант А",
        "text_b": "вариант Б",
        "is_ab": True,
        "photo_file_id": None,
        "button_text": None,
        "button_url": None,
        "buttons": None,
        "kind": "once",
        "time_msk": None,
        "weekdays": None,
    }

    async def due_scheduled():
        return [row]

    async def advance_scheduled(sid, nxt):
        state["advanced"] = (sid, nxt)

    async def fake_run(bot, **kw):
        state["kwargs"] = kw

    def fake_spawn(coro, *, name=None):
        fut = asyncio.ensure_future(coro)
        state["futures"].append(fut)
        return fut

    async def stop(_seconds):
        raise _Stop

    monkeypatch.setattr(br.database, "due_scheduled", due_scheduled)
    monkeypatch.setattr(br.database, "advance_scheduled", advance_scheduled)
    monkeypatch.setattr(br, "run_broadcast", fake_run)
    monkeypatch.setattr(br, "spawn", fake_spawn)
    monkeypatch.setattr(asyncio, "sleep", stop)
    return state


async def _run_one_tick(state):
    with pytest.raises(_Stop):
        await br.scheduled_broadcast_loop(object())
    await asyncio.gather(*state["futures"], return_exceptions=True)


async def test_scheduler_passes_the_b_variant_through(one_tick):
    await _run_one_tick(one_tick)

    kw = one_tick["kwargs"]
    assert kw is not None, "the due broadcast must have been fired"
    assert kw["text_b"] == "вариант Б"
    assert kw["is_ab"] is True


async def test_scheduler_still_fires_a_plain_broadcast(one_tick, monkeypatch):
    async def due_plain():
        return [{**(await _row()), "text_b": None, "is_ab": False}]

    async def _row():
        return {
            "id": 4, "admin_id": 42, "segment": "all", "text": "обычная",
            "photo_file_id": None, "button_text": None, "button_url": None,
            "buttons": None, "kind": "once", "time_msk": None, "weekdays": None,
        }

    monkeypatch.setattr(br.database, "due_scheduled", due_plain)
    await _run_one_tick(one_tick)

    kw = one_tick["kwargs"]
    assert kw["is_ab"] is False and kw["text_b"] is None
