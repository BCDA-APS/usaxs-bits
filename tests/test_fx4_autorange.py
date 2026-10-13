"""Tests for the FX4 autoscale convergence loop, driven by fake devices.

The plan is a generator of Bluesky messages, so it can be exercised by a tiny
message interpreter without a RunEngine, an IOC, or ophyd signals.
"""

import pytest

from usaxs.devices.fx4_quadem import FX4AutorangeDirection
from usaxs.devices.fx4_quadem import FX4AutorangeSettings
from usaxs.plans import fx4_autorange_plan as arp


class FakeSignal:
    """A settable value with the bits of the ophyd Signal API used here.

    ``parent`` and ``name`` exist because ``bps.mv`` groups its arguments with
    ``separate_devices``, which walks the parent chain.
    """

    parent = None

    def __init__(self, value=0, name="fake"):
        """Store the initial value."""
        self.value = value
        self.name = name

    def get(self, **kwargs):
        """Return the current value."""
        return self.value

    def put(self, value):
        """Set the value."""
        self.value = value


class FakeRanges:
    """``auto.ranges`` stand-in: five background record pairs."""

    def __init__(self):
        """Create range0..range4, each with background and error signals."""
        for i in range(5):
            setattr(
                self,
                f"range{i}",
                type(
                    "R",
                    (),
                    {"background": FakeSignal(), "background_error": FakeSignal()},
                )(),
            )


class FakeAuto:
    """Sequence program that walks one step toward ``target_range`` per read."""

    def __init__(self, target_range=2, start_range=4):
        """Set where the program should end up and where it starts."""
        self.reqrange = FakeSignal(start_range)
        self.lurange = FakeSignal(start_range)
        self.channel = FakeSignal(0)
        self.mode = FakeSignal(FX4AutorangeSettings.manual)
        self.direction = FakeSignal(FX4AutorangeDirection.both)
        self.settling_time = FakeSignal(0.0)
        # Convergence window, as on FX4AutorangeDevice.  _reading_above_window
        # reads max_fraction on every iteration of the autoscale loop.
        self.min_fraction = FakeSignal(0.07)
        self.max_fraction = FakeSignal(0.90)
        self.ranges = FakeRanges()
        self.target_range = target_range
        self.reads = 0

    def setRange(self, target):
        """Plan: seed the range, as the real device does."""
        self.reqrange.value = int(target)
        self.lurange.value = int(target)
        yield ("set_range", int(target))

    def setChannel(self, channel):
        """Plan: point the program at a channel."""
        self.channel.value = channel
        yield ("set_channel", channel)

    def current_window(self, full_scale_pA):
        """Return a window that always passes, so logging never raises."""
        return (0.0, float("inf"))

    def on_read(self):
        """Move one range toward the target, the way the IOC does per read.

        Mirrors ``FX4_autoRange.st``'s ``checkRange``: ``dir = Increase``
        suppresses only the move toward a *more sensitive* range (``reqrange++``,
        index up), leaving the move toward a coarser one always available.
        """
        self.reads += 1
        if self.mode.value != FX4AutorangeSettings.automatic:
            return
        if self.lurange.value < self.target_range:
            if self.direction.value == FX4AutorangeDirection.increase:
                return
            self.lurange.value += 1
        elif self.lurange.value > self.target_range:
            self.lurange.value -= 1


class FakeQuadEM:
    """Electrometer stand-in that notifies its autoranger on each trigger."""

    def __init__(self, name, auto):
        """Bind the electrometer to its sequence program."""
        self.name = name
        self.auto = auto
        self.averaging_time = FakeSignal(1.0)
        self.em_range = FakeSignal("100 nA")


class FakeControls:
    """``FX4DetectorControls`` stand-in."""

    def __init__(self, nickname, quadem, channel, auto):
        """Bind nickname, electrometer, channel and autoranger."""
        self.nickname = nickname
        self.quadem = quadem
        self.channel_number = channel
        self.auto = auto
        self.signal = FakeSignal(1234.0)

    @property
    def autoranged(self):
        """Return True: these fakes always have a sequence program."""
        return self.auto is not None


def run(plan, auto):
    """Execute a plan's messages, letting *auto* re-range on each trigger.

    Returns
    -------
    list
        The messages seen, for assertions.
    """
    seen = []
    for msg in plan:
        # bluesky's Msg is itself a NamedTuple, so test for the field rather
        # than the type -- the fake setRange/setChannel plans yield plain
        # tuples, which would otherwise be indistinguishable.
        if not hasattr(msg, "command"):
            seen.append(msg)
            continue
        seen.append(msg.command)
        if msg.command == "set":
            obj, value = msg.obj, msg.args[0]
            obj.put(value)
        elif msg.command == "trigger":
            auto.on_read()
    return seen


@pytest.fixture(autouse=True)
def _clear_memory():
    """Each test starts with no remembered ranges."""
    arp._last_range_.clear()
    yield
    arp._last_range_.clear()


def _make(target_range=2, start_range=4, nickname="UPD", channel=1):
    auto = FakeAuto(target_range=target_range, start_range=start_range)
    return FakeControls(nickname, FakeQuadEM("fx4", auto), channel, auto), auto


def test_converges_and_stops_reading():
    """The loop exits as soon as the range repeats, not after max_iterations."""
    control, auto = _make(target_range=2, start_range=4)
    run(arp._autoscale_one_(control, RE=None), auto)
    assert auto.lurange.get() == 2
    # 4->3, 3->2, then one more read where it stays at 2 == convergence
    assert auto.reads == 3
    assert auto.reads < arp.DEFAULT_MAX_ITERATIONS


def test_default_iterations_cover_the_whole_range_table():
    """Worst case, range 0 to range 4, still converges inside the default."""
    control, auto = _make(target_range=4, start_range=0)
    run(arp._autoscale_one_(control, RE=None), auto)
    assert auto.lurange.get() == 4
    assert auto.reads <= arp.DEFAULT_MAX_ITERATIONS


def test_the_channel_is_selected_before_anything_else():
    """One Range serves all channels, so this must happen first."""
    control, auto = _make(channel=4, nickname="TRD")
    seen = run(arp._autoscale_one_(control, RE=None), auto)
    assert ("set_channel", 4) in seen
    assert seen.index(("set_channel", 4)) < seen.index("trigger")
    assert auto.channel.get() == 4


def test_converged_range_is_remembered_and_seeds_the_next_call():
    """Second call starts from the remembered range instead of walking."""
    control, auto = _make(target_range=2, start_range=4)
    run(arp._autoscale_one_(control, RE=None), auto)
    assert arp._last_range_[("fx4", 1)] == 2
    first_reads = auto.reads

    auto.lurange.value = 4  # something else moved the range meanwhile
    auto.reads = 0
    seen = run(arp._autoscale_one_(control, RE=None), auto)
    assert ("set_range", 2) in seen  # seeded, not walked
    assert auto.reads < first_reads


def test_memory_is_per_channel_not_per_box():
    """UPD and TRD share one sequence program but need different ranges."""
    upd, upd_auto = _make(target_range=1, start_range=1, nickname="UPD", channel=1)
    trd, trd_auto = _make(target_range=4, start_range=4, nickname="TRD", channel=4)
    trd.quadem = upd.quadem  # same electrometer, as in the real instrument

    run(arp._autoscale_one_(upd, RE=None), upd_auto)
    run(arp._autoscale_one_(trd, RE=None), trd_auto)

    assert arp._last_range_[("fx4", 1)] == 1
    assert arp._last_range_[("fx4", 4)] == 4


def test_mode_is_automatic_during_and_manual_after():
    """Leaving it automatic would let the IOC re-range mid-scan."""
    control, auto = _make()
    run(arp._autoscale_one_(control, RE=None), auto)
    assert auto.mode.get() == FX4AutorangeSettings.manual


def test_count_time_is_restored():
    """The trial count time must not leak into the measurement that follows."""
    control, auto = _make()
    control.quadem.averaging_time.value = 3.0
    run(arp._autoscale_one_(control, RE=None), auto)
    assert control.quadem.averaging_time.get() == pytest.approx(3.0)


def test_non_convergence_is_reported_not_raised_outside_user_operations():
    """A range that never settles must not abort a scan by itself."""
    control, auto = _make()

    def never_settles():
        auto.reads += 1
        auto.lurange.value = auto.reads % 5  # keeps moving

    auto.on_read = never_settles
    run(arp._autoscale_one_(control, RE=None), auto)  # RE=None: must not raise
    assert ("fx4", 1) not in arp._last_range_  # nothing to remember


def test_enable_autorange_selects_the_channel_before_arming():
    """Arming without selecting the channel ranges whichever was last chosen.

    That is the UPD/TRD failure mode: after a transmission measurement the
    sequence program points at TRD, and a UPD scan armed without re-selecting
    would range for the transmitted beam.
    """
    from usaxs.plans.fx4_setup import enable_fx4_autorange

    control, auto = _make(nickname="UPD", channel=1)
    auto.channel.value = 4  # left on TRD by a transmission measurement

    seen = run(enable_fx4_autorange(control, "automatic"), auto)

    assert auto.channel.get() == 1
    assert ("set_channel", 1) in seen
    assert seen.index(("set_channel", 1)) < seen.index("set")
    assert auto.mode.get() == "automatic"


def test_enable_autorange_is_a_noop_for_a_fixed_range_detector():
    """I0 and I00 have no sequence program to arm."""
    from usaxs.plans.fx4_setup import enable_fx4_autorange

    control, auto = _make(nickname="I0", channel=1)
    control.auto = None
    assert list(enable_fx4_autorange(control, "automatic")) == []


# --- seq01:dir, the range-movement direction -------------------------------


def test_autoscale_clears_the_direction_before_converging():
    """The convergence loop has to be free to walk the table both ways.

    ``seq01:dir`` is autosaved in the IOC, so a tune or transmission
    measurement that left it on "Increase" would otherwise stop the loop
    reaching a finer range -- and this is one of the two paths that undoes
    that.
    """
    control, auto = _make(target_range=4, start_range=0)
    auto.direction.value = FX4AutorangeDirection.increase

    run(arp._autoscale_one_(control, RE=None), auto)

    assert auto.direction.get() == FX4AutorangeDirection.both
    assert auto.lurange.get() == 4  # reached the finer range despite the seed


def test_enable_autorange_writes_the_direction_before_the_mode():
    """The IOC reads ``dir`` inside ``checkRange``, after a completed read.

    Setting it before ``mode`` means no read can slip through under the
    previous direction.
    """
    from usaxs.plans.fx4_setup import enable_fx4_autorange

    control, auto = _make()
    writes = []
    for msg in enable_fx4_autorange(control, "automatic", "Increase"):
        if getattr(msg, "command", None) == "set":
            writes.append((msg.obj, msg.args[0]))
            msg.obj.put(msg.args[0])

    assert writes == [
        (auto.direction, FX4AutorangeDirection.increase),
        (auto.mode, "automatic"),
    ]


def test_enable_autorange_defaults_to_both_directions():
    """Every call site that does not ask for a hold must clear one."""
    from usaxs.plans.fx4_setup import enable_fx4_autorange

    control, auto = _make()
    auto.direction.value = FX4AutorangeDirection.increase

    run(enable_fx4_autorange(control, "auto+background"), auto)

    assert auto.direction.get() == FX4AutorangeDirection.both


def _registry(monkeypatch, upd, i0):
    """Point the oregistry lookups inside fx4_setup at fake controls."""
    monkeypatch.setattr(
        "apsbits.core.instrument_init.oregistry",
        {"upd_controls": upd, "I0_controls": i0},
    )


def test_hold_for_peak_holds_only_the_fitted_detector(monkeypatch):
    """tune_ar fits on UPD, so I0's program must stay free to range."""
    from usaxs.plans.fx4_setup import autorange_hold_for_peak

    upd, upd_auto = _make(nickname="UPD", channel=1)
    i0, i0_auto = _make(nickname="I0", channel=1)
    i0.quadem = FakeQuadEM("fx42", i0_auto)
    _registry(monkeypatch, upd, i0)

    run(autorange_hold_for_peak(upd), upd_auto)

    assert upd_auto.direction.get() == FX4AutorangeDirection.increase
    assert i0_auto.direction.get() == FX4AutorangeDirection.both
    assert upd_auto.mode.get() == "automatic"
    assert i0_auto.mode.get() == "automatic"


def test_hold_for_peak_follows_the_fitted_detector_not_upd(monkeypatch):
    """tune_mr fits the rocking curve on I0, on the other electrometer."""
    from usaxs.plans.fx4_setup import autorange_hold_for_peak

    upd, upd_auto = _make(nickname="UPD", channel=1)
    i0, i0_auto = _make(nickname="I0", channel=1)
    i0.quadem = FakeQuadEM("fx42", i0_auto)
    _registry(monkeypatch, upd, i0)

    run(autorange_hold_for_peak(i0), i0_auto)

    assert i0_auto.direction.get() == FX4AutorangeDirection.increase
    assert upd_auto.direction.get() == FX4AutorangeDirection.both
    # usxFX4's shared channel is still left on the scattered beam.
    assert upd_auto.channel.get() == 1


def test_held_program_will_not_climb_but_still_drops(monkeypatch):
    """The whole point: hold the gain, but keep the escape from a railed range.

    Mirrors ``checkRange`` -- ``Increase`` blocks ``reqrange++`` only.
    """
    from usaxs.plans.fx4_setup import autorange_hold_for_peak

    upd, upd_auto = _make(nickname="UPD", channel=1)
    i0, i0_auto = _make(nickname="I0", channel=1)
    i0.quadem = FakeQuadEM("fx42", i0_auto)
    _registry(monkeypatch, upd, i0)
    run(autorange_hold_for_peak(upd), upd_auto)

    # Signal falls: the program would like a finer range but may not take it.
    upd_auto.lurange.value, upd_auto.target_range = 2, 4
    upd_auto.on_read()
    assert upd_auto.lurange.get() == 2

    # Signal rails: dropping to a coarser range is never blocked.
    upd_auto.target_range = 0
    upd_auto.on_read()
    assert upd_auto.lurange.get() == 1
