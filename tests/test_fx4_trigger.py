"""Tests for ``QuadFX4.trigger`` arming against a laggy monitor dispatcher.

The bug these cover: stopping a free-running acquisition makes ``Acquire``
fall 1 -> 0, and that monitor event is delivered on the control layer's
callback thread some milliseconds later -- after ``trigger()`` has armed the
status for the acquisition it is *about* to start.  ophyd's
``_acquire_changed`` finishes whatever status is armed on any falling edge, so
the stale edge either nulled ``self._status`` (``bps.trigger`` then died with
``AttributeError: 'NoneType' object has no attribute 'add_callback'``) or
completed the new status immediately, so the plan read the previous
acquisition's mean.

The real device cannot be instantiated without an IOC, so the methods under
test are borrowed onto a stand-in that fakes the two EPICS records and the
dispatcher's lag.  ``_acquire_changed`` below mirrors
``ophyd.areadetector.trigger_mixins.SingleTrigger._acquire_changed``, which is
the library behaviour being worked around.
"""

import threading
import time

import pytest

from usaxs.devices.fx4_quadem import QuadFX4


class FakeStatus:
    """``DeviceStatus`` stand-in: records whether it has been completed."""

    def __init__(self, device):
        """Start out incomplete."""
        self.device = device
        self.done = False

    def set_finished(self):
        """Mark the acquisition complete."""
        self.done = True


class FakeAcquireSignal:
    """``Acquire`` record whose monitor events are dispatched late.

    A put returns as soon as the value changes -- as ``put(wait=True)`` does,
    which waits on the IOC -- but the subscription callback runs ``lag``
    seconds later on another thread, the way the control layer's dispatcher
    does.
    """

    def __init__(self, value=0, lag=0.05, finish_immediately=False):
        """Set the resting value, the dispatcher lag in seconds, and whether
        an acquisition ends as soon as it is started."""
        self.value = value
        self.lag = lag
        self.finish_immediately = finish_immediately
        self.callbacks = []
        self.timers = []

    def subscribe(self, cb, **kwargs):
        """Register *cb* and call it once with the current value, as ophyd does."""
        self.callbacks.append(cb)
        cb(value=self.value, old_value=self.value)
        return len(self.callbacks)

    def get(self, **kwargs):
        """Return the value the IOC holds now."""
        return self.value

    def put(self, value, wait=False):
        """Change the value now, deliver the monitor event per the lag."""
        self._change(value)
        if value == 1 and self.finish_immediately:
            self._change(0)

    def _change(self, value):
        old, self.value = self.value, value
        if not self.lag:
            self._dispatch(old, value)
            return
        timer = threading.Timer(self.lag, self._dispatch, args=(old, value))
        timer.daemon = True
        self.timers.append(timer)
        timer.start()

    def _dispatch(self, old_value, value):
        for cb in self.callbacks:
            cb(value=value, old_value=old_value)

    def settle(self):
        """Wait for every pending monitor event to be delivered."""
        for timer in list(self.timers):
            timer.join()


class FakeModeSignal:
    """``AcquireMode`` record, string-valued."""

    def __init__(self, value="Continuous"):
        """Start in the resting free-running mode."""
        self.value = value

    def get(self, as_string=False, **kwargs):
        """Return the mode."""
        return self.value

    def put(self, value, wait=False):
        """Set the mode."""
        self.value = value


class FakeFX4:
    """Enough of ``QuadFX4`` to exercise the real ``trigger()``."""

    name = "fx4"
    _status_type = FakeStatus

    # The methods under test, borrowed from the real class.
    trigger = QuadFX4.trigger
    _ensure_acquire_subscription = QuadFX4._ensure_acquire_subscription
    _drain_stale_acquire_edge = QuadFX4._drain_stale_acquire_edge
    _acquire_is_idle = staticmethod(QuadFX4._acquire_is_idle)

    def __init__(self, acquiring=False, lag=0.05, finish_immediately=False):
        """Create a device that is, or is not, already free-running."""
        self.acquire_mode = FakeModeSignal("Continuous" if acquiring else "Single")
        self._acquisition_signal = FakeAcquireSignal(
            1 if acquiring else 0,
            lag=lag,
            finish_immediately=finish_immediately,
        )
        self._acquire_sub_cid = None
        self._acquire_seen = None
        self._status = None

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        """Mirror of ophyd's ``SingleTrigger._acquire_changed``, plus our hook."""
        self._acquire_seen = value
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            self._status.set_finished()
            self._status = None

    def finish_acquisition(self):
        """Let the IOC end the acquisition that ``trigger()`` started."""
        self._acquisition_signal.put(0)
        self._acquisition_signal.settle()


def test_trigger_of_free_running_device_returns_a_live_status():
    """The stale 1 -> 0 edge must not land on the status being armed."""
    det = FakeFX4(acquiring=True)

    status = det.trigger()
    det._acquisition_signal.settle()  # let every late monitor event land

    assert status is not None, "trigger() returned None; the RunEngine would abort"
    assert not status.done, "the stale edge completed the status before acquiring"
    assert det._acquisition_signal.get() == 1, "acquisition was not started"

    det.finish_acquisition()
    assert status.done, "the real falling edge did not complete the status"


def test_trigger_survives_an_acquisition_that_ends_inside_the_put():
    """``trigger()`` must return its own status, not ``self._status``.

    ``_acquire_changed`` sets ``self._status = None`` the moment the
    acquisition completes, and for a short count time that can happen before
    ``trigger()`` gets to its ``return`` -- which is the form the failure took
    on the beamline: ``'NoneType' object has no attribute 'add_callback'``.
    """
    det = FakeFX4(acquiring=True, lag=0.0, finish_immediately=True)

    status = det.trigger()

    assert status is not None, "trigger() returned None; the RunEngine would abort"
    assert status.done, "the completing edge did not reach the returned status"
    assert det._status is None, "ophyd should have cleared the armed status"


def test_trigger_waits_for_the_stale_edge_before_arming():
    """``trigger()`` blocks until the subscription has seen Acquire go idle."""
    det = FakeFX4(acquiring=True, lag=0.2)

    t0 = time.monotonic()
    det.trigger()
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.2, "armed before the stopping edge was delivered"
    assert det._acquisition_signal.get() == 1, "acquisition was not started"


def test_repeated_triggers_never_return_none():
    """The dark-current loop triggers an already-idle device many times."""
    det = FakeFX4(acquiring=True)

    for _ in range(5):
        status = det.trigger()
        assert status is not None
        det.finish_acquisition()
        assert status.done


def test_drain_times_out_without_hanging(caplog):
    """A missing edge warns and proceeds instead of blocking forever."""
    det = FakeFX4(acquiring=True)
    det._acquire_seen = 1

    assert det._drain_stale_acquire_edge(timeout=0.05) is False
    assert "Acquire still reads" in caplog.text


@pytest.mark.parametrize(
    "value, idle",
    [(0, True), ("Done", True), (1, False), ("Acquire", False), (None, False)],
)
def test_acquire_is_idle(value, idle):
    """Both the numeric and the string form of "not acquiring" count as idle."""
    assert QuadFX4._acquire_is_idle(value) is idle
