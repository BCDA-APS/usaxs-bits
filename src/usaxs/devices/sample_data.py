"""
Sample metadata device for the 12-ID-E USAXS instrument.

One ``EpicsSignal`` per field of the ``usxSample:`` IOC.  The field list,
types, units, scopes and file paths are defined in
``usaxs.utils.sample_metadata_schema``; ``tests/test_sample_metadata_schema.py``
checks that this class matches it, so add a field there first.

Do not write these signals directly from a plan: use
``usaxs.plans.sample_metadata`` (``set_sample_metadata``,
``update_environment``, ``clear_sample_metadata``, ``SampleState``), which
replaces whole scopes at a time so that no stale value survives.
"""

import math
import time

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO


class NanSafeSetMixin:
    """Let ``set()`` (and so ``bps.mv``) write NaN to a signal.

    ophyd decides that a ``set`` is done when the readback compares equal to
    the setpoint, and ``nan == nan`` is False, so writing NaN -- the *unset*
    value of every numeric sample field -- would wait out the whole write
    timeout (60 s here, ``OPHYD.TIMEOUTS.PV_WRITE``) and then fail.  This
    treats a NaN readback as matching a NaN setpoint.  Other values take the
    normal path.
    """

    def _set_and_wait(self, value, timeout, **kwargs):
        if not (isinstance(value, float) and math.isnan(value)):
            return super()._set_and_wait(value, timeout, **kwargs)
        self.put(value, **kwargs)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            current = self.get()
            if isinstance(current, float) and math.isnan(current):
                return
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"{self.name} did not read back NaN in {timeout} s")
            time.sleep(0.01)


class NanSafeEpicsSignal(NanSafeSetMixin, EpicsSignal):
    """``EpicsSignal`` that can be ``set()`` to NaN."""


class SampleDataDevice(Device):
    """EPICS PVs describing the current sample and what is being done to it.

    Numeric fields are ``NanSafeEpicsSignal`` so that they can be cleared.
    Unset values are NaN (numbers) or ``""`` (strings); enumerations use
    state 0.  ``shutter_open`` is not sample metadata: it is the Uniblitz
    open/closed tracker (``usxLAX:userStringCalc10``, 1 = last command was
    *open*) that the X-ray exposure accounting integrates, and is omitted from
    readings.
    """

    # --- sample properties (scope: sample) ---
    description = Component(EpicsSignal, "usxSample:Description", string=True)
    chemical_formula = Component(EpicsSignal, "usxSample:ChemicalFormula", string=True)
    concentration = Component(NanSafeEpicsSignal, "usxSample:Concentration")
    density = Component(NanSafeEpicsSignal, "usxSample:Density")
    volume_fraction = Component(NanSafeEpicsSignal, "usxSample:VolumeFraction")
    scattering_length_density = Component(
        NanSafeEpicsSignal, "usxSample:ScatteringLengthDensity"
    )
    magnetic_field = Component(NanSafeEpicsSignal, "usxSample:MagneticField")
    magnetic_field_dir = Component(
        EpicsSignal, "usxSample:MagneticFieldDir", string=True
    )
    stress_field = Component(NanSafeEpicsSignal, "usxSample:StressField")
    stress_field_dir = Component(EpicsSignal, "usxSample:StressFieldDir", string=True)
    electric_field = Component(NanSafeEpicsSignal, "usxSample:ElectricField")
    electric_field_dir = Component(
        EpicsSignal, "usxSample:ElectricFieldDir", string=True
    )
    x_translation = Component(NanSafeEpicsSignal, "usxSample:XTranslation")
    rotation_angle = Component(NanSafeEpicsSignal, "usxSample:RotationAngle")

    # --- what is being done to it now (scope: environment) ---
    env_type = Component(EpicsSignal, "usxSample:EnvType", string=True)
    procedure_name = Component(EpicsSignal, "usxSample:ProcedureName", string=True)
    procedure_step = Component(EpicsSignal, "usxSample:ProcedureStep", string=True)
    step_index = Component(NanSafeEpicsSignal, "usxSample:StepIndex")
    temperature = Component(NanSafeEpicsSignal, "usxSample:Temperature")
    temperature_setpoint = Component(
        NanSafeEpicsSignal, "usxSample:TemperatureSetpoint"
    )
    ramp_rate = Component(NanSafeEpicsSignal, "usxSample:RampRate")
    temperature_source = Component(
        EpicsSignal, "usxSample:TemperatureSource", string=True
    )
    series_name = Component(EpicsSignal, "usxSample:SeriesName", string=True)
    series_index = Component(NanSafeEpicsSignal, "usxSample:SeriesIndex")
    series_t0 = Component(NanSafeEpicsSignal, "usxSample:SeriesT0")
    elapsed_time = Component(NanSafeEpicsSignal, "usxSample:ElapsedTime")
    rheo_pulse_count = Component(NanSafeEpicsSignal, "usxSample:RheoPulseCount")
    rheo_last_pulse_time = Component(NanSafeEpicsSignal, "usxSample:RheoLastPulseTime")
    rheo_phase = Component(EpicsSignal, "usxSample:RheoPhase", string=True)
    xray_exposure_time = Component(NanSafeEpicsSignal, "usxSample:XrayExposureTime")
    exposure_type = Component(EpicsSignal, "usxSample:ExposureType", string=True)
    exposure_source = Component(EpicsSignal, "usxSample:ExposureSource", string=True)
    exposure_wavelength = Component(NanSafeEpicsSignal, "usxSample:ExposureWavelength")
    exposure_intensity = Component(NanSafeEpicsSignal, "usxSample:ExposureIntensity")
    exposure_intensity_units = Component(
        EpicsSignal, "usxSample:ExposureIntensityUnits", string=True
    )
    exposure_on = Component(EpicsSignal, "usxSample:ExposureOn", string=True)
    exposure_start_time = Component(NanSafeEpicsSignal, "usxSample:ExposureStartTime")
    exposure_time = Component(NanSafeEpicsSignal, "usxSample:ExposureTime")
    exposure_dose = Component(NanSafeEpicsSignal, "usxSample:ExposureDose")
    exposure_dose_units = Component(
        EpicsSignal, "usxSample:ExposureDoseUnits", string=True
    )
    user_key1 = Component(EpicsSignal, "usxSample:UserKey1", string=True)
    user_value1 = Component(NanSafeEpicsSignal, "usxSample:UserValue1")
    user_units1 = Component(EpicsSignal, "usxSample:UserUnits1", string=True)
    user_key2 = Component(EpicsSignal, "usxSample:UserKey2", string=True)
    user_value2 = Component(NanSafeEpicsSignal, "usxSample:UserValue2")
    user_units2 = Component(EpicsSignal, "usxSample:UserUnits2", string=True)
    user_key3 = Component(EpicsSignal, "usxSample:UserKey3", string=True)
    user_value3 = Component(NanSafeEpicsSignal, "usxSample:UserValue3")
    user_units3 = Component(EpicsSignal, "usxSample:UserUnits3", string=True)
    user_key4 = Component(EpicsSignal, "usxSample:UserKey4", string=True)
    user_value4 = Component(NanSafeEpicsSignal, "usxSample:UserValue4")
    user_units4 = Component(EpicsSignal, "usxSample:UserUnits4", string=True)

    # --- state of the metadata itself (scope: bookkeeping) ---
    meta_state = Component(EpicsSignal, "usxSample:MetaState", string=True)
    meta_owner = Component(EpicsSignal, "usxSample:MetaOwner", string=True)
    meta_set_time = Component(NanSafeEpicsSignal, "usxSample:MetaSetTime")
    bound_title = Component(EpicsSignal, "usxSample:BoundTitle", string=True)

    shutter_open = Component(
        EpicsSignalRO, "usxLAX:userStringCalc10.VAL", kind="omitted"
    )

    def resetAll(self):
        """Bluesky plan: clear all sample metadata (old name, kept for scripts).

        Same as ``usaxs.plans.sample_metadata.clear_sample_metadata``.  It used
        to write plausible placeholders (25 C, concentration 1, ...) which the
        data files could not tell apart from real values.
        """
        from usaxs.plans.sample_metadata import clear_sample_metadata

        yield from clear_sample_metadata()
