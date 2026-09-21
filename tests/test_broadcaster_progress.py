"""Broadcast progress must scale with the audience, not with a fixed constant.

The old cadence was "every 5000 dispatched messages", so a real audience (a few
hundred to a few thousand users) produced **zero** progress reports — neither the
admin in Telegram nor the dashboard event stream saw anything until the run had
finished. Progress is now a share of the audience, so every run reports roughly
the same number of times whatever its size.
"""
from app.services import broadcaster


async def _run(total: int, **kw) -> list[int]:
    """Run a broadcast over ``total`` fake recipients; return the sent-counts
    handed to the progress callback."""
    seen: list[int] = []

    async def send_one(uid):
        pass

    async def progress(res):
        seen.append(res.sent)

    await broadcaster.broadcast(
        list(range(total)), send_one, rate=0, concurrency=64, progress=progress, **kw
    )
    return seen


async def test_reports_progress_for_a_thousand_recipients():
    """The size that used to report nothing at all."""
    seen = await _run(1000)
    assert len(seen) >= 5, f"a 1000-user run reported {len(seen)} times"


async def test_reports_progress_for_a_few_hundred_recipients():
    seen = await _run(300)
    assert len(seen) >= 2, f"a 300-user run reported {len(seen)} times"


async def test_large_run_does_not_spam_the_admin():
    """Progress goes to a Telegram message per call, so the count must stay
    bounded as the audience grows."""
    seen = await _run(50_000)
    assert len(seen) <= 20, f"a 50k run reported {len(seen)} times"


async def test_progress_counts_only_move_forward():
    seen = await _run(2000)
    assert seen == sorted(seen)
    assert seen[-1] <= 2000


async def test_tiny_run_is_left_to_the_final_summary():
    """A handful of recipients finishes in about a second; intermediate updates
    would be pure noise there."""
    assert await _run(20) == []
