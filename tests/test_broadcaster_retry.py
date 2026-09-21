"""Flood control must not eat recipients.

Telegram answers a bulk run with 429/``TelegramRetryAfter`` when it wants the
sender to slow down — that is throttling, not a delivery failure. The run used to
retry a recipient exactly once; a second 429 (entirely normal once the whole run
is backing off) dropped that user into ``failed`` and they never got the message.
"""
from aiogram.exceptions import TelegramRetryAfter

from app.services import broadcaster


def _flaky(fail_times: int):
    """A sender that is throttled ``fail_times`` times, then succeeds."""
    state = {"left": fail_times, "attempts": 0}

    async def send_one(uid):
        state["attempts"] += 1
        if state["left"] > 0:
            state["left"] -= 1
            raise TelegramRetryAfter(method=None, message="flood", retry_after=0)

    return send_one, state


async def test_recipient_throttled_twice_is_still_delivered():
    send_one, state = _flaky(2)
    res = await broadcaster.broadcast([1], send_one, rate=0)

    assert (res.sent, res.failed) == (1, 0), "429 is backpressure, not a failure"
    assert state["attempts"] == 3


async def test_gives_up_after_the_retry_budget():
    send_one, _ = _flaky(99)
    res = await broadcaster.broadcast([1], send_one, rate=0)

    assert (res.sent, res.failed) == (0, 1), "a permanently throttled user fails once"


async def test_a_real_error_is_not_retried_as_throttling():
    attempts = {"n": 0}

    async def send_one(uid):
        attempts["n"] += 1
        raise ValueError("bad markup")

    res = await broadcaster.broadcast([1], send_one, rate=0)

    assert (res.sent, res.failed) == (0, 1)
    assert attempts["n"] == 1, "only 429 earns a retry"
