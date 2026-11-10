"""
Sample metadata: set it, update it in situ, clear it, and check it per scan.

The ``usxSample:`` IOC is the single source of truth: the AD IOCs and the
fly-scan writer can only read PVs, so every value here goes to a PV and
nowhere else.  The field table, with each field's **scope**, is in
``usaxs.utils.sample_metadata_schema``.

Writes always replace a **whole scope** -- an unnamed field is cleared, never
left as it was -- so a stale value (last segment's ``ProcedureStep``, the
previous sample's concentration) cannot leak into the next file.

Plans
-----
``set_sample_metadata(title, **sample_fields)``
    Replace the *sample* scope and bind the metadata to ``title``.
``update_environment(**env_fields)``
    Replace the *environment* scope.  The in-situ operation.
``clear_sample_metadata()``
    Everything unset, ``MetaState = Unset``.  Never touches thickness.
``check_sample_binding(title)``
    The per-scan rule, run by the data plans through ``@sample_metadata_checked``:

    * a **blank** title ("blank", any case: Matilda's rule) clears everything;
    * a title that does **not start with** ``BoundTitle`` clears everything,
      with a warning and an Obsidian line;
    * a title that starts with ``BoundTitle`` (``PS_film_200C_22min`` under
      ``PS_film``) keeps it.
``end_sample_metadata(exposure_signal=None)``
    For a template's ``finalize_wrapper``: switch a UV/laser source off
    first, then clear.

``SampleState`` is what plan templates use: it keeps the sample's properties
in Python, rewrites the full set before every scan (so a blank in the loop
costs nothing), keeps the series and exposure bookkeeping, and returns the
scan title in the template's existing encoding.

X-ray self-exposure
-------------------
``usxLAX:userStringCalc10.VAL`` (``sample_data.shutter_open``) is 1 while the
last Uniblitz command was *open*.  ``start_xray_exposure_tracking()`` (called
by ``startup.py``) subscribes to it; open time is integrated **only while a
data plan is running** -- samples are out of the beam during tunes (Jan,
2026-11-10) -- and is kept per sample key: the bound title, or the scan title
when nothing is bound.  Blanks don't count.  Re-measuring a title continues
its count; ``set_sample_metadata(..., reset_xray_exposure=True)`` starts a
fresh spot, and ``newUser()`` clears all counts.

No import from ``usaxs.startup`` (see CLAUDE.md); the device comes from
``oregistry`` on first use, or from ``set_sample_data_device`` in tests.
"""

import functools
import inspect
import logging
import math
import threading
import time

from bluesky import plan_stubs as bps

from usaxs.utils import sample_metadata_schema as schema
from usaxs.utils.sample_metadata_schema import BOOKKEEPING
from usaxs.utils.sample_metadata_schema import ENVIRONMENT
from usaxs.utils.sample_metadata_schema import SAMPLE

logger = logging.getLogger(__name__)

SAMPLE_FIELDS = schema.fields_in_scope(SAMPLE)
ENVIRONMENT_FIELDS = schema.fields_in_scope(ENVIRONMENT)

# Title encodings used by the plan templates.  Users, Matilda and pyIrena
# parse these suffixes, so they must not change; tests pin each one.
TITLE_TIME = "{base}_{minutes:.0f}min"
TITLE_TEMPERATURE_TIME = "{base}_{temperature:.0f}C_{minutes:.0f}min"
TITLE_INDEX = "{base}_{index}"
TITLE_RHEOMETER = "{base}_sx{sx:.2f}_sy{sy:.2f}_{phase}{index}_{minutes:.0f}min"
TITLE_DEVICE_TIME = "{base}_{value:.0f}{units}_{minutes:.0f}min"

_sample_data = None


def set_sample_data_device(device):
    """Use ``device`` instead of ``oregistry["sample_data"]`` (tests)."""
    global _sample_data
    _sample_data = device


def _device():
    if _sample_data is None:
        from apsbits.core.instrument_init import oregistry

        return oregistry["sample_data"]
    return _sample_data


# --- values -----------------------------------------------------------------


def _coerce(field, value):
    """Validate one value for ``field``; ``None`` means unset."""
    if value is None:
        return field.unset
    if field.kind == "float":
        return float(value)
    if field.kind == "int":
        value = float(value)
        if not math.isnan(value) and value != int(value):
            raise ValueError(f"{field.name} must be a whole number, got {value!r}")
        return value
    if field.kind == "enum":
        if isinstance(value, int) and not isinstance(value, bool):
            if 0 <= value < len(field.choices):
                return field.choices[value]
        if str(value) not in field.choices:
            raise ValueError(
                f"{field.name} must be one of {field.choices}, got {value!r}"
            )
        return str(value)
    text = str(value)
    if len(text) > field.max_length:
        logger.warning(
            "%s truncated to %d characters: %r", field.name, field.max_length, text
        )
        text = text[: field.max_length]
    return text


def _resolve(values, scope):
    """Every field of ``scope``: the given value, or unset if not named."""
    fields = schema.fields_in_scope(scope)
    unknown = set(values) - {f.name for f in fields}
    if unknown:
        raise ValueError(f"not {scope} fields: {sorted(unknown)}")
    return {f.name: _coerce(f, values.get(f.name)) for f in fields}


def _is_unset(field, value):
    if value is None:
        return True
    if field.kind in ("float", "int"):
        return isinstance(value, float) and math.isnan(value)
    return value == field.unset


def _bookkeeping(state, owner="", bound_title=""):
    return _resolve(
        {
            "meta_state": state,
            "meta_owner": owner,
            "meta_set_time": time.time() if state == "Set" else None,
            "bound_title": bound_title,
        },
        BOOKKEEPING,
    )


def _write(values):
    """One ``bps.mv`` for all of ``values`` (``{field_name: value}``)."""
    device = _device()
    args = []
    for name, value in values.items():
        args += [getattr(device, name), value]
    if args:
        yield from bps.mv(*args)


def _note(text):
    """Append a line to the Obsidian notebook, never raising."""
    from usaxs.utils.obsidian_plan_log import _safe_append

    _safe_append(text)


# --- X-ray self-exposure ----------------------------------------------------


class XrayExposureAccumulator:
    """Shutter-open time per sample key, counted only inside data plans.

    ``shutter_changed`` is the CA monitor callback of the open/closed tracker.
    ``begin(key)`` / ``end()`` bracket a data plan.  The state is piecewise
    constant between events, so each event first credits the time since the
    previous one to the active key, if the shutter was open.  The monitor
    thread and the RunEngine thread both call in, hence the lock.
    """

    def __init__(self, clock=time.time):
        """Start with no counts, shutter closed, nobody counting."""
        self._clock = clock
        self._lock = threading.Lock()
        self._totals = {}
        self._key = None
        self._open = False
        self._last = clock()

    def _accrue(self):
        now = self._clock()
        if self._key is not None and self._open:
            self._totals[self._key] = (
                self._totals.get(self._key, 0.0) + now - self._last
            )
        self._last = now

    def shutter_changed(self, value=None, **kwargs):
        """Monitor callback: ``value`` is 1 while the shutter is open."""
        with self._lock:
            self._accrue()
            self._open = bool(value) and not (
                isinstance(value, float) and math.isnan(value)
            )

    def begin(self, key):
        """Start counting for ``key`` (``None``: count for nobody)."""
        with self._lock:
            self._accrue()
            self._key = key

    def end(self):
        """Stop counting."""
        self.begin(None)

    def total(self, key):
        """Seconds of open shutter counted for ``key`` so far."""
        with self._lock:
            self._accrue()
            return self._totals.get(key, 0.0)

    def reset(self, key=None):
        """Forget ``key``'s count, or every count if ``key`` is None."""
        with self._lock:
            self._accrue()
            if key is None:
                self._totals.clear()
            else:
                self._totals.pop(key, None)


xray_exposure = XrayExposureAccumulator()
_tracking = False


def start_xray_exposure_tracking():
    """Subscribe the accumulator to the shutter tracker.  Called by startup."""
    global _tracking
    if _tracking:
        return
    _device().shutter_open.subscribe(xray_exposure.shutter_changed, run=True)
    _tracking = True


# --- public plans -------------------------------------------------------------


def set_sample_metadata(
    title: str,
    owner: str = "manual",
    reset_xray_exposure: bool = False,
    description: str = None,
    chemical_formula: str = None,
    concentration: float = None,
    density: float = None,
    volume_fraction: float = None,
    scattering_length_density: float = None,
    magnetic_field: float = None,
    magnetic_field_dir: str = None,
    stress_field: float = None,
    stress_field_dir: str = None,
    electric_field: float = None,
    electric_field_dir: str = None,
    x_translation: float = None,
    rotation_angle: float = None,
):
    """Replace the sample properties and bind them to ``title``.

    Every sample property not given here is cleared.  Environment fields are
    untouched.  Scans whose title starts with ``title`` keep these values;
    any other title clears them (``check_sample_binding``).

    Parameters
    ----------
    title : str
        Base sample title, e.g. ``"PS_film"``.
    owner : str
        Who set it, recorded in ``MetaOwner``: a plan name, ``"manual"``,
        ``"command file"``.
    reset_xray_exposure : bool
        Start this title's X-ray exposure count from zero (a fresh spot).
    description, chemical_formula, ... : optional
        Sample properties; units are in ``sample_metadata_schema``.
    """
    arguments = locals()  # not inside the comprehension: that has its own scope
    given = {f.name: arguments[f.name] for f in SAMPLE_FIELDS}
    values = _resolve(given, SAMPLE)
    if not title or schema.is_blank_title(title):
        raise ValueError(f"cannot bind sample metadata to title {title!r}")
    if reset_xray_exposure:
        xray_exposure.reset(title)
    values.update(_bookkeeping("Set", owner, title))
    yield from _write(values)


def update_environment(**env_fields):
    """Replace the environment fields: what is being done to the sample now.

    Every environment field not given here is cleared.  Sample properties
    are untouched.  Field names and units are in ``sample_metadata_schema``.
    """
    yield from _write(_resolve(env_fields, ENVIRONMENT))


def clear_sample_metadata():
    """Clear every field: NaN, ``""`` or state 0, and ``MetaState = Unset``.

    Never touches the sample thickness, which stays a usable number.
    """
    values = _resolve({}, SAMPLE)
    values.update(_resolve({}, ENVIRONMENT))
    values.update(_bookkeeping("Unset"))
    yield from _write(values)


def end_sample_metadata(exposure_signal=None):
    """For ``finalize_wrapper``: switch the exposure source off, then clear.

    The source goes off first, so an abort can't leave a UV lamp on.
    """
    if exposure_signal is not None:
        yield from bps.mv(exposure_signal, 0)
    yield from clear_sample_metadata()


def check_sample_binding(title):
    """The per-scan rule: clear stale metadata, keep it for the same sample.

    Also starts the X-ray exposure count for this scan and writes the count
    so far to ``XrayExposureTime``.  Called by ``@sample_metadata_checked``
    before any detector is armed.

    Returns
    -------
    str or None
        The exposure key the scan counts against; ``None`` for a blank.
    """
    if schema.is_blank_title(title):
        yield from clear_sample_metadata()
        xray_exposure.begin(None)
        return None

    device = _device()
    state = yield from bps.rd(device.meta_state)
    bound = yield from bps.rd(device.bound_title)
    if state == "Set" and bound and not title.startswith(bound):
        message = (
            f"sample metadata for {bound!r} cleared:"
            f" scan {title!r} is a different sample"
        )
        logger.warning(message)
        _note(message)
        yield from clear_sample_metadata()
        state, bound = "Unset", ""

    key = bound if (state == "Set" and bound) else title
    xray_exposure.begin(key)
    yield from bps.mv(device.xray_exposure_time, xray_exposure.total(key))
    return key


def sample_metadata_snapshot():
    """Read every set field, for the start document.

    Unset fields are left out, so the result stays small and JSON-safe (no
    NaN).  A field direction is kept only when its field is set.
    """
    device = _device()
    snapshot = {}
    for field in schema.FIELDS:
        value = yield from bps.rd(getattr(device, field.name))
        if field.name.endswith("_dir"):
            if field.name[: -len("_dir")] in snapshot:
                snapshot[field.name] = value
            continue
        if _is_unset(field, value):
            continue
        if field.kind == "int":
            value = int(value)
        snapshot[field.name] = value
    return snapshot


# --- decorator for the data plans ---------------------------------------------

_depth = 0


def sample_metadata_checked(plan_func):
    """Decorator for the data plans: binding check, snapshot, exposure window.

    Before the plan body, runs ``check_sample_binding(title)`` and puts
    ``sample_metadata_snapshot()`` into ``md["sample_metadata"]``.  The X-ray
    exposure count runs until the plan ends.  Only the outermost decorated
    plan acts (``USAXSscan`` -> ``Flyscan`` checks once).  Apply at the
    definition site, innermost, like ``@obsidian_logged``.
    """
    signature = inspect.signature(plan_func)

    @functools.wraps(plan_func)
    def wrapper(*args, **kwargs):
        global _depth
        if _depth > 0:
            return (yield from plan_func(*args, **kwargs))

        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        _depth += 1
        try:
            yield from check_sample_binding(str(bound.arguments.get("title", "")))
            if "md" in bound.arguments:
                md = dict(bound.arguments["md"] or {})
                md["sample_metadata"] = yield from sample_metadata_snapshot()
                bound.arguments["md"] = md
            return (yield from plan_func(*bound.args, **bound.kwargs))
        finally:
            _depth -= 1
            xray_exposure.end()

    return wrapper


# --- SampleState: the helper every plan template uses -----------------------


class SampleState:
    """Sample metadata for one sample through a template plan.

    Create it with ``state = yield from SampleState.start(...)``, call
    ``title = yield from state.prepare_scan(...)`` immediately before every
    sample scan, and end the plan with
    ``bpp.finalize_wrapper(body(), end_sample_metadata())``.  Blanks need
    nothing: the data plan clears the PVs, and the next ``prepare_scan``
    writes the full set again.

    In debug mode nothing is written; ``prepare_scan`` prints what it would
    write and still returns the title.
    """

    def __init__(
        self,
        base_title,
        owner,
        env,
        title_format,
        temperature_source,
        procedure_name,
        series_name,
        exposure,
        exposure_signal,
        debug,
    ):
        """Use ``SampleState.start``, which also writes the PVs."""
        self.base_title = base_title
        self.owner = owner
        self.env = env
        self.title_format = title_format
        self.temperature_source = temperature_source
        self.procedure_name = procedure_name
        self.series_name = series_name if series_name is not None else base_title
        self.exposure = dict(exposure or {})
        self.exposure_signal = exposure_signal
        self.debug = debug
        self.sample_fields = {}
        self.t0 = time.time()
        self.series_index = 0
        self.rheo_pulse_count = 0
        self.rheo_last_pulse_time = math.nan
        self.exposure_start_time = math.nan
        self._exposure_since = None
        self._exposure_total = 0.0

    @classmethod
    def start(
        cls,
        base_title,
        *,
        env="Ambient",
        owner="plan template",
        title_format=TITLE_TIME,
        temperature_source="",
        procedure_name="",
        series_name=None,
        sample_fields=None,
        exposure=None,
        exposure_signal=None,
        debug=False,
    ):
        """Plan: bind the metadata to ``base_title`` and return the state.

        Sample properties already in the IOC are adopted if ``BoundTitle`` is
        ``base_title`` (the operator typed them in caQtDM); ``sample_fields``
        then overrides them.  For any other binding only ``sample_fields``
        count.

        Parameters
        ----------
        base_title : str
            The sample title before any suffix.
        env : str
            ``EnvType``: Ambient, Linkam, PTC10, Rheometer, Other.
        title_format : str
            One of the ``TITLE_*`` encodings of this module.
        procedure_name : str
            Generated by the template from its own arguments, e.g.
            ``"Linkam: 20 C/min to 200 C, hold 30 min"``.
        exposure : dict, optional
            Deliberate-exposure description: ``exposure_type``,
            ``exposure_source``, ``exposure_wavelength``, ``exposure_intensity``,
            ``exposure_intensity_units``, ``exposure_dose_units``.
        exposure_signal : ophyd signal, optional
            The TTL that switches the source; ``set_exposure`` drives it and
            ``prepare_scan`` reads it back for ``ExposureOn``.
        """
        state = cls(
            base_title,
            owner,
            env,
            title_format,
            temperature_source,
            procedure_name,
            series_name,
            exposure,
            exposure_signal,
            debug,
        )
        adopted = {}
        if not debug:
            device = _device()
            meta_state = yield from bps.rd(device.meta_state)
            bound = yield from bps.rd(device.bound_title)
            if meta_state == "Set" and bound == base_title:
                for field in SAMPLE_FIELDS:
                    value = yield from bps.rd(getattr(device, field.name))
                    if not _is_unset(field, value):
                        adopted[field.name] = value
        state.sample_fields = {**adopted, **(sample_fields or {})}
        _resolve(state.sample_fields, SAMPLE)  # fail early on a bad name
        _resolve(
            {k: v for k, v in state.exposure.items() if not k.endswith("_on")},
            ENVIRONMENT,
        )
        if debug:
            print(f"[debug] sample metadata for {base_title!r}: {state.sample_fields}")
        else:
            yield from set_sample_metadata(base_title, owner, **state.sample_fields)
        return state

    def reset_t0(self):
        """Restart the series clock (where templates used to set ``t0``)."""
        self.t0 = time.time()

    def record_pulse(self):
        """Count one rheometer TTL pulse; call right after sending it."""
        self.rheo_pulse_count += 1
        self.rheo_last_pulse_time = time.time()

    def exposure_time(self):
        """Cumulative seconds the deliberate-exposure source has been on."""
        if self._exposure_since is None:
            return self._exposure_total
        return self._exposure_total + time.time() - self._exposure_since

    def set_exposure(self, on):
        """Plan: switch the exposure source on or off, and keep the count."""
        if self.exposure_signal is not None and not self.debug:
            yield from bps.mv(self.exposure_signal, 1 if on else 0)
        now = time.time()
        if on and self._exposure_since is None:
            self._exposure_since = now
            if math.isnan(self.exposure_start_time):
                self.exposure_start_time = now
        elif not on and self._exposure_since is not None:
            self._exposure_total += now - self._exposure_since
            self._exposure_since = None

    def prepare_scan(
        self,
        *,
        step="",
        step_index=None,
        temperature=None,
        setpoint=None,
        ramp_rate=None,
        index=None,
        phase="",
        user=None,
        **title_fields,
    ):
        """Plan: write the full metadata for the next scan; return its title.

        Parameters
        ----------
        step, step_index : str, int
            ``ProcedureStep`` (``"heat"``, ``"hold"``, ``"cool"``, ...) and its
            segment number.
        temperature : float
            *Measured* temperature, read just now from the controller.  The
            same value goes into the title and ``Temperature``.
        setpoint, ramp_rate : float
            ``TemperatureSetpoint`` (C) and ``RampRate`` (C/min, 0 for a hold).
        index : int
            New ``SeriesIndex``; the current one is kept if omitted.
        phase : str
            Rheometer phase label (``"pre"``, ``"post"``), also used by
            ``TITLE_RHEOMETER``.
        user : dict, optional
            Up to four ``{key: (value, units)}`` entries for the generic slots.
        **title_fields
            Extra values the title format needs (``sx``, ``sy``, ``value``,
            ``units``).

        Returns
        -------
        str
            The scan title, in ``title_format``.
        """
        now = time.time()
        if index is not None:
            self.series_index = index
        title = self.title_format.format(
            base=self.base_title,
            minutes=(now - self.t0) / 60,
            temperature=temperature,
            index=self.series_index,
            phase=phase,
            **title_fields,
        )

        env = {
            "env_type": self.env,
            "procedure_name": self.procedure_name,
            "procedure_step": step,
            "step_index": step_index,
            "temperature": temperature,
            "temperature_setpoint": setpoint,
            "ramp_rate": ramp_rate,
            "temperature_source": self.temperature_source,
            "series_name": self.series_name,
            "series_index": self.series_index,
            "series_t0": self.t0,
            "elapsed_time": now - self.t0,
            "xray_exposure_time": xray_exposure.total(self.base_title),
        }
        if self.env == "Rheometer" or self.rheo_pulse_count:
            env["rheo_pulse_count"] = self.rheo_pulse_count
            env["rheo_last_pulse_time"] = self.rheo_last_pulse_time
            env["rheo_phase"] = phase
        if self.exposure:
            env.update(self.exposure)
            if self.exposure_signal is not None and not self.debug:
                on = bool((yield from bps.rd(self.exposure_signal)))
            else:
                on = self._exposure_since is not None
            seconds = self.exposure_time()
            intensity = self.exposure.get("exposure_intensity")
            env["exposure_on"] = "On" if on else "Off"
            env["exposure_start_time"] = self.exposure_start_time
            env["exposure_time"] = seconds
            if intensity is not None and not math.isnan(float(intensity)):
                env["exposure_dose"] = float(intensity) * seconds
        if user:
            if len(user) > 4:
                raise ValueError(f"at most 4 user metadata entries, got {len(user)}")
            for n, (key, (value, units)) in enumerate(user.items(), start=1):
                env[f"user_key{n}"] = key
                env[f"user_value{n}"] = value
                env[f"user_units{n}"] = units

        values = _resolve(self.sample_fields, SAMPLE)
        values.update(_resolve(env, ENVIRONMENT))
        values.update(_bookkeeping("Set", self.owner, self.base_title))
        if self.debug:
            shown = {k: v for k, v in env.items() if v not in (None, "")}
            print(f"[debug] {title}: {shown}")
        else:
            yield from _write(values)
        return title
