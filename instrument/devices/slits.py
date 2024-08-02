
"""
slits
"""

__all__ = [
    'guard_slit',
    'usaxs_slit',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from ophyd import Component, EpicsSignal, MotorBundle, EpicsMotor

from ..framework import sd
from .general_terms import terms
#from .usaxs_motor_devices import UsaxsMotor
#from ..utils import move_motors


class UsaxsSlitDevice(MotorBundle):
    """
    USAXS slit just before the sample

    * center of slit: (x, y)
    * aperture: (h_size, v_size)
    """
    h_size = Component(EpicsMotor, 'usxLAX:m58:c1:m8', labels=("uslit",))
    x      = Component(EpicsMotor, 'usxLAX:m58:c1:m6', labels=("uslit",))
    v_size = Component(EpicsMotor, 'usxLAX:m58:c1:m7', labels=("uslit",))
    y      = Component(EpicsMotor, 'usxLAX:m58:c1:m5', labels=("uslit",))

    def set_size(self, *args, h=None, v=None):
        """move the slits to the specified size"""
        if h is None:
            raise ValueError("must define horizontal size")
        if v is None:
            raise ValueError("must define vertical size")
        #move_motors(self.h_size, h, self.v_size, v)
        yield from bps.mv(
            self.h_size, h,
            self.v_size, v,
        )



class GuardSlitMotor(EpicsMotor):
    process_record = Component(EpicsSignal, ".PROC", kind="omitted")
    status_update = Component(EpicsSignal, ".STUP", kind="omitted")


class GSlitDevice(MotorBundle):
    """
    guard slit

    * aperture: (h_size, v_size)
    """
    bot  = Component(GuardSlitMotor, 'usxLAX:m58:c1:m4', labels=("gslit",))
    inb  = Component(GuardSlitMotor, 'usxLAX:m58:c1:m2', labels=("gslit",))
    outb = Component(GuardSlitMotor, 'usxLAX:m58:c1:m1', labels=("gslit",))
    top  = Component(GuardSlitMotor, 'usxLAX:m58:c1:m3', labels=("gslit",))
    x    = Component(EpicsMotor, 'usxLAX:m58:c0:m7', labels=("gslit",))
    y    = Component(EpicsMotor, 'usxLAX:m58:c0:m6', labels=("gslit",))

    h_size = Component(EpicsSignal, 'usxLAX:GSlit1H:size')
    v_size = Component(EpicsSignal, 'usxLAX:GSlit1V:size')

    h_sync_proc = Component(EpicsSignal, 'usxLAX:GSlit1H:sync.PROC')
    v_sync_proc = Component(EpicsSignal, 'usxLAX:GSlit1V:sync.PROC')

    gap_tolerance = 0.02        # actual must be this close to desired
    scale_factor = 1.2    # 1.2x the size of the beam should be good guess for guard slits.
    h_step_away = 0.2     # 0.2mm step away from beam
    v_step_away = 0.1     # 0.1mm step away from beam
    h_step_into = 1.1     # 1.1mm step into the beam (blocks the beam)
    v_step_into = 0.4     # 0.4mm step into the beam (blocks the beam)
    tuning_intensity_threshold = 500

    def set_size(self, *args, h=None, v=None):
        """move the slits to the specified size"""
        if h is None:
            raise ValueError("must define horizontal size")
        if v is None:
            raise ValueError("must define vertical size")
        #move_motors(self.h_size, h, self.v_size, v)
        yield from bps.mv(
            self.h_size, h,
            self.v_size, v,
        )

    @property
    def h_gap_ok(self):
        gap = self.outb.position - self.inb.position
        return abs(gap - terms.SAXS.guard_h_size.get()) <= self.gap_tolerance

    @property
    def v_h_gap_ok(self):
        gap = self.top.position - self.bot.position
        return abs(gap - terms.SAXS.guard_v_size.get()) <= self.gap_tolerance

    @property
    def gap_ok(self):
        return self.h_gap_ok and self.v_h_gap_ok

    def process_motor_records(self):
        yield from bps.mv(self.top.process_record, 1)
        yield from bps.mv(self.outb.process_record, 1)
        yield from bps.sleep(0.05)
        yield from bps.mv(self.bot.process_record, 1)
        yield from bps.mv(self.inb.process_record, 1)
        yield from bps.sleep(0.05)


guard_slit = GSlitDevice('', name='guard_slit')
usaxs_slit = UsaxsSlitDevice('', name='usaxs_slit')
sd.baseline.append(guard_slit)
sd.baseline.append(usaxs_slit)
