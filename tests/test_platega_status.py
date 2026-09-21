"""The reconcile poll must not re-probe an endpoint that answered 404.

Production logs show /v2/transaction/{id} answering 404 on every single
lookup, with the legacy /transaction/{id} then returning the status. Because
reconcile polls a pending payment once a minute for up to three hours, a fixed
"try v2 first" order spends one wasted round-trip per poll — up to 180 per
unpaid payment. Learn which path the provider actually serves and keep using
it, while still probing the preferred one once per process so the newer API is
picked up if the provider turns it on.
"""
import pytest

from app.services import platega


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected raise_for_status on {self.status_code}")

    def json(self):
        return self._payload


class FakeClient:
    """Answers 404 for the v2 path and a status for the legacy one."""

    def __init__(self):
        self.paths: list[str] = []

    async def get(self, path: str):
        self.paths.append(path)
        if path.startswith("/v2/"):
            return FakeResponse(404)
        return FakeResponse(200, {"status": "PENDING"})


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(platega, "_get_client", lambda: fake)
    monkeypatch.setattr(platega, "_status_path", None, raising=False)
    return fake


async def test_first_lookup_probes_the_preferred_path(client):
    assert await platega.get_status("abc") == "PENDING"
    assert client.paths == ["/v2/transaction/abc", "/transaction/abc"]


async def test_later_lookups_go_straight_to_the_path_that_works(client):
    await platega.get_status("abc")
    client.paths.clear()

    for _ in range(5):
        assert await platega.get_status("abc") == "PENDING"

    assert client.paths == ["/transaction/abc"] * 5, (
        "the dead v2 path was probed again: " + ", ".join(client.paths)
    )


async def test_an_unknown_transaction_is_still_none(client, monkeypatch):
    class AllMissing(FakeClient):
        async def get(self, path):
            self.paths.append(path)
            return FakeResponse(404)

    missing = AllMissing()
    monkeypatch.setattr(platega, "_get_client", lambda: missing)
    assert await platega.get_status("nope") is None
