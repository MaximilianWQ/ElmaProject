"""Connect screen access: a user with only bypass GB (no premium) can still
install — the screen shows the Обход key(s); premium-only shows VPN; both show
both; neither is blocked."""
import pytest

import app.handlers.onboarding as onb


class _Msg:
    def __init__(self):
        self.photo = self.video = self.animation = self.document = None


class _Call:
    def __init__(self, data):
        self.data = data
        self.message = _Msg()
        self.from_user = type("U", (), {"id": 42, "username": "u"})()
        self.answered = False

    async def answer(self, *a, **k):
        self.answered = True


@pytest.fixture
def wire(monkeypatch):
    cap = {}

    async def fake_show_screen(msg, key, text, reply_markup=None):
        cap["labels"] = [b.text for row in reply_markup.inline_keyboard for b in row]

    async def fake_no_access(call):
        cap["no_access"] = True

    async def none(uid):
        return None

    monkeypatch.setattr(onb, "show_screen", fake_show_screen)
    monkeypatch.setattr(onb, "_no_access", fake_no_access)
    monkeypatch.setattr(onb, "_agg_url", none)               # legacy path
    monkeypatch.setattr(onb, "_incy_vpn_key", none)          # no Incy for simplicity
    monkeypatch.setattr(onb, "_incy_bypass_key", none)
    return cap


async def _set(monkeypatch, *, premium, bypass):
    async def happ(uid):
        return "happ://crypt4/PREM" if premium else None

    async def bp(uid):
        return "happ://crypt4/BYPASS" if bypass else None

    monkeypatch.setattr(onb, "_happ_key", happ)
    monkeypatch.setattr(onb, "_bypass_key", bp)


async def test_bypass_only_can_connect(wire, monkeypatch):
    await _set(monkeypatch, premium=False, bypass=True)
    await onb.cb_connect(_Call("cn:ios"))
    assert "no_access" not in wire, "bypass-only user must NOT be blocked"
    labels = wire["labels"]
    assert "Happ Обход" in labels, "shows the Обход key"
    assert "Happ VPN" not in labels, "no VPN key without premium"


async def test_premium_only_shows_vpn(wire, monkeypatch):
    await _set(monkeypatch, premium=True, bypass=False)
    await onb.cb_connect(_Call("cn:ios"))
    assert "Happ VPN" in wire["labels"] and "Happ Обход" not in wire["labels"]


async def test_both_shows_both(wire, monkeypatch):
    await _set(monkeypatch, premium=True, bypass=True)
    await onb.cb_connect(_Call("cn:ios"))
    assert "Happ VPN" in wire["labels"] and "Happ Обход" in wire["labels"]


async def test_neither_is_blocked(wire, monkeypatch):
    await _set(monkeypatch, premium=False, bypass=False)
    await onb.cb_connect(_Call("cn:ios"))
    assert wire.get("no_access") is True
