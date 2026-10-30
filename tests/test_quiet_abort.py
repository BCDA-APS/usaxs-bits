"""Tests for the ``Run aborted`` log filter.

These run without EPICS or ``apsbits``: ``quiet_abort`` only needs ``logging``
and the bluesky exception classes.

    PYTHONPATH=src python -m pytest tests/test_quiet_abort.py -v
"""

import logging

import pytest
from bluesky.utils import PlanHalt
from bluesky.utils import RequestAbort

from usaxs.utils.quiet_abort import UserAbortIsNotAnError
from usaxs.utils.quiet_abort import quiet_user_abort


def make_record(message, exception):
    """Build the record the RunEngine's ``log.exception(message)`` would make."""
    exc_info = (None, None, None)
    if exception is not None:
        try:
            raise exception
        except BaseException as exc:  # noqa: BLE001 -- we want whatever was raised
            exc_info = (type(exc), exc, exc.__traceback__)
    return logging.LogRecord(
        name="bluesky",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg=message,
        args=(),
        exc_info=exc_info if exception is not None else None,
    )


@pytest.fixture
def bluesky_logger():
    """The ``bluesky`` logger, with any filters this test added removed after."""
    log = logging.getLogger("bluesky")
    before = list(log.filters)
    yield log
    for extra in [f for f in log.filters if f not in before]:
        log.removeFilter(extra)


@pytest.mark.parametrize("exception_class", [RequestAbort, PlanHalt])
def test_user_abort_becomes_one_info_line(exception_class):
    """A user stop loses its traceback and drops to INFO."""
    reason = "EPICS user requested stop data collection before next scan"
    record = make_record("Run aborted", exception_class(reason))

    assert UserAbortIsNotAnError().filter(record) is True

    assert record.exc_info is None
    assert record.levelno == logging.INFO
    assert record.levelname == "INFO"
    assert reason in record.getMessage()


def test_real_failure_keeps_its_traceback():
    """Anything that is not a user stop is left exactly as the RunEngine made it."""
    record = make_record("Run aborted", ValueError("motor did not move"))

    assert UserAbortIsNotAnError().filter(record) is True

    assert record.exc_info is not None
    assert record.levelno == logging.ERROR
    assert record.getMessage() == "Run aborted"


def test_other_messages_are_untouched():
    """The filter keys on the RunEngine's exact message, not on the exception."""
    record = make_record("Failed to unstage %r.", RequestAbort("stop"))

    assert UserAbortIsNotAnError().filter(record) is True

    assert record.exc_info is not None
    assert record.levelno == logging.ERROR


def test_abort_without_exception_is_untouched():
    """``logger.error('Run aborted')`` with no exception is not rewritten."""
    record = make_record("Run aborted", None)

    assert UserAbortIsNotAnError().filter(record) is True

    assert record.levelno == logging.ERROR
    assert record.getMessage() == "Run aborted"


def test_install_is_idempotent(bluesky_logger):
    """Re-importing ``usaxs.startup`` must not stack copies of the filter."""
    quiet_user_abort()
    quiet_user_abort()

    installed = [
        f for f in bluesky_logger.filters if isinstance(f, UserAbortIsNotAnError)
    ]
    assert len(installed) == 1
