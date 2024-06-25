
"""
laser distance meter AR500 support
"""

__all__ = [
    'laser',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


from ophyd import Component, Device, EpicsSignal, EpicsSignalRO



class LaserAR500(Device):
    """
    Temporary support for laser distacne meter AR500
    https://www.acuitylaser.com/product/laser-sensors/short-range-sensors/ar500-laser-position-sensor/
    uses Galil analog in and digital out to read distacne as analog volatge and switch AR500 on/off 
    uses Galil userAve (2 seconds long) to average noise
    uses userCalc7 in LAX to convert to real distace
    to read distace use laser.distance.get()
    to switch on use laser.enable.put(1)
    to switch off use laser.enable.put(0)
    dx_in and dy_in reads defined positions from epics. PVs and on Parameters GUI. 
    """
    distance    = Component(EpicsSignalRO, "usxLAX:userCalc7.VAL")
    enable      = Component(EpicsSignal, "usxRIO:Galil2Bo1_CMD")
    dx          = Component(EpicsSignalRO, "usxLAX:USAXS:Laser_dx")    
    dy          = Component(EpicsSignalRO, "usxLAX:USAXS:Laser_dy")


laser = LaserAR500("", name="laser")


