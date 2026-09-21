"""Squad membership must hit the route Remnawave 3.x actually exposes.

Verified against the 3.4.3 contract (libs/contract/api/controllers/*):

* there is NO ``squads`` controller — only ``internal-squads`` / ``external-squads``
* ``INTERNAL_SQUADS_ROUTES.BULK_ACTIONS.ADD_MANY_USERS`` is
  ``{uuid}/bulk-actions/add-many-users`` (POST) with body ``{userIds: number[]}``
* ``ADD_USERS`` (``{uuid}/bulk-actions/add-users``) adds **every** user in the
  panel to the squad and takes no body — it must never be used here
* ``ROOT`` is ``/api``

The previous call (``POST /api/squads/add-users-to-squad``) 404s, and ``_req``
turns a 404 into ``None`` — so the "user reached no inbound" safety net failed
silently and the user got a subscription with zero servers.
"""
import pytest

from app.services import remnawave as rw


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def fake_req(method, path, **kwargs):
        calls.append({"method": method, "path": path, **kwargs})
        return {}

    monkeypatch.setattr(rw, "_req", fake_req)
    return calls


async def test_posts_to_the_internal_squad_bulk_route(captured):
    await rw.add_users_to_squad("11111111-2222-3333-4444-555555555555", ["17"])

    assert captured == [
        {
            "method": "POST",
            "path": "/api/internal-squads/11111111-2222-3333-4444-555555555555"
                    "/bulk-actions/add-many-users",
            "json": {"userIds": [17]},
        }
    ]


async def test_never_calls_the_add_all_users_route(captured):
    await rw.add_users_to_squad("squad-uuid", ["17"])

    path = captured[0]["path"]
    assert path.endswith("/add-many-users")
    assert not path.endswith("/bulk-actions/add-users"), (
        "add-users adds EVERY panel user to the squad"
    )


async def test_ids_are_sent_as_numbers(captured):
    await rw.add_users_to_squad("squad-uuid", [17, "42"])

    assert captured[0]["json"] == {"userIds": [17, 42]}, "contract: z.array(z.number())"


async def test_legacy_uuid_identifiers_are_not_sent(captured):
    """3.x identifies users by numeric id only; a legacy uuid cannot be added
    and must not be turned into a doomed request."""
    result = await rw.add_users_to_squad("squad-uuid", ["7f3a1c2e-uuid-style"])

    assert captured == [], "nothing to send -> no request"
    assert result is None


async def test_empty_input_makes_no_request(captured):
    assert await rw.add_users_to_squad("squad-uuid", []) is None
    assert captured == []
