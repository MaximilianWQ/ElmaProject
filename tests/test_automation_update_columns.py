"""``update_automation`` interpolates its keys straight into the SQL.

Today only a whitelisting route reaches it, so nothing is exploitable — but the
primitive itself will happily build ``UPDATE automations SET <anything> = $2``.
That is one careless future caller away from an injection, so the guard belongs
in the function, not only in the handler above it.
"""
import pytest

from database import automations


class _FakePool:
    def __init__(self):
        self.sql = None
        self.args = None

    async def execute(self, sql, *args):
        self.sql = sql
        self.args = args


@pytest.fixture
def pool(monkeypatch):
    p = _FakePool()
    monkeypatch.setattr(automations, "get_pool", lambda: p)
    return p


async def test_rejects_a_column_it_does_not_know(pool):
    with pytest.raises(ValueError):
        await automations.update_automation(1, **{"text = 'x', enabled": True})

    assert pool.sql is None, "nothing may reach the database"


async def test_rejects_an_unknown_but_harmless_looking_column(pool):
    with pytest.raises(ValueError):
        await automations.update_automation(1, created_at="now()")

    assert pool.sql is None


async def test_accepts_the_real_columns(pool):
    await automations.update_automation(1, name="ночная", enabled=False)

    assert "name = $2" in pool.sql and "enabled = $3" in pool.sql
    assert pool.args == (1, "ночная", False), "values stay parameterised"


async def test_no_fields_is_a_no_op(pool):
    await automations.update_automation(1)
    assert pool.sql is None
