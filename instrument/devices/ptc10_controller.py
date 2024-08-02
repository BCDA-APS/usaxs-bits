"""
PTC10 Programmable Temperature Controller
"""

__all__ = [
    "ptc10",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import PTC10AioChannel
from apstools.devices import PTC10PositionerMixin
from apstools.devices import PTC10RtdChannel
from ophyd import Component
from ophyd import EpicsSignalRO
from ophyd import EpicsSignalWithRBV
from ophyd import PVPositioner


class USAXS_PTC10(PTC10PositionerMixin, PVPositioner):
    """
    PTC10 as seen from the GUI screen

    The IOC templates and .db files provide a more general depiction.
    The PTC10 has feature cards, indexed by the slot where each is
    installed (2A, 3A, 5A, ...).  Here, slot 2 has four temperature
    sensor channels (2A, 2B, 2C, 2D).  The EPICS database template file
    calls for these EPICS database files:

    * PTC10_tc_chan.db  (channels 2A, 2B, 2C, 2D, ColdJ2)
    * PTC10_rtd_chan.db (channels 3A, 3B)
    * PTC10_aio_chan.db (channels 5A, 5B, 5C, 5D)

    USAGE

    * Change the temperature and wait to get there: ``yield from bps.mv(ptc10, 75)``
    * Change the temperature and not wait: ``yield from bps.mv(ptc10.setpoint, 75)``
    * Change other parameter: ``yield from bps.mv(ptc10.tolerance, 0.1)``
    * To get temperature: ``ptc10.position``  (because it is a **positioner**)
    * Is it at temperature?:  ``ptc10.done.get()``
    """

    # PVPositioner interface
    readback = Component(EpicsSignalRO, "2A:temperature", kind="hinted")
    setpoint = Component(EpicsSignalWithRBV, "5A:setPoint", kind="hinted")

    # PTC10 base
    enable = Component(EpicsSignalWithRBV, "outputEnable", kind="config", string=True)

    # PTC10 thermocouple module : reads as NaN
    # temperatureB = Component(
    #     EpicsSignalRO, "2B:temperature", kind="config"
    # )
    # temperatureC = Component(EpicsSignalRO, "2C:temperature", kind="config")
    # # temperatureD = Component(EpicsSignalRO, "2D:temperature", kind="omitted")  # it's a NaN now
    # coldj2 = Component(
    #     EpicsSignalRO, "ColdJ2:temperature", kind="config"
    # )

    # PTC10 RTD module
    # rtd = Component(PTC10RtdChannel, "3A:")  # reads as NaN
    # rtdB = Component(PTC10RtdChannel, "3B:")  # unused now

    # PTC10 AIO module
    pid = Component(PTC10AioChannel, "5A:")
    # pidB = Component(PTC10AioChannel, "5B:")  # unused now
    # pidC = Component(PTC10AioChannel, "5C:")  # unused now
    # pidD = Component(PTC10AioChannel, "5D:")  # unused now


ptc10 = USAXS_PTC10("9idcTEMP:tc1:", name="ptc10")
ptc10.report_dmov_changes.put(True)  # a diagnostic
ptc10.tolerance.put(1.0)  # done when |readback-setpoint|<=tolerance

# aliases to make PTC10 have same terms as Linkam controllers
ptc10.temperature = ptc10
ptc10.ramp = ptc10.pid.ramprate
