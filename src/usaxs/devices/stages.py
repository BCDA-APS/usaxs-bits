"""
Motion stage devices for the 12-ID-E USAXS instrument.

Defines MotorBundle subclasses for each major optomechanical stage, grouped by
their role in the optical path:

``TuneRanges``                — EPICS PVs holding the scan range for each tune axis.
``UsaxsCollimatorStageDevice``— Collimator (MR) stage: r, x, y, r2p.
``UsaxsDetectorStageDevice``  — Detector (DX/DY) stage: x, y.
``UsaxsSampleStageDevice``    — Sample stage: x, y.
``UsaxsAnalyzerStageDevice``  — Analyzer (AR) stage: r, x, y, r2p.
``SaxsDetectorStageDevice``   — SAXS detector stage: x, y, z.
``GuardSlitsStageDevice``     — Guard slits translation stage: x, y.

``TUNE_METHOD_PEAK_CHOICE``
    Peak-finding method used during axis tuning.  ``"centroid"`` selects the
    centre-of-mass rather than the raw peak value.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import MotorBundle

from .usaxs_motor_devices import TunableEpicsMotor2
from .usaxs_motor_devices import TunableEpicsMotor2WTolerance

# centre-of-mass is preferred over raw peak value for axis tuning
TUNE_METHOD_PEAK_CHOICE = "centroid"


class TuneRanges(Device):
    """EPICS PVs storing the scan half-width for each tunable USAXS axis.

    Components are listed in optical-path order: MR → M2RP → AR → A2RP → DX/DY.
    ``msrp`` and ``asrp`` are monochromator/analyzer second roll-pitch axes.
    """

    # in order of optical path
    mr = Component(EpicsSignal, "usxLAX:USAXS:tune_mr_range")
    msrp = Component(EpicsSignal, "usxLAX:USAXS:tune_msrp_range")
    m2rp = Component(EpicsSignal, "usxLAX:USAXS:tune_m2rp_range")
    ar = Component(EpicsSignal, "usxLAX:USAXS:tune_ar_range")
    asrp = Component(EpicsSignal, "usxLAX:USAXS:tune_asrp_range")
    a2rp = Component(EpicsSignal, "usxLAX:USAXS:tune_a2rp_range")
    dx = Component(EpicsSignal, "usxLAX:USAXS:tune_dx_range")
    dy = Component(EpicsSignal, "usxLAX:USAXS:tune_dy_range")

    @property
    def display(self) -> str:
        """Return all tune ranges as a comma-separated ``name=value`` string."""
        return ", ".join(
            [f"{k}={getattr(self, k).get()}" for k in self.component_names]
        )


axis_tune_range = TuneRanges(name="axis_tune_range")


class UsaxsCollimatorStageDevice(MotorBundle):
    """USAXS collimator (MR) stage: rotation, translation, and piezo roll-pitch.

    ``r``   — main collimator rotation (tunable, with tolerance).
    ``x``, ``y`` — lateral translation.
    ``r2p`` — secondary roll-pitch piezo (tunable).
    ``isChannelCut`` — class flag indicating channel-cut geometry.
    """

    r = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m12",
        labels=("collimator", "tunable"),
        tune_range=axis_tune_range.mr,
    )
    x = Component(EpicsMotor, "usxAERO:m10", labels=("collimator",))
    y = Component(EpicsMotor, "usxAERO:m11", labels=("collimator",))
    r2p = Component(
        TunableEpicsMotor2,
        "usxLAX:pi:c0:m2",
        labels=("collimator", "tunable"),
        tune_range=axis_tune_range.m2rp,
    )
    isChannelCut: bool = True


class UsaxsDetectorStageDevice(MotorBundle):
    """USAXS detector (DX/DY) stage: both axes are tunable."""

    x = Component(
        TunableEpicsMotor2,
        "usxAERO:m1",
        labels=("detector", "tunable"),
        tune_range=axis_tune_range.dx,
    )
    y = Component(
        TunableEpicsMotor2,
        "usxAERO:m2",
        labels=("detector", "tunable"),
        tune_range=axis_tune_range.dy,
    )


class UsaxsSampleStageDevice(MotorBundle):
    """USAXS sample stage: x and y translation."""

    x = Component(EpicsMotor, "usxAERO:m8", labels=("sample",))
    y = Component(EpicsMotor, "usxAERO:m9", labels=("sample",))


class UsaxsAnalyzerStageDevice(MotorBundle):
    """USAXS analyzer (AR) stage: rotation, translation, and piezo roll-pitch.

    ``r``   — main analyzer rotation (tunable, with tolerance).
    ``x``, ``y`` — lateral translation.
    ``r2p`` — secondary roll-pitch piezo (tunable).
    """

    r = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m6",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.ar,
    )
    x = Component(EpicsMotor, "usxAERO:m4", labels=("analyzer",))
    y = Component(EpicsMotor, "usxAERO:m5", labels=("analyzer",))
    r2p = Component(
        TunableEpicsMotor2,
        "usxLAX:pi:c0:m1",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.a2rp,
    )


class SaxsDetectorStageDevice(MotorBundle):
    """SAXS detector stage: x, y, and z translation."""

    x = Component(EpicsMotor, "usxAERO:m13", labels=("saxs",))
    y = Component(EpicsMotor, "usxAERO:m15", labels=("saxs",))
    z = Component(EpicsMotor, "usxAERO:m14", labels=("saxs",))


class GuardSlitsStageDevice(MotorBundle):
    """Guard slits translation stage: x and y."""

    x = Component(EpicsMotor, "usxLAX:m58:c0:m7", labels=("guard_slits",))
    y = Component(EpicsMotor, "usxLAX:m58:c0:m6", labels=("guard_slits",))
