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
        self.max_dark_error = FakeSignal(0.5)
        self.dark_count_time = FakeSignal(0.2)
        self.ranges = FakeRanges()
        self.target_range = target_range
        self.reads = 0

    def setRange(self, target):
        """Plan: seed the range, as the real device does."""
        self.reqrange.value = int(target)
        self.lurange.value = int(target)
        if getattr(self, "quadem", None) is not None:
            self.quadem.em_range.value = RANGE_LABELS[int(target)]
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
        auto.quadem = self
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


# --- measure_background ----------------------------------------------------


class SequenceSignal(FakeSignal):
    """Reading that advances through *values* on every trigger."""

    def __init__(self, values):
        """Store the readings to hand out, one per trigger."""
        super().__init__(values[0])
        self.values = list(values)
        self.index = -1

    def advance(self):
        """Move to the next reading (repeating the last one at the end)."""
        self.index = min(self.index + 1, len(self.values) - 1)
        self.value = self.values[self.index]


def _dark_setup(monkeypatch, readings):
    """Return (control, auto, notes) with mode plans and Obsidian stubbed."""
    calls = []
    notes = []

    def fake_scaler_mode(det, count_time):
        calls.append("scaler_mode")
        calls.append(count_time)
        yield ("scaler_mode", det.name)

    def fake_monitor_mode(det):
        calls.append("monitor_mode")
        yield ("monitor_mode", det.name)

    monkeypatch.setattr(arp, "fx4_scaler_mode", fake_scaler_mode)
    monkeypatch.setattr(arp, "fx4_monitor_mode", fake_monitor_mode)
    monkeypatch.setattr(arp, "_safe_append", notes.append)
    # Keep tests from appending to the real /share1 dark-current record.
    monkeypatch.setattr(arp, "_record_dark", lambda *args: None)

    control, auto = _make(start_range=2)
    auto.mode.value = FX4AutorangeSettings.auto_background
    control.signal = SequenceSignal(readings)
    auto.ranges.range4.background.value = 1.9
    auto.ranges.range4.background_error.value = 0.05
    original_on_read = auto.on_read

    def on_read():
        original_on_read()
        control.signal.advance()

    auto.on_read = on_read
    return control, auto, notes, calls


def _good(n):
    return [2.0 + 0.01 * ((i % 5) - 2) for i in range(n)]


def test_dark_discards_the_first_readings(monkeypatch):
    """Two wild readings up front never reach the statistics."""
    n = arp.DARK_DISCARD_READINGS
    readings = [-50.0, 80.0][:n] + _good(arp.DARK_NUM_READINGS)
    control, auto, notes, _ = _dark_setup(monkeypatch, readings)
    run(arp._measure_background_one_(control), auto)
    assert auto.ranges.range4.background.value == pytest.approx(2.0, abs=0.01)
    assert auto.ranges.range4.background_error.value < 0.05
    assert notes == []


def test_dark_rejects_a_transient_and_stores_the_clean_mean(monkeypatch):
    """One glitched reading among the counted ones is rejected, not averaged."""
    good = _good(arp.DARK_NUM_READINGS)
    good[4] = -15.0
    readings = _good(arp.DARK_DISCARD_READINGS) + good
    control, auto, notes, _ = _dark_setup(monkeypatch, readings)
    run(arp._measure_background_one_(control), auto)
    assert auto.ranges.range4.background.value == pytest.approx(2.0, abs=0.01)
    assert notes == []


def test_dark_retries_after_a_noisy_attempt(monkeypatch):
    """A noisy first attempt is retried and the clean second one stored."""
    per_attempt = arp.DARK_DISCARD_READINGS + arp.DARK_NUM_READINGS
    noisy = [(-1) ** i * 6.0 + 0.3 * i for i in range(per_attempt)]
    readings = noisy + _good(per_attempt)
    control, auto, notes, _ = _dark_setup(monkeypatch, readings)
    run(arp._measure_background_one_(control), auto)
    assert auto.ranges.range4.background.value == pytest.approx(2.0, abs=0.01)
    assert auto.reads == 2 * per_attempt
    assert notes == []


def test_dark_keeps_the_previous_value_when_every_attempt_fails(monkeypatch):
    """Never overwrite a good dark with a bad one; say so in the notebook."""
    per_attempt = arp.DARK_DISCARD_READINGS + arp.DARK_NUM_READINGS
    total = per_attempt * arp.DARK_MAX_ATTEMPTS
    noisy = [(-1) ** i * 6.0 + 0.3 * i for i in range(total)]
    control, auto, notes, _ = _dark_setup(monkeypatch, noisy)
    run(arp._measure_background_one_(control), auto)
    assert auto.ranges.range4.background.value == 1.9
    assert auto.ranges.range4.background_error.value == 0.05
    assert auto.reads == total
    assert len(notes) == 1 and "Dark Current Rejected" in notes[0]


def test_dark_configures_scaler_mode_first_and_restores_after(monkeypatch):
    """CallbacksBlock comes from scaler mode; mode and count time come back."""
    readings = _good(arp.DARK_DISCARD_READINGS + arp.DARK_NUM_READINGS)
    control, auto, _notes, calls = _dark_setup(monkeypatch, readings)
    seen = run(arp._measure_background_one_(control), auto)
    assert calls == ["scaler_mode", 0.2, "monitor_mode"]
    assert seen.index(("scaler_mode", "fx4")) < seen.index("trigger")
    assert auto.mode.value == FX4AutorangeSettings.auto_background
    assert control.quadem.averaging_time.value == 1.0
    assert auto.lurange.value == arp.MOST_SENSITIVE_RANGE


RANGE_LABELS = ["1 mA", "100 uA", "10 uA", "1 uA slow", "100 nA fast"]
"""FX4 ``Range`` labels for sequence-program indices 0..4."""


def test_dark_waits_for_the_range_before_reading(monkeypatch):
    """No trigger until the FX4's own Range_RBV shows the requested range."""
    readings = _good(arp.DARK_DISCARD_READINGS + arp.DARK_NUM_READINGS)
    control, auto, _notes, _ = _dark_setup(monkeypatch, readings)
    control.quadem.em_range.value = RANGE_LABELS[0]

    def slow_set_range(target):
        # lurange is NOT updated in manual mode (the IOC clears the event).
        auto.reqrange.value = int(target)
        yield ("set_range", int(target))

    polls = {"n": 0}

    def em_range_get(**kwargs):
        polls["n"] += 1
        if polls["n"] >= 3:
            control.quadem.em_range.value = RANGE_LABELS[auto.reqrange.value]
        return control.quadem.em_range.value

    auto.setRange = slow_set_range
    control.quadem.em_range.get = em_range_get
    seen = run(arp._measure_background_one_(control), auto)
    first_trigger = seen.index("trigger")
    assert seen[:first_trigger].count("sleep") >= 2
    assert auto.ranges.range4.background.value == pytest.approx(2.0, abs=0.01)


def test_dark_on_the_wrong_range_is_never_stored(monkeypatch):
    """If the FX4 never reaches the range, nothing is measured or written."""
    readings = _good(arp.DARK_DISCARD_READINGS + arp.DARK_NUM_READINGS)
    control, auto, _notes, _ = _dark_setup(monkeypatch, readings)

    def stuck_set_range(target):
        auto.reqrange.value = int(target)
        yield ("set_range", int(target))

    auto.setRange = stuck_set_range
    control.quadem.em_range.value = RANGE_LABELS[0]
    seen = run(arp._measure_background_one_(control), auto)
    assert "trigger" not in seen
    assert auto.ranges.range4.background.value == 1.9
    assert auto.ranges.range4.background_error.value == 0.05


def test_seq_range_full_scale_matches_the_fx4_labels():
    """Index 0 is 1 mA, index 4 is 100 nA; 'fast'/'slow' do not matter."""
    from usaxs.utils.fx4_ranges import full_scale_pA

    for index, label in enumerate(RANGE_LABELS):
        assert arp.seq_range_full_scale_pA(index) == full_scale_pA(label)


# --- measure_background_if_stale -------------------------------------------


class StampedSignal(FakeSignal):
    """FakeSignal with a Channel Access-style ``timestamp``."""

    def __init__(self, value=0, timestamp=0.0):
        """Store value and timestamp."""
        super().__init__(value)
        self.timestamp = timestamp


def _stale_setup(monkeypatch, upd_age_s, i0_age_s, now=1.0e6):
    """Two boxes with darks of the given ages; measure_background recorded."""
    measured = []

    def fake_measure(controls, shutter=None, note=""):
        measured.append(([c.nickname for c in controls], shutter))
        yield ("measure", tuple(c.nickname for c in controls))

    monkeypatch.setattr(arp, "measure_background", fake_measure)
    upd, upd_auto = _make(nickname="UPD")
    i0_auto = FakeAuto()
    i0 = FakeControls("I0", FakeQuadEM("fx42", i0_auto), 1, i0_auto)
    upd_auto.ranges.range4.background = StampedSignal(2.0, now - upd_age_s)
    i0_auto.ranges.range4.background = StampedSignal(2.0, now - i0_age_s)
    return [upd, i0], measured, now


def test_fresh_darks_are_left_alone(monkeypatch):
    """Nothing stale: no messages at all, not even a checkpoint."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 3600, 7200)
    msgs = list(arp.measure_background_if_stale(controls, 3 * 3600, now=now))
    assert msgs == [] and measured == []


def test_only_the_stale_box_is_measured(monkeypatch):
    """UPD 4 h old is re-measured; I0 1 h old is not."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 4 * 3600, 3600)
    msgs = list(
        arp.measure_background_if_stale(controls, 3 * 3600, shutter="sh", now=now)
    )
    assert measured == [(["UPD"], "sh")]
    assert msgs[-1].command == "checkpoint"


def test_a_failed_dark_is_not_retried_on_every_scan(monkeypatch):
    """The timestamp stays old after a rejection; the back-off holds retries."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 4 * 3600, 4 * 3600)
    list(arp.measure_background_if_stale(controls, 3 * 3600, now=now))
    list(arp.measure_background_if_stale(controls, 3 * 3600, now=now + 600))
    assert len(measured) == 1
    later = now + arp.DARK_RETRY_BACKOFF_S + 1
    list(arp.measure_background_if_stale(controls, 3 * 3600, now=later))
    assert len(measured) == 2


def test_unreadable_timestamp_counts_as_stale(monkeypatch):
    """No timestamp means unknown age, which must not mean fresh."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 3600, 3600)
    controls[0].auto.ranges.range4.background.timestamp = 0.0
    list(arp.measure_background_if_stale(controls, 3 * 3600, now=now))
    assert measured == [(["UPD"], None)]


def test_zero_age_limit_disables_the_check(monkeypatch):
    """DARK_CURRENT_MAX_AGE_H = 0 turns it off."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 1e9, 1e9)
    assert list(arp.measure_background_if_stale(controls, 0, now=now)) == []
    assert measured == []


def test_a_deferred_dark_is_measured_even_when_fresh(monkeypatch):
    """force=True: the command file skipped it after a tune, so do it now."""
    arp._last_dark_attempt_.clear()
    controls, measured, now = _stale_setup(monkeypatch, 600, 600)
    list(arp.measure_background_if_stale(controls, 3 * 3600, now=now, force=True))
    assert measured == [(["UPD", "I0"], None)]
