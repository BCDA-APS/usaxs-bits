"""
Load frame (small Instron) device for the 12-ID-E USAXS instrument.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignalRO


class LoadFrameDevice(Device):
    """Ophyd device for the USAXS sector-1 load frame (small Instron).

    ``extension``
        Motor controlling the crosshead extension (``usxLAX:m58:c2:m1``).
    ``strain``
        Read-only strain signal calculated by a synApps userCalc record
        (``usxLAX:userCalc2.VAL``).
    """

    extension = Component(EpicsMotor, "usxLAX:m58:c2:m1", kind="hinted")
    strain = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")
