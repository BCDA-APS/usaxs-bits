"""
PTC10 Programmable Temperature Controller device for the 12-ID-E USAXS instrument.

``PTC10AioChannelFixed``
    Subclass of ``PTC10AioChannel`` that corrects the voltage-readback PV suffix
    from ``voltage_RBV`` to ``output_RBV`` to match the 12-ID IOC template.

``USAXS_PTC10``
    Positioner device combining ``PTC10PositionerMixin`` with ``PVPositioner``.
    Reads temperature from thermocouple channel 2A and controls via AIO channel 5A.
"""

from apstools.devices import PTC10AioChannel
from apstools.devices import PTC10PositionerMixin
from ophyd import Component
from ophyd import EpicsSignalRO
from ophyd import EpicsSignalWithRBV
from ophyd import PVPositioner


class PTC10AioChannelFixed(PTC10AioChannel):
    """``PTC10AioChannel`` with corrected voltage-readback PV suffix.

    The 12-ID IOC template uses ``output_RBV`` for the AIO output readback;
    the apstools default is ``voltage_RBV`` which does not exist on this IOC.
    """

    voltage = Component(EpicsSignalRO, "output_RBV", kind="config")


class USAXS_PTC10(PTC10PositionerMixin, PVPositioner):
    """PTC10 temperature controller as seen from the GUI screen.

    The IOC templates and .db files provide a more general depiction.
    The PTC10 has feature cards indexed by their slot (2A, 3A, 5A, …).
    Slot 2 has four thermocouple channels (2A, 2B, 2C, 2D); slot 3 has
    RTD channels (3A, 3B); slot 5 has AIO (PID) channels (5A–5D).

    EPICS database files used:

    * ``PTC10_tc_chan.db``  (channels 2A, 2B, 2C, 2D, ColdJ2)
    * ``PTC10_rtd_chan.db`` (channels 3A, 3B)
    * ``PTC10_aio_chan.db`` (channels 5A, 5B, 5C, 5D)

    Usage::

        yield from bps.mv(ptc10, 75)            # move and wait
        yield from bps.mv(ptc10.setpoint, 75)   # move, don't wait
        yield from bps.mv(ptc10.tolerance, 0.1)
        ptc10.position   # current temperature (positioner interface)
        ptc10.done.get() # True when within tolerance

    PTC10 PID parameters for different heaters (from legacy SPEC macros)::

        # Gas flow cell:  P=0.0344, I=0.0013, D=0.0253
        # NMR tube:       P=0.5,    I=0.03,   D=1.7
        # Rheo heater:    P=1,      I=0.01,   D=10

    Note: the NMR tube heater exhibits a significant temperature gradient
    (~20 °C at 300 °C) across the holder; verify the offset at each new
    position before use.
    """

    # PVPositioner interface
    readback = Component(EpicsSignalRO, "2A:temperature", kind="hinted")
    setpoint = Component(EpicsSignalWithRBV, "5A:setPoint", kind="hinted")

    # PTC10 base
    enable = Component(EpicsSignalWithRBV, "outputEnable", kind="config", string=True)

    # PTC10 AIO module (only channel 5A is active; B/C/D are unused)
    pid = Component(PTC10AioChannelFixed, "5A:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_dmov_changes.put(True)  # diagnostic: log every done/moving change
        self.tolerance.put(1.0)  # done when |readback-setpoint| <= tolerance

    @property
    def temperature(self):
        """Get the current temperature reading."""
        return self

    @property
    def ramp(self):
        """Get the current ramp rate."""
        return self.pid.ramprate
