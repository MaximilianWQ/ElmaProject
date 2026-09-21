"""Rate-limited fan-out for admin broadcasts.

Telegram throttles bulk sends to ~30 messages/second to *different* users before
it starts returning 429 / ``RetryAfter``. We pace strictly below that
(``BROADCAST_RATE``) and cap the number of in-flight requests
(``BROADCAST_CONCURRENCY``), so a 50k broadcast drips out steadily (~33 min at
25/s) instead of bursting. Everything is cooperative ``await`` + ``asyncio.sleep``,
so the bot keeps handling webhooks and scheduler loops while it runs.

Failure handling per recipient:
  * ``RetryAfter``        -> globally back off for the requested seconds, retry once
  * ``Forbidden``         -> user blocked the bot: mark unreachable, count separately
  * anything else         -> log + count as failed (one bad user never aborts the run)
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

import config
from database import mark_unreachable

logger = logging.getLogger(__name__)

# How many times one recipient is attempted while Telegram keeps answering 429.
RETRY_ATTEMPTS = 3


@dataclass
class BroadcastResult:
    sent: int = 0
    failed: int = 0
    blocked: int = 0  # users who have blocked the bot

    @property
    def processed(self) -> int:
        return self.sent + self.failed + self.blocked


async def broadcast(
    user_ids: list[int],
    send_one: Callable[[int], Awaitable[None]],
    *,
    rate: int = config.BROADCAST_RATE,
    concurrency: int = config.BROADCAST_CONCURRENCY,
    progress: Callable[[BroadcastResult], Awaitable[None]] | None = None,
    progress_every: int = 5000,
) -> BroadcastResult:
    """Send to every id in ``user_ids`` via ``send_one(uid)``, paced to ``rate``
    messages/second with at most ``concurrency`` in-flight.

    ``progress`` (if given) is awaited roughly ten times per run: the step is a
    tenth of the audience, floored at 100 and capped at ``progress_every``. A
    fixed constant cannot work for both ends — 5000 meant a 1000-user broadcast
    reported *nothing at all*, while a small constant would spam the admin (each
    report is a Telegram message) on a 50k run.
    """
    res = BroadcastResult()
    total = len(user_ids)
    step = max(100, min(progress_every, total // 10)) if progress else 0
    sem = asyncio.Semaphore(concurrency)
    interval = 1.0 / rate if rate > 0 else 0.0
    next_slot = time.monotonic()
    pause_until = 0.0  # global backoff deadline set on RetryAfter
    tasks: list[asyncio.Task] = []

    async def _send(uid: int) -> None:
        nonlocal pause_until
        try:
            # 429 is Telegram asking us to slow down, not a delivery failure —
            # retrying once was not enough, because during a large run the whole
            # fan-out is being throttled and the retry is very likely throttled
            # too. Honour the server-provided delay for a few attempts before
            # writing the recipient off.
            for attempt in range(1, RETRY_ATTEMPTS + 1):
                try:
                    await send_one(uid)
                    res.sent += 1
                    return
                except TelegramRetryAfter as exc:
                    pause_until = max(pause_until, time.monotonic() + exc.retry_after)
                    logger.warning(
                        "Broadcast hit RetryAfter %.0fs (attempt %d/%d)",
                        exc.retry_after, attempt, RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(exc.retry_after)
            res.failed += 1
            logger.warning(
                "Broadcast gave up on %s after %d throttled attempts",
                uid, RETRY_ATTEMPTS,
            )
        except TelegramForbiddenError:
            res.blocked += 1
            await mark_unreachable(uid)
        except Exception:  # noqa: BLE001 - one bad recipient must not abort the run
            logger.exception("Broadcast send failed for %s", uid)
            res.failed += 1
        finally:
            sem.release()

    for idx, uid in enumerate(user_ids, 1):
        await sem.acquire()  # cap in-flight (also throttles us if Telegram is slow)
        # Respect any global RetryAfter backoff in progress.
        now = time.monotonic()
        if now < pause_until:
            await asyncio.sleep(pause_until - now)
        # Pace to the target rate.
        now = time.monotonic()
        if now < next_slot:
            await asyncio.sleep(next_slot - now)
        next_slot = max(next_slot + interval, time.monotonic())

        tasks.append(asyncio.create_task(_send(uid)))
        if progress and step and idx % step == 0:
            await progress(res)

    await asyncio.gather(*tasks, return_exceptions=True)
    return res
