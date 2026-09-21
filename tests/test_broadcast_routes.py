"""The broadcast HTTP routes must hand the storage layer everything the wizard
collected, and must not pay for the recipient list twice.

1. ``scheduled_create`` dropped ``text_b`` / ``is_ab`` on the floor, so a
   recurring A/B test was stored — and later fired — as a plain single-variant
   broadcast. The columns and the scheduler already carry the variant; this is
   the last hop.
2. Starting a broadcast ran ``recipients()`` once for the HTTP response and
   then again inside ``run_broadcast``: two full scans of ``users`` per send,
   where the response only ever needed the count.
"""
import pytest
from aiohttp import web

import database
from app.api.dashboard.routes import broadcasts as route


class FakeRequest:
    def __init__(self, body: dict):
        self._body = body
        self.config_dict = {"bot": object()}
        self.match_info: dict[str, str] = {}
        self["admin"] = {"sub": "42"}

    def __setitem__(self, k, v):
        getattr(self, "_data", None) or setattr(self, "_data", {})
        self._data[k] = v

    def __getitem__(self, k):
        return self._data[k]

    async def json(self):
        return self._body


@pytest.fixture
def wired(monkeypatch):
    state = {"created": None, "recipients_calls": 0, "count_calls": 0, "spawned": []}

    async def recipients(segment):
        state["recipients_calls"] += 1
        return [1, 2, 3]

    async def segment_count(segment):
        state["count_calls"] += 1
        return 3

    async def create_scheduled(**kw):
        state["created"] = kw
        return {"id": 1, **kw}

    async def log_audit(*a, **kw):
        return None

    monkeypatch.setattr(database, "recipients", recipients)
    monkeypatch.setattr(database, "segment_count", segment_count)
    monkeypatch.setattr(database, "create_scheduled", create_scheduled)
    monkeypatch.setattr(database, "log_audit", log_audit)

    def fake_spawn(coro, **kw):
        coro.close()  # never actually run the send in a unit test
        state["spawned"].append(True)
        return None

    monkeypatch.setattr(route, "spawn", fake_spawn, raising=False)
    return state


def _ab_body(**over) -> dict:
    body = {
        "segment": "all",
        "text": "вариант А",
        "text_b": "вариант Б",
        "is_ab": True,
        "kind": "daily",
        "time_msk": "10:00",
    }
    body.update(over)
    return body


async def test_scheduled_create_stores_the_ab_variant(wired):
    await route.scheduled_create(FakeRequest(_ab_body()))

    created = wired["created"]
    assert created is not None
    assert created["text_b"] == "вариант Б"
    assert created["is_ab"] is True


async def test_scheduled_create_keeps_a_plain_broadcast_plain(wired):
    await route.scheduled_create(FakeRequest(_ab_body(text_b="", is_ab=False)))

    created = wired["created"]
    assert created["is_ab"] is False
    assert created["text_b"] is None


async def test_starting_a_broadcast_does_not_scan_users_twice(wired):
    resp = await route.create(FakeRequest({"segment": "all", "text": "привет"}))

    assert isinstance(resp, web.Response)
    assert wired["recipients_calls"] == 0, (
        "the response only needs the count; run_broadcast fetches the ids itself"
    )
    assert wired["count_calls"] == 1
