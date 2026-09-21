"""Thin async client over the Remnawave panel REST API (httpx), **v3.x**.

Four user operations plus a squad helper. Auth is a Bearer token.

Remnawave 3.x breaking changes handled here:
- users are identified by a numeric ``id`` (the ``uuid`` field is gone). PATCH
  carries ``{"id": <int>, ...}`` in the body; DELETE is ``/api/users/{id}``.
- our stored ``panel_uuid`` column now holds that numeric id (as a string); a
  legacy (non-numeric) value yields ``None`` from :func:`_as_id`, so the caller
  re-adopts the record by ``username`` (still supported) and heals itself.
- squad membership uses ``userIds`` (numbers), not ``userUuids``.
- DELETE returns 204 (no body); ``404`` is normalised to ``None``.

No webhooks panel->bot: the bot always drives the panel.
"""
import asyncio
import logging

import httpx

import config

logger = logging.getLogger(__name__)

_BASE = config.REMNAWAVE_URL.rstrip("/")
_TIMEOUT = httpx.Timeout(15.0)
_RETRIES = 3
_RETRY_BACKOFF = 0.5  # seconds, doubled each attempt

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Lazily create a shared client bound to the running event loop."""
    global _client
    if _client is None or _client.is_closed:
        if not _BASE or not config.REMNAWAVE_TOKEN:
            raise RuntimeError("REMNAWAVE_URL / REMNAWAVE_TOKEN are not configured")
        _client = httpx.AsyncClient(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {config.REMNAWAVE_TOKEN}"},
            timeout=_TIMEOUT,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def _req(method: str, path: str, **kwargs) -> dict | None:
    """One request with light retries on transient transport / 5xx errors.

    Returns the parsed JSON, or ``None`` for ``404``. Raises
    ``httpx.HTTPStatusError`` for other non-2xx responses (e.g. 409 conflict),
    so the caller can branch on the status code.
    """
    client = _get_client()
    delay = _RETRY_BACKOFF
    last_exc: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = await client.request(method, path, **kwargs)
        except httpx.TransportError as exc:  # connect/read/timeout
            last_exc = exc
            logger.warning(
                "Remnawave %s %s transport error (attempt %d/%d): %s",
                method, path, attempt, _RETRIES, exc,
            )
        else:
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500 and attempt < _RETRIES:
                logger.warning(
                    "Remnawave %s %s -> %d (attempt %d/%d), retrying",
                    method, path, resp.status_code, attempt, _RETRIES,
                )
            else:
                if resp.status_code >= 400:
                    # Log the panel's actual error body so validation failures
                    # (400/422) are diagnosable instead of a bare status code.
                    logger.error(
                        "Remnawave %s %s -> %d: %s",
                        method, path, resp.status_code, resp.text[:800],
                    )
                resp.raise_for_status()
                if resp.content:
                    return _unwrap(resp.json())
                return {}
        if attempt < _RETRIES:
            await asyncio.sleep(delay)
            delay *= 2
    assert last_exc is not None
    raise last_exc


# Panel error code for "this username is taken" (ERRORS.USER_USERNAME_ALREADY_EXISTS
# in the 3.x source). It is returned with **HTTP 400**, not 409 — the whole point
# of the helper below.
USERNAME_CONFLICT_CODE = "A019"
_USERNAME_TAKEN = "username already exists"


def is_username_conflict(exc: httpx.HTTPStatusError) -> bool:
    """True when the panel refused a create because the username is taken.

    3.x answers a duplicate username with ``400`` + ``errorCode: "A019"``
    (``HttpExceptionFilter`` emits ``{timestamp, path, message, errorCode}``),
    so a plain ``status_code == 409`` check never matches and a lost create race
    surfaces as a hard provisioning failure instead of an adopt.

    Deliberately narrow: a nestjs-zod validation failure is *also* a 400 but goes
    through the filter's other branch and carries no ``errorCode``, so it stays a
    real error rather than being silently swallowed as a conflict. 409 is still
    honoured for older panels.
    """
    response = exc.response
    if response.status_code == 409:
        return True
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 - not JSON, fall through to the raw text
        body = None
    if isinstance(body, dict):
        if body.get("errorCode") == USERNAME_CONFLICT_CODE:
            return True
        message = body.get("message")
        if isinstance(message, str) and _USERNAME_TAKEN in message.lower():
            return True
        return False
    return _USERNAME_TAKEN in (response.text or "").lower()


def _unwrap(payload: dict) -> dict:
    """Remnawave sometimes nests the object under ``{"response": {...}}``."""
    if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
        return payload["response"]
    return payload


# --- User operations -------------------------------------------------------

def _as_id(identifier) -> int | None:
    """Numeric Remnawave 3.x user id, or None for a uuid/None identifier."""
    try:
        return int(identifier)
    except (TypeError, ValueError):
        return None


async def create_user(payload: dict) -> dict:
    """POST /api/users -> 201. The response carries the numeric ``id``."""
    return await _req("POST", "/api/users", json=payload)


async def update_user(identifier, **fields) -> dict | None:
    """PATCH /api/users — 3.x accepts only ``id`` (numeric) or ``username`` to
    identify the user; a ``uuid`` is rejected ("At least one of username, id must
    be provided"). So we PATCH by numeric ``id``; a legacy (non-numeric) stored
    identifier returns ``None`` so the caller re-adopts by username and heals the
    row to the numeric id. ``None`` also on 404."""
    uid = _as_id(identifier)
    if uid is None:
        return None
    return await _req("PATCH", "/api/users", json={"id": uid, **fields})


async def find_user_by_username(username: str) -> dict | None:
    """GET /api/users/by-username/{username} — still supported in 3.x (unlike
    by-telegram-id / by-email / by-tag / by-id). Returns the object with the
    numeric ``id``, or ``None`` on 404."""
    return await _req("GET", f"/api/users/by-username/{username}")


async def find_user_by_telegram_id(
    telegram_id: int, *, username: str | None = None
) -> dict | None:
    """GET /api/users/stream?telegramId= — the 3.x-guaranteed lookup (the old
    /by-telegram-id was removed).

    A user can have several entities under one telegramId (premium ``elma_<id>``
    AND bypass ``elma_bp_<id>``), so pass ``username`` to pick the right one —
    never adopt/patch the wrong entity."""
    res = await _req(
        "GET", "/api/users/stream", params={"telegramId": telegram_id, "size": 10}
    )
    users = (res or {}).get("users") or []
    if username is not None:
        users = [u for u in users if u.get("username") == username]
    return users[0] if users else None


async def iter_users(*, size: int = 1000, max_pages: int = 200):
    """Yield pages of panel users via ``GET /api/users/stream``.

    3.x keyset pagination: pass back ``nextCursor`` until ``hasMore`` is false.
    ``size`` is capped at 1000 by the contract. Lets a caller read the whole
    population in ``ceil(N/1000)`` requests instead of one request per user;
    ``max_pages`` is a safety stop so a misbehaving cursor can't loop forever.
    """
    cursor = None
    for _ in range(max_pages):
        params: dict = {"size": min(size, 1000)}
        if cursor is not None:
            params["cursor"] = cursor
        res = await _req("GET", "/api/users/stream", params=params) or {}
        users = res.get("users") or []
        if users:
            yield users
        cursor = res.get("nextCursor")
        if not res.get("hasMore") or not users or cursor is None:
            return
    logger.warning("iter_users hit the %d-page safety stop", max_pages)


async def delete_user(identifier) -> None:
    """DELETE /api/users/{identifier} — the path is the id (3.x) or uuid (older),
    so the raw value works either way. 204/404 both mean 'gone'."""
    if not identifier:
        return
    await _req("DELETE", f"/api/users/{identifier}")


async def add_users_to_squad(squad_uuid: str, user_ids: list) -> dict | None:
    """Attach specific users to an internal squad — the safety net for a freshly
    created user whose ``activeInternalSquads`` came back empty (§10.4).

    Route per the 3.x contract (``INTERNAL_SQUADS_ROUTES.BULK_ACTIONS``):
    ``POST /api/internal-squads/{uuid}/bulk-actions/add-many-users`` with body
    ``{"userIds": [<numbers>]}``. Note the neighbouring ``add-users`` route adds
    **every** user in the panel to the squad — never use it here.

    Users are identified by numeric id only in 3.x, so a legacy uuid identifier
    is dropped rather than sent in a request that cannot succeed.
    """
    ids = [i for i in (_as_id(u) for u in user_ids) if i is not None]
    if not ids:
        logger.warning(
            "add_users_to_squad(%s): no numeric user ids in %r — nothing to do",
            squad_uuid, user_ids,
        )
        return None
    return await _req(
        "POST",
        f"/api/internal-squads/{squad_uuid}/bulk-actions/add-many-users",
        json={"userIds": ids[:1000]},  # contract caps the batch at 1000
    )
