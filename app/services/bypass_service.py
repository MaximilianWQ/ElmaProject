"""Bypass provisioning — a second Remnawave entity, metered by GB.

Completely separate from premium (``subscription_service``): its own panel user
``<prefix>bp_<id>`` in the bypass squad, ``trafficLimitBytes`` accumulating with
every pack, ``expireAt`` far in the future. Buying bypass never touches the
premium row, and buying premium never touches this one.
"""
import logging
from datetime import timedelta

import httpx

import config
from database import (
    clear_bypass_panel,
    get_bypass,
    set_bypass_meta,
    upsert_bypass,
    utcnow,
)

from . import aggregator, remnawave

logger = logging.getLogger(__name__)

_DESCRIPTION = "Elma bypass (traffic)"


def _iso_z(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _far_future() -> str:
    return _iso_z(utcnow() + timedelta(days=config.BYPASS_EXPIRE_DAYS))


def _extract(data: dict | None) -> dict:
    data = data or {}
    # Remnawave 3.x: numeric ``id`` (stringified); ``uuid`` is a legacy fallback.
    pid = data.get("id") or data.get("uuid") or data.get("userUuid")
    # Consumption moved into a nested block in 3.x: the user object carries
    # `trafficLimitBytes` at the top level but `usedTrafficBytes` only inside
    # `userTraffic` (contract: ExtendedUsersSchema + UserTrafficSchema). Reading
    # it off the top level silently yields 0 — which disables every low-traffic
    # warning and zeroes the client's traffic bar. Keep the flat key as a
    # fallback for older panels.
    traffic = data.get("userTraffic") or {}
    used = (
        traffic.get("usedTrafficBytes")
        or data.get("usedTrafficBytes")
        or data.get("used_traffic_bytes")
        or 0
    )
    return {
        "uuid": str(pid) if pid is not None else None,
        "url": (
            data.get("subscriptionUrl")
            or data.get("subscription_url")
            or data.get("url")
        ),
        "used": used,
        "limit": data.get("trafficLimitBytes") or data.get("traffic_limit_bytes") or 0,
        "squads": data.get("activeInternalSquads") or [],
    }


# How many pre-tag entities one pass may heal. Each costs a lookup plus a
# PATCH, so while a backlog drains a pass is dearer than the single filtered
# read it settles at; keep the burst to a few times the old cost, not more.
TAG_HEAL_PER_PASS = 100


def _create_payload(telegram_id: int, limit_bytes: int) -> dict:
    payload = {
        "username": config.build_bypass_username(telegram_id),
        "trafficLimitBytes": int(limit_bytes),
        "trafficLimitStrategy": "NO_RESET",
        "status": "ACTIVE",
        "expireAt": _far_future(),
        "hwidDeviceLimit": config.BYPASS_DEVICE_LIMIT,  # 3.x renamed deviceLimit
        "description": _DESCRIPTION,
        "telegramId": telegram_id,
        "tag": config.BYPASS_TAG,   # lets the monitor filter the shared panel
    }
    if config.REMNAWAVE_BYPASS_SQUAD_UUID:
        payload["activeInternalSquads"] = [config.REMNAWAVE_BYPASS_SQUAD_UUID]
    return payload


async def _ensure_squad(uuid: str | None, squads: list) -> None:
    squad = config.REMNAWAVE_BYPASS_SQUAD_UUID
    if squad and uuid and not squads:
        try:
            await remnawave.add_users_to_squad(squad, [uuid])
        except Exception:  # noqa: BLE001 - non-fatal
            logger.exception("Failed to add bypass %s to squad %s", uuid, squad)


async def _adopt_existing(found: dict, limit_bytes: int) -> tuple[str, str | None] | None:
    """Take over an entity already in the panel; None if it carries no id."""
    e = _extract(found)
    if not e["uuid"]:
        return None
    patched = await remnawave.update_user(
        e["uuid"], trafficLimitBytes=int(limit_bytes),
        status="ACTIVE", expireAt=_far_future(),
    )
    pe = _extract(patched)
    await _ensure_squad(e["uuid"], e["squads"])
    return e["uuid"], pe["url"] or e["url"]


async def _create_or_adopt(telegram_id: int, limit_bytes: int) -> tuple[str, str | None]:
    """Create a fresh bypass entity, or adopt one left in the panel."""
    username = config.build_bypass_username(telegram_id)
    found = await remnawave.find_user_by_username(username)
    if found:
        adopted = await _adopt_existing(found, limit_bytes)
        if adopted:
            return adopted

    try:
        created = _extract(
            await remnawave.create_user(_create_payload(telegram_id, limit_bytes))
        )
    except httpx.HTTPStatusError as exc:
        # Same lost-race as the premium path: the entity appeared between the
        # preflight lookup and the POST. The panel says 400/A019, so re-look it
        # up and adopt instead of failing a paid top-up.
        if not remnawave.is_username_conflict(exc):
            raise
        logger.info("Bypass create conflict for %s; adopting existing entity", telegram_id)
        found = await remnawave.find_user_by_username(username)
        adopted = await _adopt_existing(found, limit_bytes) if found else None
        if adopted:
            return adopted
        raise
    if not created["uuid"]:
        raise RuntimeError(f"Remnawave bypass create returned no uuid for {telegram_id}")
    await _ensure_squad(created["uuid"], created["squads"])
    return created["uuid"], created["url"]


async def ensure_starter_bypass(telegram_id: int) -> bool:
    """Create the user's bypass profile with the starter allowance
    (BYPASS_TRIAL_BONUS_MB), once. Granted to every new subscriber — trial AND
    paid — so a subscription always comes with a bypass profile (the aggregator's
    LTE servers / the «Обход» key). Returns True if it was created. No-op if
    bypass is off, the allowance is 0, or the user already has a bypass entity
    (never stacks, so renewals don't re-grant)."""
    if not config.BYPASS_ENABLED or config.BYPASS_TRIAL_BONUS_MB <= 0:
        return False
    row = await get_bypass(telegram_id)
    if row and row["panel_uuid"]:
        return False  # already has bypass — don't add the bonus again
    bonus_bytes = config.BYPASS_TRIAL_BONUS_MB * 1024 * 1024
    await provision_traffic(telegram_id, bonus_bytes)
    logger.info("Created starter bypass profile (%d MB) for %s",
                config.BYPASS_TRIAL_BONUS_MB, telegram_id)
    return True


# Backwards-compatible alias (older callers / naming).
provision_trial_bonus = ensure_starter_bypass


async def provision_traffic(telegram_id: int, extra_bytes: int) -> int:
    """Add bypass traffic (see :func:`_provision_traffic`) and drop the cached
    aggregated body so the user's next client refresh shows the new limit live."""
    new_limit = await _provision_traffic(telegram_id, extra_bytes)
    await aggregator.invalidate(telegram_id)
    return new_limit


async def _provision_traffic(telegram_id: int, extra_bytes: int) -> int:
    """Add ``extra_bytes`` to the user's bypass entity (creating it if needed).
    Returns the new total limit in bytes. Panel call first, DB write second.

    Remnawave 3.x ``trafficLimitBytes`` is ABSOLUTE, so the new limit is
    ``current + extra`` — and ``current`` is read LIVE from the panel (not the
    possibly-stale DB cache), so a top-up never assigns the wrong amount."""
    row = await get_bypass(telegram_id)
    if row and row["panel_uuid"]:
        current = await remnawave.find_user_by_username(
            config.build_bypass_username(telegram_id)
        )
        base = int(_extract(current)["limit"]) if current else int(row["traffic_limit_bytes"] or 0)
        new_limit = base + int(extra_bytes)
        patched = await remnawave.update_user(
            row["panel_uuid"], trafficLimitBytes=new_limit, status="ACTIVE"
        )
        if patched is None:
            # 404 — entity gone from the panel; recreate with the new total.
            logger.info("Bypass entity for %s gone (404); recreating", telegram_id)
            await clear_bypass_panel(telegram_id)
            uuid, url = await _create_or_adopt(telegram_id, new_limit)
            await upsert_bypass(
                telegram_id, panel_uuid=uuid, subscription_url=url,
                traffic_limit_bytes=new_limit, reset_notify=True,
            )
            return new_limit
        url = _extract(patched)["url"] or row["subscription_url"]
        await upsert_bypass(
            telegram_id, panel_uuid=row["panel_uuid"], subscription_url=url,
            traffic_limit_bytes=new_limit, reset_notify=True,
        )
        return new_limit

    # First pack — create the entity.
    uuid, url = await _create_or_adopt(telegram_id, int(extra_bytes))
    await upsert_bypass(
        telegram_id, panel_uuid=uuid, subscription_url=url,
        traffic_limit_bytes=int(extra_bytes), reset_notify=True,
    )
    return int(extra_bytes)


async def usage_snapshot(expected: list[str] | None = None) -> dict[str, dict]:
    """Traffic for our bypass entities, read from the panel by tag.

    Returns ``{panel_username: {used, limit, url}}``. The panel is shared, so
    asking for everything meant paging through every other service's users too;
    ``tag`` narrows the read to ours (there is no username filter in the 3.4.3
    contract, so the prefix check stays as a second line of defence).

    ``expected`` is the set of usernames our own database says should be there.
    Entities provisioned before the tag existed carry none and are invisible to
    a tagged read, so each miss is looked up once, measured from that very
    response — no user skips a tick — and tagged for next time. Healing is
    capped per pass so a large backlog cannot burst against the panel.
    """
    prefix = config.BYPASS_USERNAME_PREFIX
    snapshot: dict[str, dict] = {}
    async for page in remnawave.iter_users(tag=config.BYPASS_TAG):
        for user in page:
            username = user.get("username") or ""
            if not username.startswith(prefix):
                continue  # a tag collision with another service on the panel
            e = _extract(user)
            snapshot[username] = {
                "used": int(e["used"]), "limit": int(e["limit"]), "url": e["url"],
            }

    missing = [u for u in (expected or []) if u not in snapshot]
    for username in missing[:TAG_HEAL_PER_PASS]:
        try:
            found = await remnawave.find_user_by_username(username)
        except Exception:  # noqa: BLE001 - one bad row must not blind the pass
            logger.exception("bypass tag heal: lookup failed for %s", username)
            continue
        if not found:
            continue  # deleted from the panel; nothing to measure or tag
        e = _extract(found)
        snapshot[username] = {
            "used": int(e["used"]), "limit": int(e["limit"]), "url": e["url"],
        }
        try:
            await remnawave.update_user(found.get("id"), tag=config.BYPASS_TAG)
        except Exception:  # noqa: BLE001 - already measured; retried next pass
            logger.exception("bypass tag heal: tagging %s failed", username)
    if len(missing) > TAG_HEAL_PER_PASS:
        logger.info(
            "bypass tag backfill: %d entities still untagged", 
            len(missing) - TAG_HEAL_PER_PASS,
        )
    return snapshot


async def get_usage(telegram_id: int) -> dict | None:
    """Live bypass usage: ``{used, limit, remaining, subscription_url, live}``,
    or None if the user has no bypass entity. Syncs the cached link/limit on the
    way.

    ``live`` is True when the figures come straight from the panel this call, and
    False when the panel read failed and only the cached limit is known (``used``
    unknown → reported as 0). Callers that must show accurate consumption should
    check ``live`` and omit the number when it's False."""
    row = await get_bypass(telegram_id)
    if not row or not row["panel_uuid"]:
        return None
    try:
        user = await remnawave.find_user_by_username(
            config.build_bypass_username(telegram_id)
        )
    except Exception:  # noqa: BLE001 - never let a usage read break the cabinet
        logger.warning("Bypass usage read failed for %s; using cached", telegram_id)
        user = None
    if user is None:
        limit = int(row["traffic_limit_bytes"] or 0)
        return {
            "used": 0, "limit": limit, "remaining": limit,
            "subscription_url": row["subscription_url"], "live": False,
        }
    e = _extract(user)
    used, limit = int(e["used"]), int(e["limit"])
    url = e["url"] or row["subscription_url"]
    await set_bypass_meta(telegram_id, subscription_url=url, traffic_limit_bytes=limit)
    return {
        "used": used, "limit": limit,
        "remaining": max(0, limit - used), "subscription_url": url, "live": True,
    }
