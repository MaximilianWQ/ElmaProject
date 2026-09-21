"""Routine logs must not look like errors to the platform.

logging.basicConfig writes to stderr, so Railway tagged every single INFO line
— "Database schema ready", every aggregator hit — with severity=error. A real
failure was then indistinguishable from normal traffic, which is exactly when
the severity filter matters. Ordinary records go to stdout; WARNING and above
go to stderr.
"""
import logging
import sys

import pytest

import main


@pytest.fixture(autouse=True)
def clean_root():
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    root.handlers = []
    yield
    root.handlers, root.level = saved[0], saved[1]


def _streams_for(level: int) -> set:
    record = logging.LogRecord("t", level, __file__, 1, "m", None, None)
    # handler.filter() applies both plain callables and Filter objects.
    return {
        h.stream for h in logging.getLogger().handlers
        if record.levelno >= h.level and h.filter(record)
    }


def test_info_goes_to_stdout_only():
    main.setup_logging()
    assert _streams_for(logging.INFO) == {sys.stdout}


def test_warning_and_error_go_to_stderr_only():
    main.setup_logging()
    assert _streams_for(logging.WARNING) == {sys.stderr}
    assert _streams_for(logging.ERROR) == {sys.stderr}


def test_calling_it_twice_does_not_double_every_line():
    main.setup_logging()
    main.setup_logging()
    assert len(logging.getLogger().handlers) == 2
