"""Lifecycle of the sample metadata: set, update, clear, binding, exposure.

Runs a real RunEngine against a stand-in for ``sample_data`` built from the
schema (ophyd soft ``Signal`` s with the same NaN-safe ``set``), so no EPICS
or ``apsbits`` is needed.  A fake clock replaces ``time`` inside
``usaxs.plans.sample_metadata`` only.

    PYTHONPATH=src python -m pytest tests/test_sample_metadata.py -v
"""

import inspect
import math
import types

import pytest
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from ophyd import Component
from ophyd import Device
from ophyd import Signal

from usaxs.devices.sample_data import NanSafeSetMixin
from usaxs.plans import sample_metadata as sm
from usaxs.utils import sample_metadata_schema as schema


class NanSafeSignal(NanSafeSetMixin, Signal):
    """Soft signal that, like the device's, can be set to NaN."""


FakeSampleData = type(
    "FakeSampleData",
    (Device,),
    {
        **{f.name: Component(NanSafeSignal, value=f.unset) for f in schema.FIELDS},
        "shutter_open": Component(Signal, value=0, kind="omitted"),
    },
)


class Clock:
    """Settable clock standing in for ``time.time``."""

    def __init__(self, t=1_000_000.0):
        """Start the clock at ``t`` (epoch seconds)."""
        self.t = t

    def __call__(self):
        """Return the current fake time."""
        return self.t


@pytest.fixture
def clock(monkeypatch):
    """Fake clock for the module's ``time``, and a fresh X-ray accumulator."""
    c = Clock()
    monkeypatch.setattr(sm, "time", types.SimpleNamespace(time=c))
    monkeypatch.setattr(sm, "xray_exposure", sm.XrayExposureAccumulator(clock=c))
    monkeypatch.setattr(sm, "_depth", 0)
    return c


@pytest.fixture
def dev(clock):
    """Stand-in ``sample_data`` device, registered with the module."""
    device = FakeSampleData(name="sample_data")
    sm.set_sample_data_device(device)
    yield device
    sm.set_sample_data_device(None)


@pytest.fixture
def notes(monkeypatch):
    """Capture Obsidian lines instead of writing them."""
    captured = []
    monkeypatch.setattr(sm, "_note", captured.append)
    return captured


@pytest.fixture
def RE():
    """A RunEngine without the SIGINT handler."""
    return RunEngine({}, context_managers=[])


def run(RE, plan):
    """Run ``plan`` and return its return value."""
    box = []

    def capture():
        box.append((yield from plan))

    RE(capture())
    return box[0]


def values(dev, fields):
    """Current values of ``fields`` on ``dev``."""
    return {f.name: getattr(dev, f.name).get() for f in fields}


def assert_unset(dev, fields):
    """Assert every one of ``fields`` holds its unset value."""
    for f in fields:
        value = getattr(dev, f.name).get()
        if f.kind in ("float", "int"):
            assert math.isnan(value), f.name
        else:
            assert value == f.unset, f.name


# --- set / update / clear -----------------------------------------------------


def test_set_replaces_sample_scope_only(RE, dev):
    """Unnamed sample fields are cleared; environment fields stay."""
    dev.concentration.put(9.0)
    dev.ramp_rate.put(20.0)
    run(RE, sm.set_sample_metadata("PS_film", density=1.05, description="PS 50k"))

    assert dev.density.get() == 1.05
    assert dev.description.get() == "PS 50k"
    assert math.isnan(dev.concentration.get())  # replaced, not merged
    assert dev.ramp_rate.get() == 20.0  # environment untouched
    assert dev.meta_state.get() == "Set"
    assert dev.bound_title.get() == "PS_film"
    assert dev.meta_owner.get() == "manual"


def test_update_environment_replaces_environment_only(RE, dev):
    """Unnamed environment fields are cleared; sample fields stay."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    run(RE, sm.update_environment(procedure_step="heat", ramp_rate=20))
    run(RE, sm.update_environment(temperature=150.2))

    assert math.isnan(dev.ramp_rate.get())  # last segment's value is gone
    assert dev.procedure_step.get() == ""
    assert dev.temperature.get() == 150.2
    assert dev.density.get() == 1.05  # sample untouched


def test_clear_unsets_everything(RE, dev):
    """Clear leaves every field unset and MetaState Unset."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    run(RE, sm.update_environment(env_type="Linkam", step_index=2))
    run(RE, sm.clear_sample_metadata())

    assert_unset(dev, schema.FIELDS)
    assert dev.meta_state.get() == "Unset"


def test_clear_touches_only_sample_data(RE, dev):
    """A clear writes only usxSample fields, so never the thickness."""
    touched = []
    RE.msg_hook = lambda msg: msg.command == "set" and touched.append(msg.obj)
    run(RE, sm.clear_sample_metadata())
    assert len(touched) == len(schema.FIELDS)
    assert all(obj.parent is dev for obj in touched)


def test_bad_names_and_values_are_rejected(RE, dev):
    """Typos, unknown states, fractional indices and blank titles raise."""
    with pytest.raises(ValueError):
        run(RE, sm.update_environment(no_such_field=1))
    with pytest.raises(ValueError):
        run(RE, sm.update_environment(env_type="Furnace"))
    with pytest.raises(ValueError):
        run(RE, sm.update_environment(step_index=2.5))
    with pytest.raises(ValueError):
        run(RE, sm.set_sample_metadata("blank_kapton", density=1))


def test_long_strings_are_truncated(RE, dev):
    """A string longer than its record is cut, not rejected."""
    run(RE, sm.update_environment(procedure_step="x" * 60))
    assert dev.procedure_step.get() == "x" * schema.STRINGOUT_MAX


def test_signature_lists_every_sample_field():
    """The queueserver builds its form from the signature."""
    params = inspect.signature(sm.set_sample_metadata).parameters
    for f in sm.SAMPLE_FIELDS:
        assert f.name in params, f.name


def test_reset_all_is_clear(RE, dev):
    """The device's old resetAll() now clears instead of writing 25 C."""
    from usaxs.devices.sample_data import SampleDataDevice

    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    run(RE, SampleDataDevice.resetAll(dev))
    assert_unset(dev, schema.FIELDS)


# --- binding rule ---------------------------------------------------------------


@pytest.mark.parametrize("title", ["blank", "Blank_kapton", "air BLANK"])
def test_blank_clears(RE, dev, notes, title):
    """A blank title clears everything, silently."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    run(RE, sm.update_environment(temperature=25))
    assert run(RE, sm.check_sample_binding(title)) is None
    assert_unset(dev, schema.FIELDS)
    assert not notes  # a blank is routine, not a warning


def test_different_sample_clears_and_notes(RE, dev, notes):
    """A title outside the binding clears, with one Obsidian line."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    key = run(RE, sm.check_sample_binding("Glassy_carbon"))
    assert key == "Glassy_carbon"
    assert_unset(dev, sm.SAMPLE_FIELDS)
    assert dev.meta_state.get() == "Unset"
    assert len(notes) == 1 and "'PS_film'" in notes[0]


def test_same_sample_keeps(RE, dev, notes):
    """A title starting with BoundTitle keeps the metadata."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    key = run(RE, sm.check_sample_binding("PS_film_200C_22min"))
    assert key == "PS_film"
    assert dev.density.get() == 1.05
    assert dev.meta_state.get() == "Set"
    assert not notes


def test_nothing_bound_keeps_nothing(RE, dev, notes):
    """With nothing set, a scan neither clears nor warns."""
    assert run(RE, sm.check_sample_binding("Glassy_carbon")) == "Glassy_carbon"
    assert not notes


def test_finalize_clears_after_abort(RE, dev):
    """A template's finalize_wrapper clears even when the body fails."""
    ttl = NanSafeSignal(name="uv_ttl", value=0)

    def body():
        yield from sm.set_sample_metadata("PS_film", density=1.05)
        yield from bps.mv(ttl, 1)
        raise RuntimeError("simulated abort")

    with pytest.raises(RuntimeError):
        RE(bpp.finalize_wrapper(body(), sm.end_sample_metadata(ttl)))
    assert ttl.get() == 0  # source off
    assert dev.meta_state.get() == "Unset"
    assert_unset(dev, schema.FIELDS)


# --- snapshot and decorator ---------------------------------------------------


def test_snapshot_keeps_only_set_fields(RE, dev):
    """The start-document snapshot carries set fields only, no NaN."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05, magnetic_field=0.5))
    run(RE, sm.update_environment(step_index=3))
    snap = run(RE, sm.sample_metadata_snapshot())
    assert snap["density"] == 1.05
    assert snap["step_index"] == 3 and isinstance(snap["step_index"], int)
    assert snap["magnetic_field_dir"] == "X"  # kept: its field is set
    assert "stress_field_dir" not in snap  # dropped: its field is unset
    assert "concentration" not in snap
    assert snap["meta_state"] == "Set"
    assert not any(isinstance(v, float) and math.isnan(v) for v in snap.values())


def test_decorator_checks_once_and_fills_md(RE, dev, notes):
    """Only the outermost plan checks; its md gains the snapshot."""
    seen = []

    @sm.sample_metadata_checked
    def inner(pos_X, pos_Y, thickness, title, md=None):
        seen.append(("inner", md))
        yield from bps.null()

    @sm.sample_metadata_checked
    def outer(pos_X, pos_Y, thickness, title, md=None):
        seen.append(("outer", md))
        yield from inner(pos_X, pos_Y, thickness, title, md=md)

    run(RE, sm.set_sample_metadata("PS_film", density=1.05))
    run(RE, outer(0, 0, 1, "PS_film_25C_0min", md={"user": "x"}))

    assert seen[0][1]["sample_metadata"]["density"] == 1.05
    assert seen[0][1]["user"] == "x"
    assert seen[1][1] is seen[0][1]  # inner passed through untouched
    assert sm._depth == 0


def test_decorator_signature_preserved():
    """Queueserver validates plan parameters with inspect.signature()."""

    @sm.sample_metadata_checked
    def plan(pos_X, pos_Y, thickness, title, md=None):
        yield from bps.null()

    assert list(inspect.signature(plan).parameters) == [
        "pos_X",
        "pos_Y",
        "thickness",
        "title",
        "md",
    ]


# --- X-ray self-exposure --------------------------------------------------------


def test_accumulator_counts_open_time_inside_window_only():
    """Open time counts only between begin() and end()."""
    c = Clock(0.0)
    acc = sm.XrayExposureAccumulator(clock=c)
    acc.shutter_changed(value=1)  # open, but no data plan running
    c.t = 10
    acc.begin("A")
    c.t = 15
    acc.shutter_changed(value=0)
    c.t = 20
    acc.shutter_changed(value=1.0)
    c.t = 23
    acc.end()
    c.t = 100
    assert acc.total("A") == pytest.approx(8.0)  # 10..15 + 20..23
    acc.shutter_changed(value=float("nan"))  # disconnected reads as closed
    acc.begin("A")
    c.t = 200
    assert acc.total("A") == pytest.approx(8.0)


def test_xray_exposure_per_sample(RE, dev, clock, notes):
    """Blanks don't add, a blank doesn't reset, a reset flag does."""

    @sm.sample_metadata_checked
    def scan(pos_X, pos_Y, thickness, title, md=None):
        sm.xray_exposure.shutter_changed(value=1)
        clock.t += 30
        sm.xray_exposure.shutter_changed(value=0)
        yield from bps.null()

    run(RE, sm.set_sample_metadata("PS_film"))
    run(RE, scan(0, 0, 1, "PS_film_25C_0min"))
    assert dev.xray_exposure_time.get() == 0.0  # before this scan
    run(RE, scan(0, 0, 1, "blank"))
    assert sm.xray_exposure.total("blank") == 0.0
    run(RE, sm.set_sample_metadata("PS_film"))  # a template re-binds after a blank
    run(RE, scan(0, 0, 1, "PS_film_25C_5min"))
    assert dev.xray_exposure_time.get() == pytest.approx(30.0)
    assert sm.xray_exposure.total("PS_film") == pytest.approx(60.0)

    run(RE, sm.set_sample_metadata("PS_film", reset_xray_exposure=True))
    assert sm.xray_exposure.total("PS_film") == 0.0


def test_blank_stops_an_open_count(RE, dev, clock):
    """A blank never inherits the previous sample's counting window."""
    sm.xray_exposure.begin("PS_film")
    run(RE, sm.check_sample_binding("blank"))
    sm.xray_exposure.shutter_changed(value=1)
    clock.t += 40
    assert sm.xray_exposure.total("PS_film") == 0.0


def test_xray_exposure_switches_key_with_the_sample(RE, dev, clock, notes):
    """A different sample counts under its own key."""

    @sm.sample_metadata_checked
    def scan(pos_X, pos_Y, thickness, title, md=None):
        sm.xray_exposure.shutter_changed(value=1)
        clock.t += 10
        sm.xray_exposure.shutter_changed(value=0)
        yield from bps.null()

    run(RE, sm.set_sample_metadata("A"))
    run(RE, scan(0, 0, 1, "A_1"))
    run(RE, scan(0, 0, 1, "B"))  # different sample: clears, counts for "B"
    assert sm.xray_exposure.total("A") == pytest.approx(10.0)
    assert sm.xray_exposure.total("B") == pytest.approx(10.0)


# --- SampleState ------------------------------------------------------------------


def test_state_adopts_ioc_values_for_same_title(RE, dev):
    """Values typed for the same title are adopted; plan args win."""
    run(RE, sm.set_sample_metadata("PS_film", density=1.05, concentration=0.1))
    state = run(
        RE, sm.SampleState.start("PS_film", sample_fields={"concentration": 0.2})
    )
    assert state.sample_fields == {"density": 1.05, "concentration": 0.2}
    assert dev.density.get() == 1.05 and dev.concentration.get() == 0.2


def test_state_ignores_ioc_values_for_other_title(RE, dev):
    """Values bound to another title are not adopted."""
    run(RE, sm.set_sample_metadata("Other", density=1.05))
    state = run(
        RE, sm.SampleState.start("PS_film", sample_fields={"volume_fraction": 0.3})
    )
    assert state.sample_fields == {"volume_fraction": 0.3}
    assert math.isnan(dev.density.get())


def test_blank_in_a_template_loop_then_full_rewrite(RE, dev, clock, notes):
    """After a blank clears, prepare_scan writes the full set again."""
    state = run(
        RE,
        sm.SampleState.start(
            "PS_film",
            env="Linkam",
            title_format=sm.TITLE_TEMPERATURE_TIME,
            temperature_source="linkam_tc1",
            sample_fields={"density": 1.05},
        ),
    )
    run(RE, state.prepare_scan(step="hold", step_index=2, temperature=199.8))
    run(RE, sm.check_sample_binding("blank"))
    assert_unset(dev, schema.FIELDS)

    clock.t += 120
    title = run(RE, state.prepare_scan(step="hold", step_index=2, temperature=200.1))
    assert title == "PS_film_200C_2min"
    assert dev.density.get() == 1.05
    assert dev.env_type.get() == "Linkam"
    assert dev.procedure_step.get() == "hold"
    assert dev.step_index.get() == 2
    assert dev.elapsed_time.get() == pytest.approx(120)
    assert dev.bound_title.get() == "PS_film"
    assert run(RE, sm.check_sample_binding(title)) == "PS_film"  # kept


def test_prepare_scan_replaces_environment(RE, dev):
    """A hold after a heat leaves no ramp rate or setpoint behind."""
    state = run(RE, sm.SampleState.start("S", env="Linkam"))
    run(RE, state.prepare_scan(step="heat", ramp_rate=20, setpoint=200, temperature=80))
    run(RE, state.prepare_scan(step="hold", temperature=200))
    assert math.isnan(dev.ramp_rate.get())
    assert math.isnan(dev.temperature_setpoint.get())


def drive(gen):
    """Run a plan that yields nothing (debug mode) and return its value."""
    try:
        msg = next(gen)
    except StopIteration as stop:
        return stop.value
    raise AssertionError(f"debug plan yielded {msg}")


# Each case: title format, prepare_scan kwargs, and the template's old f-string.
OLD_TITLES = [
    (
        sm.TITLE_TEMPERATURE_TIME,
        {"temperature": 199.5},
        lambda base, T, m, **kw: f"{base}_{T:.0f}C_{m:.0f}min",
    ),
    (sm.TITLE_TIME, {}, lambda base, T, m, **kw: f"{base}_{m:.0f}min"),
    (sm.TITLE_INDEX, {"index": 7}, lambda base, T, m, **kw: f"{base}_{7}"),
    (
        sm.TITLE_RHEOMETER,
        {"sx": 1.234, "sy": -0.5, "phase": "pre", "index": 3},
        lambda base, T, m, **kw: (
            f"{base}_sx{1.234:.2f}_sy{-0.5:.2f}_{'pre'}{3}_{m:.0f}min"
        ),
    ),
    (
        sm.TITLE_DEVICE_TIME,
        {"value": 12.6, "units": "N"},
        lambda base, T, m, **kw: f"{base}_{12.6:.0f}{'N'}_{m:.0f}min",
    ),
]


@pytest.mark.parametrize("fmt, kwargs, old", OLD_TITLES)
@pytest.mark.parametrize("elapsed_s", [0, 29.9, 30, 90, 150, 1319.9])
def test_titles_match_templates_byte_for_byte(clock, fmt, kwargs, old, elapsed_s):
    """Titles equal the templates' old f-strings, rounding included."""
    state = drive(sm.SampleState.start("My_sample", title_format=fmt, debug=True))
    clock.t = state.t0 + elapsed_s
    title = drive(state.prepare_scan(**kwargs))
    expected = old("My_sample", kwargs.get("temperature"), (clock.t - state.t0) / 60)
    assert title == expected


def test_debug_writes_nothing(RE, dev):
    """Debug mode returns titles without writing a PV."""
    state = drive(sm.SampleState.start("S", debug=True))
    drive(state.prepare_scan(temperature=25))
    assert_unset(dev, schema.FIELDS)


def test_exposure_time_is_cumulative(RE, dev, clock):
    """Exposure time sums the on-intervals; dose = intensity x time."""
    ttl = NanSafeSignal(name="uv_ttl", value=0)
    state = run(
        RE,
        sm.SampleState.start(
            "S",
            exposure={
                "exposure_type": "UV",
                "exposure_source": "365 nm LED",
                "exposure_wavelength": 365,
                "exposure_intensity": 2.0,
                "exposure_intensity_units": "mW/cm2",
                "exposure_dose_units": "mJ/cm2",
            },
            exposure_signal=ttl,
        ),
    )
    t_start = clock.t
    run(RE, state.set_exposure(True))
    clock.t += 100
    run(RE, state.set_exposure(False))
    clock.t += 50  # off: doesn't count
    run(RE, state.set_exposure(True))
    clock.t += 20
    run(RE, state.prepare_scan())

    assert ttl.get() == 1
    assert dev.exposure_on.get() == "On"
    assert dev.exposure_time.get() == pytest.approx(120)
    assert dev.exposure_dose.get() == pytest.approx(240)
    assert dev.exposure_start_time.get() == t_start
    assert dev.exposure_type.get() == "UV"
    assert dev.exposure_wavelength.get() == 365


def test_rheometer_pulses(RE, dev, clock):
    """Pulse count, last pulse time and phase are recorded."""
    state = run(RE, sm.SampleState.start("S", env="Rheometer"))
    state.record_pulse()
    clock.t += 5
    state.record_pulse()
    run(RE, state.prepare_scan(phase="post"))
    assert dev.rheo_pulse_count.get() == 2
    assert dev.rheo_last_pulse_time.get() == clock.t
    assert dev.rheo_phase.get() == "post"


def test_user_slots(RE, dev):
    """Generic key/value/units slots fill in order; at most four."""
    state = run(RE, sm.SampleState.start("S", env="Other"))
    run(RE, state.prepare_scan(user={"force": (12.5, "N"), "humidity": (40, "%")}))
    assert (dev.user_key1.get(), dev.user_value1.get(), dev.user_units1.get()) == (
        "force",
        12.5,
        "N",
    )
    assert dev.user_key2.get() == "humidity"
    assert dev.user_key3.get() == ""
    with pytest.raises(ValueError):
        run(RE, state.prepare_scan(user={str(n): (n, "") for n in range(5)}))
