"""
slits
"""

from typing import Any
from typing import Generator
from typing import Optional

from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import MotorBundle

# from ..devices.general_terms import terms

# from .usaxs_motor_devices import UsaxsMotor
# from ..utils import move_motors


class UsaxsSlitDevice(MotorBundle):
    """
    USAXS slit just before the sample

    * center of slit: (x, y)
    * aperture: (h_size, v_size)
    """

    h_size = Component(EpicsMotor, "usxLAX:m58:c1:m8", labels=("uslit",))
    x = Component(EpicsMotor, "usxLAX:m58:c1:m6", labels=("uslit",))
    v_size = Component(EpicsMotor, "usxLAX:m58:c1:m7", labels=("uslit",))
    y = Component(EpicsMotor, "usxLAX:m58:c1:m5", labels=("uslit",))

    def set_size(
        self, *args: Any, h: Optional[float] = None, v: Optional[float] = None
    ) -> Generator[Any, None, None]:
        """move the slits to the specified size"""
        if h is None:
            raise ValueError("must define horizontal size")
        if v is None:
            raise ValueError("must define vertical size")
        # move_motors(self.h_size, h, self.v_size, v)
        yield from bps.mv(
            self.h_size,
            h,
            self.v_size,
            v,
        )


class GuardSlitMotor(EpicsMotor):
    """
    Motor for guard slits with additional process record and status update signals.

    This class extends EpicsMotor to add functionality specific to guard slit motors.
    """

    process_record = Component(EpicsSignal, ".PROC", kind="omitted")
    status_update = Component(EpicsSignal, ".STUP", kind="omitted")


class GSlitDevice(MotorBundle):
    """
    guard slit

    * aperture: (h_size, v_size)
    """

    bot = Component(GuardSlitMotor, "usxLAX:m58:c1:m4", labels=("gslit",))
    inb = Component(GuardSlitMotor, "usxLAX:m58:c1:m2", labels=("gslit",))
    outb = Component(GuardSlitMotor, "usxLAX:m58:c1:m1", labels=("gslit",))
    top = Component(GuardSlitMotor, "usxLAX:m58:c1:m3", labels=("gslit",))
    x = Component(EpicsMotor, "usxLAX:m58:c0:m7", labels=("gslit",))
    y = Component(EpicsMotor, "usxLAX:m58:c0:m6", labels=("gslit",))

    h_size = Component(EpicsSignal, "usxLAX:GSlit1H:size")
    v_size = Component(EpicsSignal, "usxLAX:GSlit1V:size")

    h_sync_proc = Component(EpicsSignal, "usxLAX:GSlit1H:sync.PROC")
    v_sync_proc = Component(EpicsSignal, "usxLAX:GSlit1V:sync.PROC")

    gap_tolerance: float = 0.02  # actual must be this close to desired
    scale_factor: float = (
        1.2  # 1.2x the size of the beam should be good guess for guard slits.
    )
    h_step_away: float = 0.2  # 0.2mm step away from beam
    v_step_away: float = 0.1  # 0.1mm step away from beam
    h_step_into: float = 1.1  # 1.1mm step into the beam (blocks the beam)
    v_step_into: float = 0.4  # 0.4mm step into the beam (blocks the beam)
    tuning_intensity_threshold: int = 500



# guard_slit = GSlitDevice("", name="guard_slit")
# usaxs_slit = UsaxsSlitDevice("", name="usaxs_slit")
