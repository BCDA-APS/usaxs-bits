"""Tests for the operations-vs-simulation decision.

The property under test is one-sided: a PV that cannot be read must never
produce ``in_operation = False``.  Simulation replaces the shutters and the
beam suspenders with stand-ins that move nothing and never trigger, so a wrong
*False* here costs a shift of beamtime and reports nothing worse than a failed
fit.  A wrong *True* costs a traceback.
"""

import pytest

from usaxs.utils.operation_mode import BL_ENABLE_PV
from usaxs.utils.operation_mode import OVERRIDE_ENV
from usaxs.utils.operation_mode import OperationModeUnknown
from usaxs.utils.operation_mode import determine_in_operation
from usaxs.utils.operation_mode import operation_mode_banner


class FakePV:
    """Stand-in for ``epics.PV`` with scripted connect/read behaviour."""

    def __init__(self, pvname, connection_timeout=None):
        """Record what ``epics.PV`` would have been constructed with."""
        self.pvname = pvname
        self.connection_timeout = connection_timeout

    def wait_for_connection(self, timeout=None):
        """Report the scripted connection outcome."""
        return self._connects

    def get(self, timeout=None, use_monitor=None):
        """Report the scripted value."""
        return self._value


def fake_pv_factory(connects=True, value=1.0):
    """Build a ``FakePV`` subclass that connects/reads as specified."""
    return type("ScriptedPV", (FakePV,), {"_connects": connects, "_value": value})


@pytest.fixture(autouse=True)
def _clear_override(monkeypatch):
    """Keep a developer's exported USAXS_SIMULATE out of the tests."""
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, True),
        (1, True),
        (0.0, False),
        (0, False),
        (2.0, False),
    ],
)
def test_pv_value_decides_mode(monkeypatch, value, expected):
    """A readable PV decides the mode, and only 1 means operations."""
    monkeypatch.setattr("usaxs.utils.operation_mode.PV", fake_pv_factory(value=value))
    in_operation, reason = determine_in_operation()
    assert in_operation is expected
    assert BL_ENABLE_PV in reason


def test_unconnectable_pv_raises_rather_than_simulating(monkeypatch):
    """The regression this module exists for: no silent downgrade to sim."""
    monkeypatch.setattr(
        "usaxs.utils.operation_mode.PV", fake_pv_factory(connects=False)
    )
    with pytest.raises(OperationModeUnknown) as excinfo:
        determine_in_operation(attempts=2)
    assert OVERRIDE_ENV in str(excinfo.value)


def test_connected_but_valueless_pv_raises(monkeypatch):
    """``caget`` returning None used to read as 'not in operation'."""
    monkeypatch.setattr("usaxs.utils.operation_mode.PV", fake_pv_factory(value=None))
    with pytest.raises(OperationModeUnknown):
        determine_in_operation(attempts=1)


def test_retries_are_attempted(monkeypatch):
    """Each attempt gets its own connection try."""
    calls = []

    class CountingPV(FakePV):
        def wait_for_connection(self, timeout=None):
            calls.append(timeout)
            return False

    monkeypatch.setattr("usaxs.utils.operation_mode.PV", CountingPV)
    with pytest.raises(OperationModeUnknown):
        determine_in_operation(attempts=3, connection_timeout=0.5)
    assert calls == [0.5, 0.5, 0.5]


@pytest.mark.parametrize("word", ["1", "true", "Yes", "ON", "sim", "simulation"])
def test_override_can_force_simulation(monkeypatch, word):
    """Simulation stays available -- but you have to ask for it."""
    monkeypatch.setenv(OVERRIDE_ENV, word)
    monkeypatch.setattr(
        "usaxs.utils.operation_mode.PV", fake_pv_factory(connects=False)
    )
    in_operation, reason = determine_in_operation()
    assert in_operation is False
    assert OVERRIDE_ENV in reason


@pytest.mark.parametrize("word", ["0", "false", "No", "OFF", "ops", "operations"])
def test_override_can_force_operations(monkeypatch, word):
    """Useful when the enable PV is down but the hardware is not."""
    monkeypatch.setenv(OVERRIDE_ENV, word)
    monkeypatch.setattr(
        "usaxs.utils.operation_mode.PV", fake_pv_factory(connects=False)
    )
    in_operation, _ = determine_in_operation()
    assert in_operation is True


def test_unparseable_override_raises(monkeypatch):
    """An override nobody can read is an unknown mode, not a default."""
    monkeypatch.setenv(OVERRIDE_ENV, "maybe")
    with pytest.raises(OperationModeUnknown):
        determine_in_operation()


def test_simulation_banner_says_what_is_fake():
    """The banner has to be readable by someone who did not expect it."""
    banner = operation_mode_banner(False, "test")
    assert "SIMULATION" in banner
    assert "usaxs_shutter" in banner
    assert "suspenders" in banner


def test_operations_banner_is_unambiguous():
    """Operations mode must not mention simulation at all."""
    banner = operation_mode_banner(True, "test")
    assert "OPERATIONS" in banner
    assert "SIMULATION" not in banner
