"""Platega webhook: a CONFIRMED payment is served exactly once, and never
becomes unrecoverable when provisioning fails.

Two production rules are pinned here:

1. Provisioning failed -> the payment must stay a *reconcile candidate* (the
   poller only looks at ``status = 'pending'``). Marking it ``failed`` would
   hide a genuinely paid transaction from the safety net for good.
2. Two concurrent deliveries (provider retry racing the reconcile poller) must
   provision ONCE — otherwise one payment grants two subscription periods.

The fake below mirrors the SQL semantics of the payments table, so the
assertions are about resulting row state, not about which mock was called.
"""
import asyncio

import pytest

from app import web
from app.services import platega
from database.subscriptions import CLAIMABLE_STATUSES, PAYMENT_CLAIM_LEASE_SECONDS


def test_claim_lease_outlives_the_provider_retry_interval():
    """Platega re-delivers a callback up to 3 times, 5 minutes apart, and gives
    each delivery 60s to answer. If the claim lease is not comfortably longer
    than that interval, a retry lands just as the lease expires and claims a
    payment whose first attempt is still inside the panel — exactly the double
    provisioning the claim exists to prevent."""
    from app.services.platega import CALLBACK_RETRY_SECONDS
    from database.subscriptions import PAYMENT_CLAIM_LEASE_SECONDS

    assert PAYMENT_CLAIM_LEASE_SECONDS > CALLBACK_RETRY_SECONDS


class FakePayments:
    """In-memory stand-in with the same semantics as the payments SQL."""

    # Mirrors the real lease so the fake cannot drift from production.
    LEASE = float(PAYMENT_CLAIM_LEASE_SECONDS)

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.now = 1000.0

    def add_pending(self, invoice_id: str, telegram_id: int = 42):
        self.rows[invoice_id] = {
            "invoice_id": invoice_id,
            "telegram_id": telegram_id,
            "amount_kopecks": 19900,
            "provider": "platega",
            "tariff_code": "1m",
            "status": "pending",
            "fail_reason": None,
            "processing_at": None,
            "confirm_message_id": None,
        }

    # --- the functions app.web calls ---------------------------------------

    async def claim_payment_for_processing(self, invoice_id: str):
        # Mirrors the real SQL, including which statuses may be claimed.
        row = self.rows.get(invoice_id)
        if row is None or row["status"] not in CLAIMABLE_STATUSES:
            return None
        held = row["processing_at"]
        if held is not None and self.now - held < self.LEASE:
            return None  # another worker holds a live lease
        row["processing_at"] = self.now
        row["status"] = "pending"
        return dict(row)

    async def release_payment_claim(self, invoice_id: str, reason=None):
        row = self.rows.get(invoice_id)
        if row is not None and row["status"] == "pending":
            row["processing_at"] = None
            if reason:
                row["fail_reason"] = reason

    async def get_payment(self, invoice_id: str):
        row = self.rows.get(invoice_id)
        return dict(row) if row else None

    async def is_payment_paid(self, invoice_id: str) -> bool:
        return self.rows.get(invoice_id, {}).get("status") == "paid"

    async def mark_payment_failed(self, invoice_id: str, reason: str):
        row = self.rows.get(invoice_id)
        if row is not None and row["status"] != "paid":
            row["status"] = "failed"
            row["fail_reason"] = reason

    def mark_paid(self, invoice_id: str):
        self.rows[invoice_id]["status"] = "paid"

    # --- what the reconcile poller would see -------------------------------

    def reconcile_candidates(self) -> list[str]:
        """Mirrors pending_payments_recent: status = 'pending' only."""
        return [i for i, r in self.rows.items() if r["status"] == "pending"]


class FakeRequest:
    def __init__(self, payload, app):
        self.headers = {"X-MerchantId": "m", "X-Secret": "s"}
        self._payload = payload
        self.app = app
        self.remote = "203.0.113.7"

    async def json(self):
        return self._payload


@pytest.fixture
def wired(monkeypatch):
    fake = FakePayments()
    for name in (
        "claim_payment_for_processing",
        "release_payment_claim",
        "get_payment",
        "is_payment_paid",
        "mark_payment_failed",
    ):
        monkeypatch.setattr(web, name, getattr(fake, name), raising=False)
    monkeypatch.setattr(platega, "verify_callback", lambda m, s: True)
    return fake


def _confirmed(txn: str) -> dict:
    return {"id": txn, "status": platega.STATUS_CONFIRMED}


async def test_failed_provisioning_leaves_payment_for_the_reconciler(wired, monkeypatch):
    """Panel down while the money is already taken: the row must remain a
    reconcile candidate so the poller can finish the job later."""
    wired.add_pending("txn-1")

    async def boom(bot, payment):
        raise RuntimeError("remnawave unreachable")

    monkeypatch.setattr(web.billing, "finalize_confirmed_payment", boom)

    resp = await web._platega_webhook(FakeRequest(_confirmed("txn-1"), {"bot": object()}))

    assert resp.status == 500, "non-2xx so the provider retries"
    assert wired.rows["txn-1"]["status"] == "pending", (
        "a CONFIRMED payment must never be marked 'failed' — that removes it "
        "from pending_payments_recent and strands a paying user forever"
    )
    assert "txn-1" in wired.reconcile_candidates()
    assert wired.rows["txn-1"]["processing_at"] is None, "claim released for retry"


async def test_concurrent_deliveries_provision_once(wired, monkeypatch):
    """Provider retry racing the reconcile poller must not grant two periods."""
    wired.add_pending("txn-2")
    started = asyncio.Event()
    finalize_calls = []

    async def slow_finalize(bot, payment):
        finalize_calls.append(payment["invoice_id"])
        started.set()
        await asyncio.sleep(0.05)  # still in flight when the retry lands
        wired.mark_paid(payment["invoice_id"])

    monkeypatch.setattr(web.billing, "finalize_confirmed_payment", slow_finalize)

    app = {"bot": object()}
    first = asyncio.create_task(web._platega_webhook(FakeRequest(_confirmed("txn-2"), app)))
    await started.wait()
    second = await web._platega_webhook(FakeRequest(_confirmed("txn-2"), app))
    await first

    assert finalize_calls == ["txn-2"], (
        "the second delivery must be rejected by the claim while the first is "
        "still provisioning"
    )
    assert second.status == 200
    assert wired.rows["txn-2"]["status"] == "paid"


async def test_unknown_transaction_is_still_reported(wired, monkeypatch):
    """A CONFIRMED txn we never journaled must not be silently acked as a dupe."""
    async def never(bot, payment):
        raise AssertionError("must not provision an unknown txn")

    monkeypatch.setattr(web.billing, "finalize_confirmed_payment", never)

    resp = await web._platega_webhook(FakeRequest(_confirmed("ghost"), {"bot": object()}))
    assert resp.status == 200
    assert "unknown" in resp.text.lower()


async def test_a_cancelled_payment_is_served_when_it_later_confirms(wired, monkeypatch):
    """Providers deliver out of order and users retry on the same transaction.
    A CANCELED that lands before the CONFIRMED must not lock the user out of
    access they then paid for."""
    wired.add_pending("txn-7")
    await wired.mark_payment_failed("txn-7", "Платёж отменён (CANCELED)")
    assert wired.rows["txn-7"]["status"] == "failed"

    finalized = []

    async def finalize(bot, payment):
        finalized.append(payment["invoice_id"])
        wired.mark_paid(payment["invoice_id"])

    monkeypatch.setattr(web.billing, "finalize_confirmed_payment", finalize)

    resp = await web._platega_webhook(FakeRequest(_confirmed("txn-7"), {"bot": object()}))

    assert finalized == ["txn-7"], "a later CONFIRMED overrides an earlier CANCELED"
    assert resp.status == 200
    assert wired.rows["txn-7"]["status"] == "paid"


async def test_a_refunded_payment_is_never_reclaimed(wired, monkeypatch):
    """Money already returned — a stray CONFIRMED must not grant access again."""
    wired.add_pending("txn-8")
    wired.rows["txn-8"]["status"] = "refunded"

    async def never(bot, payment):
        raise AssertionError("must not provision a refunded payment")

    monkeypatch.setattr(web.billing, "finalize_confirmed_payment", never)

    resp = await web._platega_webhook(FakeRequest(_confirmed("txn-8"), {"bot": object()}))
    assert resp.status == 200
    assert wired.rows["txn-8"]["status"] == "refunded"


# --- the reconcile poller shares the same claim ----------------------------


@pytest.fixture
def wired_reconcile(wired, monkeypatch):
    """Point the reconcile loop at the same fake payments table."""
    from app.services import notifications

    for name in ("claim_payment_for_processing", "release_payment_claim", "is_payment_paid"):
        monkeypatch.setattr(notifications, name, getattr(wired, name), raising=False)

    async def rows(min_age, max_age):
        return [dict(wired.rows[i]) for i in wired.reconcile_candidates()]

    monkeypatch.setattr(notifications, "pending_payments_recent", rows)

    async def confirmed(txn):
        return platega.STATUS_CONFIRMED

    monkeypatch.setattr(notifications.platega, "get_status", confirmed)
    return notifications


async def test_reconcile_skips_a_payment_the_webhook_is_provisioning(
    wired, wired_reconcile, monkeypatch
):
    """The poller runs every 60s while a webhook delivery may still be in the
    panel. Without a shared claim both would provision the same payment."""
    wired.add_pending("txn-4")
    await wired.claim_payment_for_processing("txn-4")  # webhook holds it

    finalize_calls = []

    async def finalize(bot, payment):
        finalize_calls.append(payment["invoice_id"])

    monkeypatch.setattr(wired_reconcile.billing, "finalize_confirmed_payment", finalize)

    await wired_reconcile._reconcile_payments(object())

    assert finalize_calls == [], "a live claim must keep the poller out"


async def test_reconcile_finalizes_a_payment_the_webhook_never_settled(
    wired, wired_reconcile, monkeypatch
):
    """The whole point of the safety net: an unclaimed pending payment that the
    provider confirmed does get provisioned."""
    wired.add_pending("txn-5")
    finalize_calls = []

    async def finalize(bot, payment):
        finalize_calls.append(payment["invoice_id"])
        wired.mark_paid(payment["invoice_id"])

    monkeypatch.setattr(wired_reconcile.billing, "finalize_confirmed_payment", finalize)

    await wired_reconcile._reconcile_payments(object())

    assert finalize_calls == ["txn-5"]
    assert wired.rows["txn-5"]["status"] == "paid"


async def test_reconcile_releases_its_claim_when_provisioning_fails(
    wired, wired_reconcile, monkeypatch
):
    """A failed reconcile attempt must not park the payment until the lease
    expires — the next tick should be able to retry immediately."""
    wired.add_pending("txn-6")

    async def boom(bot, payment):
        raise RuntimeError("panel down")

    monkeypatch.setattr(wired_reconcile.billing, "finalize_confirmed_payment", boom)

    await wired_reconcile._reconcile_payments(object())

    assert wired.rows["txn-6"]["status"] == "pending"
    assert wired.rows["txn-6"]["processing_at"] is None, "claim handed back"
