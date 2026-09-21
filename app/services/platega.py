"""Thin async client over the Platega payment API (httpx).

Flow: create a transaction -> redirect the user to the hosted payment page ->
Platega calls our webhook with the final status. See ``app/web.py`` for the
callback side.

Docs: https://docs.platega.io/ (base ``https://app.platega.io``). Auth is two
headers, ``X-MerchantId`` and ``X-Secret``; the very same headers are sent back
on the webhook, so verifying a callback is a constant-time compare of those.
"""
import hmac
import logging

import httpx

import config

logger = logging.getLogger(__name__)

# paymentMethod codes (PaymentMethodInt in the spec).
METHOD_SBP = 2          # СБП (QR-код)
METHOD_CARD = 11        # Карточный эквайринг

# PaymentStatus enum.
STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"   # success
STATUS_CANCELED = "CANCELED"     # failure
STATUS_CHARGEBACKED = "CHARGEBACKED"

# Callback delivery, per the provider's docs: each attempt gets 60s to answer,
# and a non-2xx is retried up to 3 times at this interval. Anything that has to
# outlive a redelivery (the payment provisioning claim) is sized against it.
CALLBACK_TIMEOUT_SECONDS = 60
CALLBACK_RETRY_SECONDS = 300

_TIMEOUT = httpx.Timeout(20.0)

_client: httpx.AsyncClient | None = None

# Status path this Platega account actually serves, learned on the first
# successful lookup. Reset per process, so a provider that later enables
# the newer API is picked up on the next restart.
_status_path: str | None = None


def _headers() -> dict[str, str]:
    return {
        "X-MerchantId": config.PLATEGA_MERCHANT_ID,
        "X-Secret": config.PLATEGA_SECRET,
    }


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        if not config.PAYMENTS_ENABLED:
            raise RuntimeError("PLATEGA_MERCHANT_ID / PLATEGA_SECRET are not set")
        _client = httpx.AsyncClient(
            base_url=config.PLATEGA_API_URL,
            headers=_headers(),
            timeout=_TIMEOUT,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def create_transaction(
    *,
    method: int | None = None,
    amount_rub: float,
    description: str,
    payload: str | None = None,
    user_id: int | None = None,
    user_name: str | None = None,
) -> dict:
    """Create a transaction (``POST /v2/transaction/process``) and return the
    parsed JSON. Use :func:`pay_url` to get the hosted pay.platega.io page where
    the user pays; ``transactionId`` is what the webhook echoes back.

    ``method`` is optional: **omit it** and the payer picks the method on the
    hosted page ("без заданного метода"); pass one to pin a single method.
    ``user_id`` is sent as ``metadata.userId`` — the docs mark it important for
    antifraud (its absence can get the merchant disabled)."""
    body: dict = {
        "paymentDetails": {"amount": amount_rub, "currency": "RUB"},
        "description": description,
    }
    if method is not None:
        body["paymentMethod"] = method
    if config.PLATEGA_RETURN_URL:
        body["return"] = config.PLATEGA_RETURN_URL
    if config.PLATEGA_FAILED_URL:
        body["failedUrl"] = config.PLATEGA_FAILED_URL
    if payload:
        body["payload"] = payload
    if user_id is not None:
        meta: dict = {"userId": str(user_id)}
        if user_name:
            meta["userName"] = user_name
        body["metadata"] = meta

    resp = await _get_client().post("/v2/transaction/process", json=body)
    resp.raise_for_status()
    return resp.json()


def pay_url(txn: dict) -> str | None:
    """The hosted payment URL from a create response. v2 returns ``url``; older
    responses used ``redirect`` — accept either."""
    return txn.get("url") or txn.get("redirect")


async def get_status(transaction_id: str) -> str | None:
    """Current status of a transaction, or None if not found.

    The reconcile safety-net depends on this, so try the v2 status path first
    (we create via /v2/transaction/process) and fall back to the legacy path —
    a wrong endpoint here would silently break missed-webhook recovery. The
    status may sit at the top level or under ``response``."""
    global _status_path
    client = _get_client()
    templates = ("/v2/transaction/{}", "/transaction/{}")
    if _status_path is not None:
        # Learned below: the other one 404s on every poll, and reconcile polls
        # a pending payment once a minute for hours.
        templates = (_status_path,) + tuple(t for t in templates if t != _status_path)
    for template in templates:
        resp = await client.get(template.format(transaction_id))
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data.get("response"), dict):
            data = data["response"]
        status = data.get("status")
        if status is not None:
            _status_path = template
            return status
    return None


def verify_callback(merchant_id: str | None, secret: str | None) -> bool:
    """Constant-time check that a webhook carries our own credentials."""
    if not merchant_id or not secret:
        return False
    return hmac.compare_digest(merchant_id, config.PLATEGA_MERCHANT_ID) and hmac.compare_digest(
        secret, config.PLATEGA_SECRET
    )
