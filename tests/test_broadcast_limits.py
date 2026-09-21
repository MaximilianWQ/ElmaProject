"""A broadcast that is too long must be rejected before it is sent, not after
it has failed for every single recipient.

Telegram counts a message as "1-4096 characters **after entities parsing**"
(0-1024 for a photo caption), in UTF-16 code units. So the check must ignore the
HTML markup — counting the raw string would reject perfectly valid messages that
are mostly tags — and must count a non-BMP emoji as the two units Telegram does.

Without this, a 1200-character caption produced a CAPTION_TOO_LONG for all N
recipients: the whole run landed in `failed` and the admin only learned about it
from the final summary.
"""
import pytest

from app.services import broadcast_runner as br


# --- length as Telegram counts it ------------------------------------------


def test_markup_does_not_count_towards_the_limit():
    assert br.visible_length("<b>hi</b>") == 2


def test_nested_markup_and_links_do_not_count():
    body = '<a href="https://example.com/very/long/path">ok</a>'
    assert br.visible_length(body) == 2


def test_escaped_entities_count_as_one_character():
    assert br.visible_length("&lt;&gt;&amp;") == 3


def test_custom_emoji_counts_as_its_fallback_glyph():
    assert br.visible_length('<tg-emoji emoji-id="5">🎁</tg-emoji>') == 2, (
        "a non-BMP emoji is two UTF-16 code units"
    )


def test_plain_text_is_counted_verbatim():
    assert br.visible_length("abc") == 3


# --- the guard -------------------------------------------------------------


def test_long_caption_is_rejected_for_a_photo_broadcast():
    with pytest.raises(br.BroadcastTooLong) as exc:
        br.check_length("x" * 1100, photo=True)
    assert "1024" in str(exc.value)


def test_same_body_is_fine_as_a_text_broadcast():
    br.check_length("x" * 1100, photo=False)  # must not raise


def test_long_text_is_rejected():
    with pytest.raises(br.BroadcastTooLong):
        br.check_length("x" * 4200, photo=False)


# --- the guard actually stops a run ----------------------------------------


@pytest.fixture
def runner(monkeypatch):
    """Wire run_broadcast to fakes; collect what it would have dispatched."""
    state = {"dispatched": [], "admin_messages": [], "finished": None}

    async def recipients(segment):
        return [1, 2, 3]

    async def record_broadcast(**kw):
        return 77

    async def finish_broadcast(bid, **kw):
        state["finished"] = (bid, kw)

    async def fake_broadcast(ids, send_one, **kw):
        state["dispatched"].append(len(ids))
        raise AssertionError("must not dispatch an over-long broadcast")

    async def fake_safe_send(bot, uid, text, **kw):
        state["admin_messages"].append(text)

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(br.database, "recipients", recipients)
    monkeypatch.setattr(br.database, "record_broadcast", record_broadcast)
    monkeypatch.setattr(br.database, "finish_broadcast", finish_broadcast)
    monkeypatch.setattr(br.broadcaster, "broadcast", fake_broadcast)
    monkeypatch.setattr(br, "safe_send", fake_safe_send)
    monkeypatch.setattr(br.config, "ADMIN_IDS", frozenset({999}))

    from app.services import push_service

    monkeypatch.setattr(push_service, "notify_broadcast_done", noop)
    return state


async def test_over_long_caption_dispatches_nothing(runner):
    await br.run_broadcast(
        object(), admin_id=999, segment="all",
        text="y" * 1200, photo_file_id="photo-file-id",
    )
    assert runner["dispatched"] == [], "no recipient should have been contacted"


async def test_over_long_caption_tells_the_admin_why(runner):
    await br.run_broadcast(
        object(), admin_id=999, segment="all",
        text="y" * 1200, photo_file_id="photo-file-id",
    )
    assert runner["admin_messages"], "the admin must be told the run did not go out"
    assert "1024" in runner["admin_messages"][0]


async def test_over_long_b_variant_stops_the_whole_run(runner):
    await br.run_broadcast(
        object(), admin_id=999, segment="all",
        text="short", text_b="y" * 5000, is_ab=True,
    )
    assert runner["dispatched"] == [], "variant B is part of the same run"


def test_a_heavily_marked_up_body_is_not_falsely_rejected():
    """~1400 raw characters but only 1020 visible ones — must pass as a caption."""
    body = "<b>" + "x" * 1000 + "</b>" + "<i>ok</i>" * 10
    assert len(body) > 1024 and br.visible_length(body) == 1020
    br.check_length(body, photo=True)
