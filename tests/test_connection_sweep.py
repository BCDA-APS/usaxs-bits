"""Tests for the post-``make_devices`` connection sweep.

These run without EPICS or ``apsbits``: ``connection_sweep`` imports only the
standard library, so fakes standing in for ophyd signals and the guarneri
instrument are enough.

    PYTHONPATH=src python -m pytest tests/test_connection_sweep.py -v
"""

import pytest

from usaxs.utils import connection_sweep
from usaxs.utils.connection_sweep import sweep_unconnected_devices


class FakeSignal:
    """An ophyd-signal stand-in with a controllable connection story.

    ``heals`` reproduces the bug this module exists for: ophyd reports
    ``connected is False`` because a metadata callback was dropped, but a
    ``wait_for_connection`` with a nonzero timeout fetches it synchronously and
    the signal comes good.
    """

    def __init__(self, name, connected=True, heals=False, pvname=None):
        """Build a signal that is ``connected``, and optionally self-heals."""
        self.name = name
        self.connected = connected
        self.pvname = pvname or f"ioc:{name}"
        self._heals = heals
        self.waits = []

    def wait_for_connection(self, timeout=None):
        """Record the timeout, then heal or raise as configured."""
        self.waits.append(timeout)
        if self._heals:
            self.connected = True
            return
        if not self.connected:
            raise TimeoutError(f"{self.pvname} could not connect within {timeout}s")


class FakeWalk:
    """Stand-in for ophyd's ``ComponentWalk`` namedtuple."""

    def __init__(self, item):
        """Wrap one signal the way ``Device.walk_signals`` does."""
        self.item = item


class FakeDevice:
    """An ophyd ``Device`` stand-in holding a fixed list of signals."""

    def __init__(self, name, signals):
        """Build a device named *name* over *signals*."""
        self.name = name
        self.signals = signals

    def walk_signals(self, include_lazy=False):
        """Yield every signal, wrapped as ophyd would wrap it."""
        return [FakeWalk(sig) for sig in self.signals]

    @property
    def connected(self):
        """True only when every component signal is connected."""
        return all(sig.connected for sig in self.signals)


class FakeRegistry:
    """Stand-in for ``Instrument.devices`` (the ophyd registry)."""

    def __init__(self):
        """Start with nothing registered."""
        self.registered = []

    def register(self, device):
        """Record that *device* was re-registered."""
        self.registered.append(device)


class FakeInstrument:
    """Stand-in for ``guarneri.Instrument``, retry list and all."""

    def __init__(self, devices):
        """Seed the retry list with *devices*."""
        self.unconnected_devices = list(devices)
        self.devices = FakeRegistry()


def test_no_leftovers_is_a_no_op():
    """The common case: make_devices connected everything."""
    inst = FakeInstrument([])
    assert sweep_unconnected_devices(inst) == ([], [])
    assert inst.devices.registered == []


def test_stuck_metadata_signal_is_repaired():
    """The user_data.scanning case: live channel, missing metadata callback."""
    stuck = FakeSignal("scanning", connected=False, heals=True)
    device = FakeDevice("user_data", [FakeSignal("state"), stuck])
    inst = FakeInstrument([device])

    repaired, failed = sweep_unconnected_devices(inst)

    assert repaired == [device]
    assert failed == []
    assert stuck.connected
    # guarneri's give-up call passes timeout=0, which skips the blocking
    # metadata fetch; the sweep exists precisely to pass a nonzero one.
    assert stuck.waits and all(t > 0 for t in stuck.waits)


def test_repaired_device_leaves_the_retry_list():
    """Otherwise every later make_devices re-pays the connect timeout."""
    device = FakeDevice("user_data", [FakeSignal("scanning", False, heals=True)])
    inst = FakeInstrument([device])

    sweep_unconnected_devices(inst)

    assert inst.unconnected_devices == []
    assert inst.devices.registered == [device]


def test_already_connected_signals_are_not_waited_on():
    """A device can be in the list with every signal since come good."""
    good = FakeSignal("state")
    device = FakeDevice("user_data", [good])
    inst = FakeInstrument([device])

    repaired, failed = sweep_unconnected_devices(inst)

    assert (repaired, failed) == ([device], [])
    assert good.waits == []


def test_dead_pv_is_reported_and_kept():
    """The sweep repairs races; it must not paper over absent hardware."""
    dead = FakeSignal("gone", connected=False, heals=False, pvname="ioc:gone")
    device = FakeDevice("broken", [dead])
    inst = FakeInstrument([device])

    repaired, failed = sweep_unconnected_devices(inst, signal_timeout=0.01)

    assert repaired == []
    assert failed == [device]
    assert inst.unconnected_devices == [device]
    assert inst.devices.registered == []


def test_partial_failure_fails_the_whole_device():
    """One unreachable signal means the device is not safe to call connected."""
    device = FakeDevice(
        "mixed",
        [FakeSignal("ok", False, heals=True), FakeSignal("bad", False, heals=False)],
    )
    inst = FakeInstrument([device])

    repaired, failed = sweep_unconnected_devices(inst, signal_timeout=0.01)

    assert (repaired, failed) == ([], [device])


def test_bare_signal_device_without_walk_signals():
    """ophyd.EpicsSignalRO entries in devices.yml are their own signal."""
    bare = FakeSignal("adam_tc2", connected=False, heals=True)
    inst = FakeInstrument([bare])

    repaired, failed = sweep_unconnected_devices(inst)

    assert (repaired, failed) == ([bare], [])
    assert bare.connected


def test_budget_stops_the_sweep(monkeypatch):
    """A dead IOC must not add minutes to startup."""
    first = FakeDevice("first", [FakeSignal("a", False, heals=True)])
    second = FakeDevice("second", [FakeSignal("b", False, heals=True)])
    inst = FakeInstrument([first, second])

    # Spend the whole budget inside the first device's turn.
    ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(connection_sweep.time, "monotonic", lambda: next(ticks))

    repaired, failed = sweep_unconnected_devices(inst, budget=10.0)

    assert repaired == [first]
    assert failed == [second]
    # Not retried, so not condemned either -- it stays for the next sweep.
    assert inst.unconnected_devices == [second]


def test_instrument_without_the_attribute_is_tolerated():
    """Guard against a guarneri version that renames the retry list."""

    class Bare:
        pass

    assert sweep_unconnected_devices(Bare()) == ([], [])


@pytest.mark.parametrize("timeout", [0.01, 1.0])
def test_signal_timeout_is_forwarded(timeout):
    """Whatever startup configures must reach ophyd, not a hardcoded default."""
    stuck = FakeSignal("scanning", connected=False, heals=True)
    inst = FakeInstrument([FakeDevice("user_data", [stuck])])

    sweep_unconnected_devices(inst, signal_timeout=timeout)

    assert stuck.waits == [timeout]
