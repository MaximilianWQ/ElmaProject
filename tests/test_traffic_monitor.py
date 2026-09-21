"""The low-traffic monitor must cost a bounded number of panel requests.

It used to call ``get_usage`` per user, sequentially, every
``TRAFFIC_MONITOR_SECONDS``: one HTTP round-trip to Remnawave per bypass user,
per tick. At a few thousand users a single pass no longer fits in its own
interval, so passes overlap and the panel is hammered continuously.

Remnawave 3.x exposes cursor-paginated ``GET /api/users/stream`` returning the
same ``ExtendedUsersSchema`` objects (contract verified at tag 3.4.3), so the
whole population can be read in pages of up to 1000.
"""
import pytest

from app.services import bypass_service as bp
from app.services import notifications as nt
from app.services import remnawave as rw

GB = 1024 ** 3


def _user(username: str, used: int, limit: int) -> dict:
    return {
        "id": abs(hash(username)) % 10_000,
        "username": username,
        "trafficLimitBytes": limit,
        "subscriptionUrl": f"https://panel/{username}",
        "userTraffic": {"usedTrafficBytes": used},
    }


# --- paginated stream ------------------------------------------------------


@pytest.fixture
def paged(monkeypatch):
    pages = [
        {"users": [_user("elma_bp_1", 0, GB)], "nextCursor": "7", "hasMore": True},
        {"users": [_user("elma_bp_2", 0, GB)], "nextCursor": None, "hasMore": False},
    ]
    seen = []

    async def fake_req(method, path, **kwargs):
        seen.append((path, kwargs.get("params")))
        return pages[len(seen) - 1]

    monkeypatch.setattr(rw, "_req", fake_req)
    return seen


async def test_stream_follows_the_cursor_to_the_last_page(paged):
    names = [u["username"] async for page in rw.iter_users() for u in page]

    assert names == ["elma_bp_1", "elma_bp_2"]
    assert [p for p, _ in paged] == ["/api/users/stream", "/api/users/stream"]
    assert paged[1][1]["cursor"] == "7", "second request must carry nextCursor"


async def test_stream_stops_when_there_is_no_more(paged):
    pages = [page async for page in rw.iter_users()]
    assert len(pages) == 2, "must not keep polling after hasMore=False"


# --- the monitor -----------------------------------------------------------


@pytest.fixture
def monitor(monkeypatch):
    """Wire _traffic_monitor to a fake DB and a fake panel population."""
    state = {"panel_calls": 0, "sent": [], "levels": []}
    population = [
        # 0.1 GB (~102 МБ) left — under the 500 МБ step, so level 4 fires.
        _user("elma_bp_1", int(9.9 * GB), 10 * GB),
        _user("elma_bp_2", 1 * GB, 10 * GB),          # 9 GB left -> no push
        _user("elma_other", 0, 0),                    # not a bypass entity
    ]

    async def fake_iter(*a, **kw):
        state["panel_calls"] += 1
        yield population

    async def all_bypass():
        return [
            {"telegram_id": 1, "panel_uuid": "1", "traffic_limit_bytes": 10 * GB,
             "notify_level": -1},
            {"telegram_id": 2, "panel_uuid": "2", "traffic_limit_bytes": 10 * GB,
             "notify_level": -1},
        ]

    async def safe_send(bot, uid, text, **kw):
        state["sent"].append((uid, text))

    async def set_level(tg, level):
        state["levels"].append((tg, level))

    async def no_usage(tg):
        raise AssertionError("per-user panel reads must not happen any more")

    monkeypatch.setattr(rw, "iter_users", fake_iter)
    monkeypatch.setattr(bp, "get_usage", no_usage)
    monkeypatch.setattr(nt, "all_bypass", all_bypass)
    monkeypatch.setattr(nt, "safe_send", safe_send)
    monkeypatch.setattr(nt, "set_bypass_notify_level", set_level)
    monkeypatch.setattr(nt.config, "BYPASS_USERNAME_PREFIX", "elma_bp_")
    monkeypatch.setattr(nt, "_ov", {})
    return state


async def test_one_bulk_read_covers_every_user(monitor):
    await nt._traffic_monitor(object())
    assert monitor["panel_calls"] == 1, "one paginated read, not one per user"


async def test_notifies_only_the_user_who_crossed_a_threshold(monitor):
    await nt._traffic_monitor(object())

    assert [uid for uid, _ in monitor["sent"]] == [1]
    assert "500 МБ" in monitor["sent"][0][1]
    assert monitor["levels"] == [(1, 4)]
