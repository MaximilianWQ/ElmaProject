"""A taken username must be recognised as a conflict, not as a failure.

Remnawave 3.x answers a duplicate username with **HTTP 400 + errorCode A019**,
not 409 (verified in the panel source: ``ERRORS.USER_USERNAME_ALREADY_EXISTS =
{code: 'A019', httpCode: 400}``, serialised by ``HttpExceptionFilter`` as
``{message, errorCode, path, timestamp}``). The adopt-on-race branch tested for
409, so it never ran: when an entity appeared between the preflight lookup and
the POST, provisioning raised instead of taking the entity over — a paid user
got "не удалось выдать доступ".

The check has to stay narrow. A Zod validation error is also a 400, but it takes
the filter's other branch and carries no ``errorCode``, so it must keep raising —
swallowing those would hide real payload bugs behind a silent adopt.
"""
import httpx
import pytest

from app.services import bypass_service, remnawave, subscription_service


def _error(status: int, body=None, text: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://panel.example/api/users")
    if text is not None:
        response = httpx.Response(status, text=text, request=request)
    else:
        response = httpx.Response(status, json=body, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def _a019(status: int = 400) -> httpx.HTTPStatusError:
    return _error(status, {
        "timestamp": "2026-09-21T10:00:00.000Z",
        "path": "/api/users",
        "message": "User username already exists",
        "errorCode": "A019",
    })


# --- recognising the conflict ---------------------------------------------


def test_400_with_a019_is_a_username_conflict():
    assert remnawave.is_username_conflict(_a019()) is True


def test_409_still_counts_for_older_panels():
    assert remnawave.is_username_conflict(_error(409, {"message": "conflict"})) is True


def test_a_validation_400_is_not_a_conflict():
    """nestjs-zod renders its own body — no errorCode field at all."""
    zod = _error(400, {
        "statusCode": 400,
        "message": "Validation failed",
        "errors": [{"path": ["expireAt"], "message": "Expiration date cannot be in the past"}],
    })
    assert remnawave.is_username_conflict(zod) is False


def test_another_domain_error_is_not_a_conflict():
    other = _error(400, {"message": "Short uuid already exists", "errorCode": "A020"})
    assert remnawave.is_username_conflict(other) is False


def test_server_error_is_not_a_conflict():
    assert remnawave.is_username_conflict(_error(500, {"message": "Server error"})) is False


def test_non_json_body_falls_back_to_the_message():
    assert remnawave.is_username_conflict(
        _error(400, text="User username already exists")
    ) is True


# --- premium: the conflict is adopted, not raised --------------------------


@pytest.fixture
def panel(monkeypatch):
    state = {"adopted": None, "patched": None}
    entity = {"id": 77, "username": "elma_5", "subscriptionUrl": "https://panel/s/5"}

    async def no_subscription(tg):
        return None

    async def not_found_on_preflight(username):
        return None

    async def create_raises(payload):
        raise _a019()

    async def update_user(identifier, **fields):
        state["patched"] = (identifier, fields)
        return entity

    async def persist(telegram_id, expire_at, source, *panel_dicts, db_sub):
        state["adopted"] = telegram_id
        return {"telegram_id": telegram_id}

    monkeypatch.setattr(subscription_service, "get_subscription", no_subscription)
    monkeypatch.setattr(remnawave, "find_user_by_username", not_found_on_preflight)
    monkeypatch.setattr(remnawave, "find_user_by_telegram_id",
                        lambda tg, username=None: _none())
    monkeypatch.setattr(remnawave, "create_user", create_raises)
    monkeypatch.setattr(remnawave, "update_user", update_user)
    monkeypatch.setattr(subscription_service, "_persist", persist)
    state["entity"] = entity
    return state


async def _none():
    return None


async def test_premium_create_conflict_adopts_the_existing_entity(panel, monkeypatch):
    from datetime import datetime, timedelta, timezone

    found = panel["entity"]

    async def found_after_conflict(username):
        return found

    # Preflight misses, the POST then loses the race, the re-lookup finds it.
    calls = {"n": 0}

    async def lookup(username):
        calls["n"] += 1
        return None if calls["n"] == 1 else found

    monkeypatch.setattr(remnawave, "find_user_by_username", lookup)

    expire = datetime.now(timezone.utc) + timedelta(days=30)
    await subscription_service.create_or_renew(5, expire, source="payment")

    assert panel["adopted"] == 5, "a lost race must adopt, not fail the purchase"
    assert panel["patched"] is not None, "the adopted entity gets its expiry patched"


async def test_premium_validation_error_still_raises(panel, monkeypatch):
    from datetime import datetime, timedelta, timezone

    async def create_invalid(payload):
        raise _error(400, {"statusCode": 400, "message": "Validation failed"})

    monkeypatch.setattr(remnawave, "create_user", create_invalid)

    expire = datetime.now(timezone.utc) + timedelta(days=30)
    with pytest.raises(httpx.HTTPStatusError):
        await subscription_service.create_or_renew(5, expire, source="payment")


# --- bypass has the identical race ----------------------------------------


async def test_bypass_create_conflict_adopts_the_existing_entity(monkeypatch):
    entity = {"id": 91, "username": "elma_bp_5", "subscriptionUrl": "https://panel/s/bp5",
              "trafficLimitBytes": 0, "activeInternalSquads": []}
    calls = {"n": 0}

    async def lookup(username):
        calls["n"] += 1
        return None if calls["n"] == 1 else entity

    async def create_raises(payload):
        raise _a019()

    async def update_user(identifier, **fields):
        return entity

    monkeypatch.setattr(remnawave, "find_user_by_username", lookup)
    monkeypatch.setattr(remnawave, "create_user", create_raises)
    monkeypatch.setattr(remnawave, "update_user", update_user)
    monkeypatch.setattr(bypass_service, "_ensure_squad", lambda *a, **kw: _none())

    uuid, url = await bypass_service._create_or_adopt(5, 10 * 1024 ** 3)

    assert uuid == "91"
    assert url == "https://panel/s/bp5"
