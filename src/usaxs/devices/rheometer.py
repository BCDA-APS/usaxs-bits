"""
Rheometer sample-stage device for the 12-ID-E USAXS instrument.

Occasionally-used sample environment: the rheometer sits on a stage with one
horizontal translation motor (``x``) and three vertical motors arranged in a
triangle (``leg1``, ``leg2``, ``leg3``) used to level the stage in the
horizontal plane. The three legs are independent motors with no shared
setpoint or interlock, so they are not guaranteed to start at equal
positions — level the stage by driving all three to the same absolute
target in one concurrent move (e.g. ``bps.mv(rheometer.leg1, target,
rheometer.leg2, target, rheometer.leg3, target)``), not by moving them one
at a time or by a relative offset.
"""

from ophyd import Component
from ophyd import EpicsMotor
from ophyd import MotorBundle


class RheometerStageDevice(MotorBundle):
    """Rheometer sample stage: horizontal x, and three vertical leveling legs.

    ``x``    — horizontal translation (``usxLAX:m58:c0:m2``).
    ``leg1`` — vertical leveling motor (``usxLAX:m58:c0:m3``).
    ``leg2`` — vertical leveling motor (``usxLAX:m58:c0:m4``).
    ``leg3`` — vertical leveling motor (``usxLAX:m58:c0:m5``).
    """

    x = Component(EpicsMotor, "usxLAX:m58:c0:m2", labels=("rheometer",))
    leg1 = Component(EpicsMotor, "usxLAX:m58:c0:m3", labels=("rheometer",))
    leg2 = Component(EpicsMotor, "usxLAX:m58:c0:m4", labels=("rheometer",))
    leg3 = Component(EpicsMotor, "usxLAX:m58:c0:m5", labels=("rheometer",))
