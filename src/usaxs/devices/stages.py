"""
stages
"""

# TODO check, refactor and verify...

from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import MotorBundle

from .usaxs_motor_devices import TunableEpicsMotor2
from .usaxs_motor_devices import TunableEpicsMotor2WTolerance

# this is for tuning part of the code.
# 2024-06-28 we need to merge stages.py with axis_tuning.py since the new tunable motor
# class is defined here.
# use center-of-mass, and not peak value: "com"
TUNE_METHOD_PEAK_CHOICE = "centroid"


class TuneRanges(Device):
    """
    width of tuning for each axis
    """

    # in order of optical path
    mr: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:USAXS:tune_mr_range")
    msrp: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:USAXS:tune_msrp_range"
    )
    m2rp: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:USAXS:tune_m2rp_range"
    )
    ar: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:USAXS:tune_ar_range")
    asrp: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:USAXS:tune_asrp_range"
    )
    a2rp: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:USAXS:tune_a2rp_range"
    )
    dx: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:USAXS:tune_dx_range")
    dy: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:USAXS:tune_dy_range")

    @property
    def display(self) -> str:
        """
        Return a string representation of all tune ranges.

        Returns:
            str: A comma-separated string of all tune range values.
        """
        return ", ".join(
            [f"{k}={getattr(self, k).get()}" for k in self.component_names]
        )


axis_tune_range = TuneRanges(name="axis_tune_range")


class UsaxsCollimatorStageDevice(MotorBundle):
    """USAXS Collimator (Monochromator) stage"""

    r: Component[TunableEpicsMotor2WTolerance] = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m12",
        labels=(
            "collimator",
            "tunable",
        ),
        tune_range=axis_tune_range.mr,
        # defaults everything else
    )
    x: Component[EpicsMotor] = Component(
        EpicsMotor, "usxAERO:m10", labels=("collimator",)
    )
    y: Component[EpicsMotor] = Component(
        EpicsMotor, "usxAERO:m11", labels=("collimator",)
    )
    r2p: Component[EpicsMotor] = Component(
        EpicsMotor,
        "usxLAX:pi:c0:m2",
        labels=(
            "collimator",
            "tunable",
        ),
    )
    isChannelCut: bool = True


# ----- end of MR ------


class UsaxsDetectorStageDevice(MotorBundle):
    """USAXS detector stage"""

    x: Component[TunableEpicsMotor2] = Component(
        TunableEpicsMotor2,
        "usxAERO:m1",
        labels=(
            "detector",
            "tunable",
        ),
        tune_range=axis_tune_range.dx,
    )
    y: Component[TunableEpicsMotor2] = Component(
        TunableEpicsMotor2,
        "usxAERO:m2",
        labels=(
            "detector",
            "tunable",
        ),
        tune_range=axis_tune_range.dy,
    )


class UsaxsSampleStageDevice(MotorBundle):
    """USAXS sample stage"""

    x: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m8", labels=("sample",))
    y: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m9", labels=("sample",))


## ----A stage ---------------------------------------


class UsaxsAnalyzerStageDevice(MotorBundle):
    """USAXS Analyzer stage"""

    r: Component[TunableEpicsMotor2WTolerance] = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m6",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.ar,
    )
    x: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m4", labels=("analyzer",))
    y: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m5", labels=("analyzer",))
    # z = Component(EpicsMotor, 'usxLAX:m58:c0:m7', labels=("analyzer",))
    r2p: Component[TunableEpicsMotor2] = Component(
        TunableEpicsMotor2,
        "usxLAX:pi:c0:m1",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.a2rp,
    )
    # rt = Component(EpicsMotor, 'usxLAX:m58:c1:m3', labels=("analyzer",))




class SaxsDetectorStageDevice(MotorBundle):
    """SAXS detector stage"""

    x: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m13", labels=("saxs",))
    y: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m15", labels=("saxs",))
    z: Component[EpicsMotor] = Component(EpicsMotor, "usxAERO:m14", labels=("saxs",))


class GuardSlitsStageDevice(MotorBundle):
    """Guard Slits stage"""

    x: Component[EpicsMotor] = Component(
        EpicsMotor, "usxLAX:m58:c0:m7", labels=("guard_slits",)
    )
    y: Component[EpicsMotor] = Component(
        EpicsMotor, "usxLAX:m58:c0:m6", labels=("guard_slits",)
    )
