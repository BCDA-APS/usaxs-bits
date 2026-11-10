"""
Field schema for the sample metadata held in the ``usxSample:`` IOC.

One table, :data:`FIELDS`, says for every field which PV holds it, what type
it is, its units, where it lands in every data file (relative to
``/entry/sample``) and its **scope**, which decides who writes it and when it
is cleared:

``sample``
    A property of the specimen, what it *is*.  Survives across the scans of
    one sample, including an in-situ series.
``environment``
    What is being done to it *now*.  Rewritten before every scan by the plan
    that owns the experiment.
``bookkeeping``
    The state of the metadata itself.

The device (``devices/sample_data.py``), the AD ``attributes.xml`` and
``layout*.xml`` files and the fly-scan ``saveFlyData.xml`` must all agree
with this table; ``tests/test_sample_metadata_schema.py`` checks them.  Add a
field here first, then everywhere the test asks for it.

**Unset** is NaN for numbers and ``""`` for strings, never a plausible
value.  Integer-valued fields (indices, counts) are ``ao`` records with
``PREC=0`` for that reason: a ``longout`` cannot hold NaN.  Enumerations use
state 0 as their unset state, except the three field directions, whose
meaning is void while the field itself is NaN, so they keep their existing
X/Y/Z states.

Sample thickness (``usxLAX:sampleThickness``) is **not** in this table: it
defaults to 1, never NaN, because data reduction divides by it, and clearing
the metadata never touches it.

No EPICS, numpy or ophyd here: the module is imported by offline tests.
See ``Plans_skills/PLAN_sample_metadata.md``.
"""

import math
import re
from dataclasses import dataclass

PV_PREFIX = "usxSample:"

SAMPLE = "sample"
ENVIRONMENT = "environment"
BOOKKEEPING = "bookkeeping"
SCOPES = (SAMPLE, ENVIRONMENT, BOOKKEEPING)

# Matilda's rule (readfromtiled.py): a title containing "blank", in any case.
BLANK_TITLE_RE = re.compile("blank", re.IGNORECASE)

STRINGOUT_MAX = 39  # an EPICS stringout holds 40 bytes, NUL included
WAVEFORM_NELM = 1024  # char waveforms; usxLAX:sampleTitle itself is 256

# NeXus class of each sub-group of /entry/sample that the schema creates.
GROUP_CLASSES = {
    "environment": "NXenvironment",
    "time_series": "NXcollection",
    "rheometer": "NXcollection",
    "exposure": "NXcollection",
    "user_metadata": "NXcollection",
    "metadata_state": "NXnote",
}


@dataclass(frozen=True)
class Field:
    """One sample-metadata field.

    ``kind`` is ``"float"``, ``"int"`` (an ``ao`` with ``PREC=0``),
    ``"str"`` or ``"enum"``.  ``long`` marks a string held in a char
    waveform instead of a 39-character ``stringout``.  ``nexus`` is the
    path below ``/entry/sample``.
    """

    name: str
    pv: str
    kind: str
    scope: str
    nexus: str
    units: str = ""
    long: bool = False
    choices: tuple = ()
    prec: int = 3
    desc: str = ""

    @property
    def pvname(self):
        """Full PV name."""
        return PV_PREFIX + self.pv

    @property
    def record_type(self):
        """EPICS record type that holds this field."""
        if self.kind in ("float", "int"):
            return "ao"
        if self.kind == "enum":
            return "mbbo"
        return "waveform" if self.long else "stringout"

    @property
    def max_length(self):
        """Longest string the record can hold, or None for non-strings."""
        if self.kind != "str":
            return None
        return WAVEFORM_NELM - 1 if self.long else STRINGOUT_MAX

    @property
    def unset(self):
        """The value that means *not set*."""
        if self.kind in ("float", "int"):
            return math.nan
        if self.kind == "enum":
            return self.choices[0]
        return ""

    @property
    def ad_attribute(self):
        """NDAttribute name in the AD ``attributes.xml`` files."""
        return "Sample_" + self.pv


_DIRECTIONS = ("X", "Y", "Z")


def _f(name, pv, scope, nexus, units="", **kw):
    return Field(name, pv, "float", scope, nexus, units, **kw)


def _i(name, pv, scope, nexus, **kw):
    return Field(name, pv, "int", scope, nexus, prec=0, **kw)


def _s(name, pv, scope, nexus, long=False, **kw):
    return Field(name, pv, "str", scope, nexus, long=long, **kw)


def _e(name, pv, scope, nexus, choices, **kw):
    return Field(name, pv, "enum", scope, nexus, choices=choices, **kw)


FIELDS = (
    # --- A. sample properties -------------------------------------------
    _s("description", "Description", SAMPLE, "description", long=True),
    _s("chemical_formula", "ChemicalFormula", SAMPLE, "chemical_formula", long=True),
    _f("concentration", "Concentration", SAMPLE, "concentration", "g/cm3"),
    _f("density", "Density", SAMPLE, "density", "g/cm3"),
    _f("volume_fraction", "VolumeFraction", SAMPLE, "volume_fraction"),
    _f(
        "scattering_length_density",
        "ScatteringLengthDensity",
        SAMPLE,
        "scattering_length_density",
        "cm/cm3",
    ),
    _f("magnetic_field", "MagneticField", SAMPLE, "magnetic_field", "T"),
    _e(
        "magnetic_field_dir",
        "MagneticFieldDir",
        SAMPLE,
        "magnetic_field_direction",
        _DIRECTIONS,
    ),
    _f("stress_field", "StressField", SAMPLE, "stress_field", "MPa"),
    _e(
        "stress_field_dir",
        "StressFieldDir",
        SAMPLE,
        "stress_field_direction",
        _DIRECTIONS,
    ),
    _f("electric_field", "ElectricField", SAMPLE, "electric_field", "V"),
    _e(
        "electric_field_dir",
        "ElectricFieldDir",
        SAMPLE,
        "electric_field_direction",
        _DIRECTIONS,
    ),
    _f("x_translation", "XTranslation", SAMPLE, "x_translation", "mm"),
    _f("rotation_angle", "RotationAngle", SAMPLE, "rotation_angle", "deg"),
    # --- B. environment type and heating --------------------------------
    _e(
        "env_type",
        "EnvType",
        ENVIRONMENT,
        "environment/type",
        ("None", "Ambient", "Linkam", "PTC10", "Rheometer", "Other"),
    ),
    _s(
        "procedure_name",
        "ProcedureName",
        ENVIRONMENT,
        "environment/procedure_name",
        long=True,
    ),
    _s("procedure_step", "ProcedureStep", ENVIRONMENT, "environment/step"),
    _i("step_index", "StepIndex", ENVIRONMENT, "environment/step_index"),
    # measured, at scan start; keeps its pre-existing NXsample path
    _f("temperature", "Temperature", ENVIRONMENT, "temperature", "C"),
    _f(
        "temperature_setpoint",
        "TemperatureSetpoint",
        ENVIRONMENT,
        "environment/temperature_setpoint",
        "C",
    ),
    _f("ramp_rate", "RampRate", ENVIRONMENT, "environment/ramp_rate", "C/min"),
    _s(
        "temperature_source",
        "TemperatureSource",
        ENVIRONMENT,
        "environment/temperature_source",
    ),
    # --- C. time series ---------------------------------------------------
    _s("series_name", "SeriesName", ENVIRONMENT, "time_series/name"),
    _i("series_index", "SeriesIndex", ENVIRONMENT, "time_series/index"),
    _f("series_t0", "SeriesT0", ENVIRONMENT, "time_series/t0", "s", desc="epoch"),
    _f("elapsed_time", "ElapsedTime", ENVIRONMENT, "time_series/elapsed_time", "s"),
    # --- D. rheometer: only the TTL pulse is known ---------------------
    _i("rheo_pulse_count", "RheoPulseCount", ENVIRONMENT, "rheometer/pulse_count"),
    _f(
        "rheo_last_pulse_time",
        "RheoLastPulseTime",
        ENVIRONMENT,
        "rheometer/last_pulse_time",
        "s",
        desc="epoch",
    ),
    _s("rheo_phase", "RheoPhase", ENVIRONMENT, "rheometer/phase"),
    # --- E1. X-ray self-exposure ------------------------------------------
    _f(
        "xray_exposure_time",
        "XrayExposureTime",
        ENVIRONMENT,
        "exposure/xray_exposure_time",
        "s",
    ),
    # --- E2. deliberate exposure ------------------------------------------
    _e(
        "exposure_type",
        "ExposureType",
        ENVIRONMENT,
        "exposure/type",
        ("None", "UV", "Visible", "Laser", "Other"),
    ),
    _s("exposure_source", "ExposureSource", ENVIRONMENT, "exposure/source"),
    _f(
        "exposure_wavelength",
        "ExposureWavelength",
        ENVIRONMENT,
        "exposure/wavelength",
        "nm",
    ),
    # units carried in exposure_intensity_units
    _f("exposure_intensity", "ExposureIntensity", ENVIRONMENT, "exposure/intensity"),
    _s(
        "exposure_intensity_units",
        "ExposureIntensityUnits",
        ENVIRONMENT,
        "exposure/intensity_units",
    ),
    _e(
        "exposure_on",
        "ExposureOn",
        ENVIRONMENT,
        "exposure/on",
        ("Unset", "Off", "On"),
    ),
    _f(
        "exposure_start_time",
        "ExposureStartTime",
        ENVIRONMENT,
        "exposure/start_time",
        "s",
        desc="epoch",
    ),
    _f("exposure_time", "ExposureTime", ENVIRONMENT, "exposure/time", "s"),
    # units carried in exposure_dose_units
    _f("exposure_dose", "ExposureDose", ENVIRONMENT, "exposure/dose"),
    _s("exposure_dose_units", "ExposureDoseUnits", ENVIRONMENT, "exposure/dose_units"),
    # --- F. generic slots -------------------------------------------------
    *(
        field
        for n in range(1, 5)
        for field in (
            _s(f"user_key{n}", f"UserKey{n}", ENVIRONMENT, f"user_metadata/key{n}"),
            _f(
                f"user_value{n}",
                f"UserValue{n}",
                ENVIRONMENT,
                f"user_metadata/value{n}",
            ),
            _s(
                f"user_units{n}",
                f"UserUnits{n}",
                ENVIRONMENT,
                f"user_metadata/units{n}",
            ),
        )
    ),
    # --- G. bookkeeping ---------------------------------------------------
    _e(
        "meta_state", "MetaState", BOOKKEEPING, "metadata_state/state", ("Unset", "Set")
    ),
    _s("meta_owner", "MetaOwner", BOOKKEEPING, "metadata_state/owner"),
    _f(
        "meta_set_time",
        "MetaSetTime",
        BOOKKEEPING,
        "metadata_state/set_time",
        "s",
        desc="epoch",
    ),
    _s(
        "bound_title",
        "BoundTitle",
        BOOKKEEPING,
        "metadata_state/bound_title",
        long=True,
    ),
)

FIELDS_BY_NAME = {f.name: f for f in FIELDS}
FIELDS_BY_PV = {f.pvname: f for f in FIELDS}


def fields_in_scope(scope):
    """All fields of one scope, in table order."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {SCOPES}")
    return tuple(f for f in FIELDS if f.scope == scope)


def is_blank_title(title):
    """True for a blank (background) scan title, by Matilda's rule."""
    return bool(BLANK_TITLE_RE.search(title or ""))
