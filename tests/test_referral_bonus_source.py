"""Referral bonus days must not reclassify the subscription they extend.

``upsert_subscription`` writes ``source = EXCLUDED.source``, so granting the
inviter bonus days with ``source="referral"`` rewrote whatever they had. For a
trial user that flipped ``'trial'`` -> ``'referral'``, and every scheduler query
keys off ``source <> 'trial'``: the user immediately started receiving paid
renewal reminders and the "подписка закончилась" copy for a subscription they
never bought, while dropping out of the trial conversion funnel.
"""
import pytest

from app.services import billing


@pytest.fixture
def referrer(monkeypatch):
    state = {"sub": None, "source": None}

    async def credit_referral(buyer_id):
        return 500  # the inviter

    async def get_subscription(tg):
        return state["sub"]

    async def create_or_renew(tg, expires, source):
        state["source"] = source
        return {"telegram_id": tg}

    async def resolve(key, default):
        return False, default  # message disabled -> keep the test focused

    monkeypatch.setattr(billing, "credit_referral", credit_referral)
    monkeypatch.setattr(billing, "get_subscription", get_subscription)
    monkeypatch.setattr(billing.subscription_service, "create_or_renew", create_or_renew)
    monkeypatch.setattr(billing.auto_msg, "resolve", resolve)
    return state


async def test_a_trial_referrer_stays_a_trial(referrer):
    referrer["sub"] = {"expires_at": None, "source": "trial"}

    await billing._reward_referrer(object(), buyer_id=1)

    assert referrer["source"] == "trial", (
        "a bonus must not turn a trial user into a paying one"
    )


async def test_a_paying_referrer_stays_paid(referrer):
    referrer["sub"] = {"expires_at": None, "source": "payment"}

    await billing._reward_referrer(object(), buyer_id=1)

    assert referrer["source"] == "payment"


async def test_a_referrer_with_no_subscription_gets_the_referral_source(referrer):
    referrer["sub"] = None

    await billing._reward_referrer(object(), buyer_id=1)

    assert referrer["source"] == "referral"
