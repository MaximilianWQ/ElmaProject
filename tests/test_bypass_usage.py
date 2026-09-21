"""Bypass traffic consumption must be read from where Remnawave 3.x puts it.

Verified against the 3.4.3 contract: ``GET /api/users/by-username/{u}`` answers
``{response: ExtendedUsersSchema}``, and ``ExtendedUsersSchema`` is
``UsersSchema.extend({subscriptionUrl, activeInternalSquads, userTraffic})``.
``UsersSchema`` contains ``trafficLimitBytes`` but **no** ``usedTrafficBytes`` —
consumption lives in the nested ``userTraffic`` block
(``libs/contract/models/user-traffic.schema.ts``).

Reading ``usedTrafficBytes`` off the top level therefore always yielded 0, which
silently disabled every low-traffic warning, showed "0.0 ГБ использовано" in the
cabinet forever, and published ``download=0`` in Subscription-Userinfo.
"""
import pytest

from app.services import bypass_service as bp

GB = 1024 ** 3


def panel_user(used: int, limit: int) -> dict:
    """A 3.x user object exactly as the panel returns it (after _unwrap)."""
    return {
        "id": 42,
        "username": "elma_bp_7",
        "status": "ACTIVE",
        "trafficLimitBytes": limit,
        "trafficLimitStrategy": "NO_RESET",
        "subscriptionUrl": "https://panel.example/sub/abc",
        "activeInternalSquads": [],
        "userTraffic": {
            "usedTrafficBytes": used,
            "lifetimeUsedTrafficBytes": used,
            "onlineAt": None,
            "firstConnectedAt": None,
            "lastConnectedNodeUuid": None,
        },
    }


def test_used_traffic_comes_from_the_user_traffic_block():
    assert bp._extract(panel_user(3 * GB, 10 * GB))["used"] == 3 * GB


def test_limit_is_still_read_from_the_top_level():
    assert bp._extract(panel_user(3 * GB, 10 * GB))["limit"] == 10 * GB


def test_legacy_top_level_field_is_still_honoured():
    """Older panels put it at the top level — keep accepting that."""
    legacy = {"id": 1, "usedTrafficBytes": 5 * GB, "trafficLimitBytes": 10 * GB}
    assert bp._extract(legacy)["used"] == 5 * GB


def test_missing_traffic_block_reads_as_zero():
    assert bp._extract({"id": 1, "trafficLimitBytes": 10 * GB})["used"] == 0


@pytest.fixture
def panel(monkeypatch):
    """get_usage wired to a fake DB row and a fake panel read."""
    state = {"user": panel_user(7 * GB, 10 * GB), "meta": None}

    async def get_bypass(tg):
        return {
            "telegram_id": tg,
            "panel_uuid": "42",
            "subscription_url": "https://panel.example/sub/abc",
            "traffic_limit_bytes": 10 * GB,
        }

    async def find_user_by_username(username):
        return state["user"]

    async def set_bypass_meta(tg, *, subscription_url, traffic_limit_bytes):
        state["meta"] = (subscription_url, traffic_limit_bytes)

    monkeypatch.setattr(bp, "get_bypass", get_bypass)
    monkeypatch.setattr(bp.remnawave, "find_user_by_username", find_user_by_username)
    monkeypatch.setattr(bp, "set_bypass_meta", set_bypass_meta)
    return state


async def test_get_usage_reports_real_consumption(panel):
    usage = await bp.get_usage(7)

    assert usage["used"] == 7 * GB
    assert usage["remaining"] == 3 * GB
    assert usage["live"] is True


async def test_get_usage_never_reports_negative_remaining(panel):
    panel["user"] = panel_user(12 * GB, 10 * GB)  # overshot the pack

    assert (await bp.get_usage(7))["remaining"] == 0
