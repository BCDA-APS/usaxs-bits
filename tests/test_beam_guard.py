"""Tests for the ``@beam_guarded`` plan decorator.

These need ``bluesky`` but not EPICS or ``apsbits``: ``beam_guard`` imports
nothing from ``usaxs`` and resolves the suspenders at call time.

    PYTHONPATH=src python -m pytest tests/test_beam_guard.py -v
"""

import pytest
from bluesky import plan_stubs as bps

from usaxs.suspenders.beam_guard import beam_guarded
from usaxs.suspenders.beam_guard import set_beam_suspenders


@pytest.fixture(autouse=True)
def disarmed():
    """Leave the module-level registry empty for every test."""
    set_beam_suspenders()
    yield
    set_beam_suspenders()


@beam_guarded
def _scan():
    yield from bps.null()
    return "done"


def _commands(plan):
    return [msg.command for msg in plan]


def test_unarmed_plan_still_opens_a_rewind_boundary():
    """The checkpoint is emitted even when no suspenders are registered.

    It is what keeps a suspender rewind from replaying messages cached by the
    *previous* plan, across a closed run.
    """
    assert _commands(_scan()) == ["checkpoint", "null"]


def test_checkpoint_precedes_the_suspenders():
    """The rewind boundary is opened before the suspenders go on."""
    set_beam_suspenders(object())
    assert _commands(_scan()) == [
        "checkpoint",
        "install_suspender",
        "null",
        "remove_suspender",
    ]


@pytest.mark.parametrize("armed", [False, True])
def test_return_value_is_preserved(armed):
    """The extra checkpoint must not swallow the plan's return value."""
    if armed:
        set_beam_suspenders(object())

    def driver():
        result = yield from _scan()
        return result

    gen = driver()
    try:
        while True:
            gen.send(None)
    except StopIteration as stop:
        assert stop.value == "done"
    else:  # pragma: no cover - the generator always terminates
        pytest.fail("plan did not terminate")
