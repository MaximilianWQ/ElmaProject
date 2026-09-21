"""A settled payment must reach the dashboard's live event stream.

The bus only ever carried admin actions, broadcasts and the bypass backfill, so
the dashboard could not show payments as they happen — its socket had nothing to
deliver (``lib/ws.ts`` even invalidated on a ``payment*`` type the backend never
emitted). Publishing here, in the shared finalizer, covers both routes a real
payment can arrive by: the provider webhook and the reconcile poller.
"""
import pytest

from app.events import bus
from app.services import billing


@pytest.fixture
def published(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(bus, "publish", lambda e: events.append(e))

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(billing, "complete_purchase", noop)
    monkeypatch.setattr(billing, "_delete_confirm_screen", noop)
    monkeypatch.setattr(billing, "notify_purchase_activated", noop)

    from app.services import push_service

    monkeypatch.setattr(push_service, "check_revenue_milestones", noop)
    return events


def _payment(**over) -> dict:
    row = {
        "invoice_id": "txn-1",
        "telegram_id": 42,
        "amount_kopecks": 19900,
        "provider": "platega",
        "tariff_code": "1m",
        "confirm_message_id": None,
    }
    row.update(over)
    return row


async def test_a_settled_subscription_payment_is_published(published):
    await billing.finalize_confirmed_payment(object(), _payment())

    paid = [e for e in published if e.get("type") == "payment:confirmed"]
    assert paid, "the dashboard has no other way to learn a payment landed"
    assert paid[0]["telegram_id"] == 42
    assert paid[0]["amount_kopecks"] == 19900
    assert paid[0]["provider"] == "platega"
    assert paid[0]["tariff_code"] == "1m"


async def test_a_traffic_pack_purchase_is_published_too(published, monkeypatch):
    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(billing, "complete_traffic_purchase", noop)

    await billing.finalize_confirmed_payment(object(), _payment(tariff_code="tr_50"))

    paid = [e for e in published if e.get("type") == "payment:confirmed"]
    assert paid and paid[0]["tariff_code"] == "tr_50"


async def test_nothing_is_published_when_provisioning_fails(published, monkeypatch):
    """The event means "served", so it must not fire on a failed finalize."""
    async def boom(*a, **kw):
        raise RuntimeError("panel down")

    monkeypatch.setattr(billing, "complete_purchase", boom)

    with pytest.raises(RuntimeError):
        await billing.finalize_confirmed_payment(object(), _payment())

    assert [e for e in published if e.get("type") == "payment:confirmed"] == []
