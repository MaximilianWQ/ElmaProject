"""Broadcast invariants that only show up end to end.

1. The length guard must measure what actually goes on the wire. The composer
   accepts Telegram-Ads premium-emoji markup — ``![🛍](tg://emoji?id=…)`` — and
   `build_sender` converts it to a `<tg-emoji>` tag before sending. Forty-one
   raw characters become two visible ones, and ELMA's own copy is full of them,
   so measuring the raw body rejects perfectly deliverable broadcasts.

2. Progress reported mid-run must describe the whole run. In an A/B send the
   two halves go out one after the other, so a report from the second half that
   carries cumulative `sent` but only its own `blocked`/`failed` is not a
   snapshot of anything.

3. Every recipient must end up in exactly one bucket: sent + blocked + failed.
"""
import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.services import broadcast_runner as br
from app.services import broadcaster
from app.utils import convert_tg_emoji

EMOJI = '![🛍](tg://emoji?id=5406683434124859552)'


# --- 1. length is measured on what is sent ---------------------------------


def test_premium_emoji_markup_is_measured_as_it_will_render():
    body = EMOJI * 26 + "Скидка только сегодня"
    assert br.visible_length(convert_tg_emoji(body)) < 200, "sanity: it is short"
    br.check_length(body, photo=True)  # must not raise


def test_a_genuinely_long_caption_is_still_refused():
    br_body = EMOJI + "я" * 1100
    with pytest.raises(br.BroadcastTooLong):
        br.check_length(br_body, photo=True)


def test_reported_length_is_the_delivered_length():
    body = EMOJI * 3 + "привет"
    with pytest.raises(br.BroadcastTooLong) as exc:
        br.check_length(body + "я" * 1100, photo=True)
    # 3 emoji (2 units each) + "привет" + 1100 -> 1112, not the ~1230 raw chars.
    assert "1112" in str(exc.value)


# --- 2 & 3. accounting and progress ----------------------------------------


@pytest.fixture
def runner(monkeypatch):
    state = {"progress": [], "done": None, "finished": None}
    # Progress reports every ~1/10th of a half, floored at 100 dispatches, so
    # the audience has to be big enough for any report to fire at all.
    ids = list(range(1, 2001))  # 1000 even, 1000 odd

    async def recipients(segment):
        return ids

    async def record_broadcast(**kw):
        return 1

    async def finish_broadcast(bid, **kw):
        state["finished"] = kw

    async def safe_send(bot, uid, text, **kw):
        return None

    async def noop(*a, **kw):
        return None

    def publish(ev):
        if ev.get("type") == "broadcast:progress":
            state["progress"].append(ev)
        if ev.get("type") == "broadcast:done":
            state["done"] = ev

    monkeypatch.setattr(br.database, "recipients", recipients)
    monkeypatch.setattr(br.database, "record_broadcast", record_broadcast)
    monkeypatch.setattr(br.database, "finish_broadcast", finish_broadcast)
    monkeypatch.setattr(br, "safe_send", safe_send)
    monkeypatch.setattr(br.bus, "publish", publish)
    monkeypatch.setattr(br.config, "ADMIN_IDS", frozenset({1}))

    from app.services import push_service

    monkeypatch.setattr(push_service, "notify_broadcast_done", noop)
    return state, ids


async def test_every_recipient_lands_in_exactly_one_bucket(runner, monkeypatch):
    """A mixed run: some delivered, some blocked, some broken."""
    async def unreachable(uid):
        return None

    monkeypatch.setattr(broadcaster, "mark_unreachable", unreachable)

    async def send_one(uid):
        if uid % 5 == 0:
            raise TelegramForbiddenError(method=None, message="blocked")
        if uid % 7 == 0:
            raise ValueError("bad markup")

    res = await broadcaster.broadcast(list(range(1, 41)), send_one, rate=0)

    assert res.sent + res.blocked + res.failed == 40
    # 35 is divisible by both; the blocked branch is checked first.
    assert (res.blocked, res.failed) == (8, 4)


async def test_ab_progress_reports_the_whole_run(runner, monkeypatch):
    state, ids = runner

    async def unreachable(uid):
        return None

    monkeypatch.setattr(broadcaster, "mark_unreachable", unreachable)

    async def send_one(uid):
        # Every id divisible by 4 is blocked: hits both halves of the split.
        if uid % 4 == 0:
            raise TelegramForbiddenError(method=None, message="blocked")

    monkeypatch.setattr(br, "build_sender", lambda *a, **kw: send_one)

    await br.run_broadcast(
        object(), admin_id=1, segment="all", text="A", text_b="B", is_ab=True,
    )

    # Progress is a running picture of the run, so each field only grows.
    for prev, cur in zip(state["progress"], state["progress"][1:]):
        for field in ("sent", "blocked", "failed"):
            assert cur[field] >= prev[field], (
                f"{field} went backwards between progress reports: "
                f"{prev[field]} -> {cur[field]}"
            )

    done = state["done"]
    assert done["sent"] + done["blocked"] + done["failed"] == len(ids)
