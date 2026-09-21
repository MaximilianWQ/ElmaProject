"""The traffic monitor must ask the panel only for our own users.

The panel is shared: production logs show 65,150 users behind
rmnw.atlassecure.ru, of which ELMA's bypass entities are a small slice, and the
monitor read all of them every five minutes — 850 of 961 panel requests over an
86-minute window, 88% of the load, to send four pushes.

`GET /api/users/stream` (contract read at tag 3.4.3) has no username filter,
so a prefix cannot be pushed down. It does filter by `tag`, and `POST /api/users`
and `PATCH /api/users` both accept one, so the entities carry a tag of our own
and the monitor asks for that tag alone.

Entities created before the tag existed carry none, and a tag-filtered read
cannot see them. They must not silently stop receiving low-balance warnings, so
a pass that misses a user our own database knows about looks that one up, uses
the traffic from that very response, and writes the tag back — bounded per pass
so a large backlog cannot burst.
"""
import re

import pytest

import config
from app.services import bypass_service as bp
from app.services import remnawave as rw

GB = 1024 ** 3


def _user(username: str, used: int, limit: int, tag: str | None = None) -> dict:
    return {
        "id": abs(hash(username)) % 10_000,
        "username": username,
        "trafficLimitBytes": limit,
        "subscriptionUrl": f"https://panel/{username}",
        "userTraffic": {"usedTrafficBytes": used},
        **({"tag": tag} if tag else {}),
    }


# --- the tag itself --------------------------------------------------------


def test_tag_satisfies_the_panel_contract():
    """Panel rule: ^[A-Z0-9_]+$, at most 16 characters."""
    assert re.fullmatch(r"[A-Z0-9_]+", config.BYPASS_TAG)
    assert len(config.BYPASS_TAG) <= 16


def test_a_new_profile_is_created_carrying_the_tag():
    payload = bp._create_payload(777, GB)
    assert payload["tag"] == config.BYPASS_TAG


# --- the read is filtered --------------------------------------------------


@pytest.fixture
def panel(monkeypatch):
    """A shared panel: our two tagged users plus a stranger's."""
    everyone = [
        _user("elma_bp_1", 0, GB, config.BYPASS_TAG),
        _user("elma_bp_2", 0, GB, config.BYPASS_TAG),
        _user("elma_bp_legacy", 900_000_000, GB),   # ours, created before tags
        _user("othersvc_9", 0, GB, "OTHER"),        # not ours
    ]
    calls = []

    async def fake_req(method, path, **kwargs):
        params = kwargs.get("params") or {}
        calls.append((path, params))
        if path == "/api/users/stream":
            tag = params.get("tag")
            users = [u for u in everyone if tag is None or u.get("tag") == tag]
            return {"users": users, "nextCursor": None, "hasMore": False}
        m = re.match(r"/api/users/by-username/(.+)", path)
        if m:
            found = [u for u in everyone if u["username"] == m.group(1)]
            return found[0] if found else None
        return {}

    monkeypatch.setattr(rw, "_req", fake_req)
    return calls, everyone


async def test_iter_users_pushes_the_filter_into_the_query(panel):
    calls, _ = panel
    [u async for page in rw.iter_users(tag=config.BYPASS_TAG) for u in page]
    assert calls[0][1]["tag"] == config.BYPASS_TAG


async def test_snapshot_reads_only_our_tagged_users(panel):
    calls, _ = panel
    snap = await bp.usage_snapshot()

    assert set(snap) == {"elma_bp_1", "elma_bp_2"}, "a stranger's user leaked in"
    assert calls[0][1].get("tag") == config.BYPASS_TAG, "the read was not filtered"


# --- legacy users keep working ---------------------------------------------


async def test_an_untagged_user_is_still_measured_on_the_very_same_pass(panel):
    _, everyone = panel
    snap = await bp.usage_snapshot(expected=["elma_bp_1", "elma_bp_2", "elma_bp_legacy"])

    assert "elma_bp_legacy" in snap, "a pre-tag user lost its low-balance warning"
    assert snap["elma_bp_legacy"]["used"] == 900_000_000


async def test_the_missing_user_gets_tagged_so_the_next_pass_is_cheap(panel):
    calls, _ = panel
    await bp.usage_snapshot(expected=["elma_bp_1", "elma_bp_legacy"])

    patches = [p for p, params in calls if p == "/api/users"]
    assert patches, "the legacy user was never tagged, so every pass re-heals it"


async def test_healing_is_bounded_so_a_backlog_cannot_burst(panel, monkeypatch):
    monkeypatch.setattr(bp, "TAG_HEAL_PER_PASS", 2)
    calls, _ = panel
    missing = [f"elma_bp_old{i}" for i in range(50)]

    await bp.usage_snapshot(expected=["elma_bp_1"] + missing)

    lookups = [p for p, _ in calls if p.startswith("/api/users/by-username/")]
    assert len(lookups) == 2, f"healed {len(lookups)} in one pass, expected 2"
