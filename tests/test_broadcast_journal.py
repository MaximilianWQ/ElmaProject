"""A broadcast sent from inside the bot must land in the same history as one
sent from the dashboard, and a button that could not be built must be reported.

Two gaps this pins down:

1. The in-bot admin flow had its own send loop that never touched
   ``broadcast_history``, so those runs were invisible in the history/resend
   list — the two entry points disagreed about what a broadcast *is*.
2. ``build_markup`` drops any spec it cannot turn into a button (a percentage
   out of range, a label with no URL) and returned ``None`` as if no buttons had
   been asked for. The admin pressed "Отправить" and got a CTA-less broadcast
   with nothing to explain it.
"""
import pytest

from app.handlers import admin
from app.services import broadcast_runner as br
from app.services import broadcaster


# --- in-bot broadcasts are journalled --------------------------------------


@pytest.fixture
def journal(monkeypatch):
    state = {"record": None, "finish": None, "summaries": []}

    async def recipients(segment):
        return [1, 2, 3]

    async def record_broadcast(**kw):
        state["record"] = kw
        return 5

    async def finish_broadcast(bid, **kw):
        state["finish"] = (bid, kw)

    async def fake_broadcast(ids, send_one, **kw):
        return broadcaster.BroadcastResult(sent=2, failed=0, blocked=1)

    async def safe_send(bot, uid, text, **kw):
        state["summaries"].append(text)

    monkeypatch.setattr(admin, "recipients", recipients)
    monkeypatch.setattr(admin, "record_broadcast", record_broadcast, raising=False)
    monkeypatch.setattr(admin, "finish_broadcast", finish_broadcast, raising=False)
    monkeypatch.setattr(admin.broadcaster, "broadcast", fake_broadcast)
    monkeypatch.setattr(admin, "safe_send", safe_send)
    return state


async def test_in_bot_broadcast_is_written_to_history(journal):
    async def make_markup(uid):
        return None

    await admin._run_broadcast(object(), "all", None, "привет", 42, make_markup)

    assert journal["record"] is not None, "the run must be journalled at start"
    assert journal["record"]["segment"] == "all"
    assert journal["record"]["total"] == 3
    assert journal["record"]["admin_id"] == 42


async def test_in_bot_broadcast_records_its_result(journal):
    async def make_markup(uid):
        return None

    await admin._run_broadcast(object(), "all", None, "привет", 42, make_markup)

    bid, counts = journal["finish"]
    assert bid == 5
    assert (counts["sent"], counts["blocked"], counts["failed"]) == (2, 1, 0)


async def test_a_crashing_run_still_closes_its_history_row(journal, monkeypatch):
    """Otherwise the row sits at status='running' for ever."""
    async def blow_up(ids, send_one, **kw):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr(admin.broadcaster, "broadcast", blow_up)

    async def make_markup(uid):
        return None

    with pytest.raises(RuntimeError):
        await admin._run_broadcast(object(), "all", None, "привет", 42, make_markup)

    assert journal["finish"] is not None, "the journal must be closed out"
    assert journal["finish"][1]["failed"] == 3


# --- unbuildable buttons are surfaced --------------------------------------


def test_out_of_range_discount_is_reported_not_swallowed():
    markup, dropped = br.build_markup_report(
        None, None, '[{"kind": "discount", "pct": 150, "hours": 24, "scope": "all"}]'
    )
    assert markup is None
    assert dropped and "150" in dropped[0]


def test_label_without_url_is_reported():
    markup, dropped = br.build_markup_report("Купить", None, None)
    assert markup is None
    assert dropped and "URL" in dropped[0]


def test_valid_buttons_report_nothing():
    markup, dropped = br.build_markup_report(None, None, '[{"kind": "buy"}]')
    assert markup is not None
    assert dropped == []


@pytest.fixture
def sending_runner(monkeypatch):
    """run_broadcast wired so the send actually completes."""
    state = {"admin_messages": []}

    async def recipients(segment):
        return [1]

    async def record_broadcast(**kw):
        return 9

    async def finish_broadcast(bid, **kw):
        return None

    async def fake_broadcast(ids, send_one, **kw):
        return broadcaster.BroadcastResult(sent=1)

    async def safe_send(bot, uid, text, **kw):
        state["admin_messages"].append(text)

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(br.database, "recipients", recipients)
    monkeypatch.setattr(br.database, "record_broadcast", record_broadcast)
    monkeypatch.setattr(br.database, "finish_broadcast", finish_broadcast)
    monkeypatch.setattr(br.broadcaster, "broadcast", fake_broadcast)
    monkeypatch.setattr(br, "safe_send", safe_send)
    monkeypatch.setattr(br.config, "ADMIN_IDS", frozenset({999}))

    from app.services import push_service

    monkeypatch.setattr(push_service, "notify_broadcast_done", noop)
    return state


async def test_summary_warns_about_a_button_that_was_dropped(sending_runner):
    await br.run_broadcast(
        object(), admin_id=999, segment="all", text="привет",
        buttons='[{"kind": "discount", "pct": 150, "hours": 24, "scope": "all"}]',
    )

    summary = sending_runner["admin_messages"][0]
    assert "150" in summary, "the admin must learn the CTA never made it"


async def test_summary_is_clean_when_every_button_was_built(sending_runner):
    await br.run_broadcast(
        object(), admin_id=999, segment="all", text="привет",
        buttons='[{"kind": "buy"}]',
    )

    assert "пропущена" not in sending_runner["admin_messages"][0]


def test_build_markup_keeps_its_simple_signature():
    """The dashboard route calls build_markup(...) and expects just a markup."""
    assert br.build_markup(None, None, '[{"kind": "buy"}]') is not None
    assert br.build_markup("Купить", None, None) is None
