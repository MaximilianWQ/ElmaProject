"""Too-long message bodies must be refused where they are authored.

Telegram caps a text message at 4096 characters after entity parsing and a
photo caption at 1024. Over the cap, the send fails for *every* recipient, and
`safe_send` swallows the resulting TelegramBadRequest — so an automation whose
text an admin pasted one paragraph too long stops reaching anybody, silently
and indefinitely. Broadcasts caught this at send time only: the composer
answered 201 and the admin learned about it from a DM, or, for a scheduled
run, whenever it eventually fired.

The guard belongs at the point where the text is saved. It measures the
*converted* body, so premium-emoji markup — forty-one raw characters that
render as two — must not be counted as length the reader never sees.
"""
import pytest
from aiohttp import web

import database
from app.api.dashboard.routes import automations as auto_route
from app.api.dashboard.routes import broadcasts as bc_route
from app.services import notifications

EMOJI = '![🛍](tg://emoji?id=5406683434124859552)'
LONG = "я" * 4200          # over TEXT_LIMIT once rendered
LONG_EMOJI = EMOJI * 200   # 8200 raw chars, 400 visible -> deliverable


class FakeRequest:
    def __init__(self, body: dict, **match):
        self._body = body
        self._data = {"admin": {"sub": "42"}}
        self.config_dict = {"bot": object()}
        self.match_info = match

    def __setitem__(self, k, v):
        self._data[k] = v

    def __getitem__(self, k):
        return self._data[k]

    async def json(self):
        return self._body


@pytest.fixture
def wired(monkeypatch):
    saved = {}

    async def noop(*a, **kw):
        return None

    async def set_override(key, **kw):
        saved["override"] = kw
        return None

    async def create_automation(**kw):
        saved["automation"] = kw
        return {"id": 1, **kw}

    async def segment_count(segment):
        return 3

    async def record_broadcast(**kw):
        return 1

    monkeypatch.setattr(database, "set_override", set_override)
    monkeypatch.setattr(database, "create_automation", create_automation)
    monkeypatch.setattr(database, "segment_count", segment_count)
    monkeypatch.setattr(database, "record_broadcast", record_broadcast)
    monkeypatch.setattr(database, "log_audit", noop)
    monkeypatch.setattr(bc_route, "spawn", lambda c, **kw: c.close(), raising=False)
    return saved


# --- custom automations ----------------------------------------------------


async def test_custom_automation_refuses_an_undeliverable_text(wired):
    req = FakeRequest({"name": "n", "trigger_type": "after_signup", "text": LONG})
    with pytest.raises(web.HTTPBadRequest) as exc:
        await auto_route.create_auto(req)
    assert "4096" in str(exc.value.reason)
    assert "automation" not in wired, "nothing may be stored"


async def test_custom_automation_accepts_premium_emoji_copy(wired):
    req = FakeRequest(
        {"name": "n", "trigger_type": "after_signup", "text": LONG_EMOJI}
    )
    await auto_route.create_auto(req)
    assert wired["automation"]["text"] == LONG_EMOJI


# --- built-in overrides ----------------------------------------------------


async def test_builtin_override_refuses_an_undeliverable_text(wired):
    key = notifications.builtin_registry()[0]["key"]
    req = FakeRequest({"enabled": True, "text": LONG}, key=key)
    with pytest.raises(web.HTTPBadRequest) as exc:
        await auto_route.set_builtin(req)
    assert "4096" in str(exc.value.reason)
    assert "override" not in wired


# --- broadcasts: refuse at compose time, not at send time ------------------


async def test_broadcast_create_refuses_before_accepting_the_job(wired):
    req = FakeRequest({"segment": "all", "text": LONG})
    with pytest.raises(web.HTTPBadRequest) as exc:
        await bc_route.create(req)
    assert "4096" in str(exc.value.reason)


async def test_broadcast_create_measures_the_caption_limit_with_a_photo(wired):
    req = FakeRequest({"segment": "all", "text": "я" * 1100, "photo_file_id": "f"})
    with pytest.raises(web.HTTPBadRequest) as exc:
        await bc_route.create(req)
    assert "1024" in str(exc.value.reason)


async def test_scheduled_create_refuses_before_storing_the_schedule(wired, monkeypatch):
    """A daily schedule with an undeliverable body fails once per day, forever."""
    stored = {}

    async def create_scheduled(**kw):
        stored.update(kw)
        return {"id": 1, **kw}

    monkeypatch.setattr(database, "create_scheduled", create_scheduled)
    req = FakeRequest(
        {"segment": "all", "text": LONG, "kind": "daily", "time_msk": "10:00"}
    )
    with pytest.raises(web.HTTPBadRequest) as exc:
        await bc_route.scheduled_create(req)
    assert "4096" in str(exc.value.reason)
    assert not stored, "nothing may be scheduled"


async def test_the_b_variant_is_measured_too(wired):
    """Send time checks both variants; the composer must not be laxer."""
    req = FakeRequest(
        {"segment": "all", "text": "короткий А", "text_b": LONG, "is_ab": True}
    )
    with pytest.raises(web.HTTPBadRequest) as exc:
        await bc_route.create(req)
    assert "4096" in str(exc.value.reason)
