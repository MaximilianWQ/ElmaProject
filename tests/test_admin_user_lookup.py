"""Admin user search must accept every shape of Telegram handle.

Telegram usernames are ``[A-Za-z0-9_]``, and the underscore is common. The old
check was ``query.isalnum()``, which is False for ``foo_bar`` — so an admin who
typed a handle without the leading ``@`` was told "Пользователь не найден" even
though the user existed.
"""
import pytest

from app.handlers import admin


@pytest.fixture
def directory(monkeypatch):
    """A tiny user directory behind the two lookup functions admin.py uses."""
    by_id = {77: {"telegram_id": 77, "username": "foo_bar"}}
    by_name = {"foo_bar": by_id[77]}
    seen = {"by_name": []}

    async def get_user(tg):
        return by_id.get(tg)

    async def find_user_by_username(name):
        seen["by_name"].append(name)
        return by_name.get(name.lstrip("@").lower())

    monkeypatch.setattr(admin, "get_user", get_user)
    monkeypatch.setattr(admin, "find_user_by_username", find_user_by_username)
    return seen


@pytest.mark.parametrize(
    "query",
    ["foo_bar", "@foo_bar", "  foo_bar  ", "FOO_BAR"],
)
async def test_finds_a_username_containing_an_underscore(directory, query):
    user = await admin._resolve_user(query)
    assert user is not None and user["telegram_id"] == 77


async def test_still_resolves_a_numeric_id(directory):
    user = await admin._resolve_user("77")
    assert user is not None and user["telegram_id"] == 77
    assert directory["by_name"] == [], "a numeric query is an id, not a handle"


async def test_rejects_something_that_is_neither(directory):
    assert await admin._resolve_user("nope nope!") is None
    assert directory["by_name"] == []
