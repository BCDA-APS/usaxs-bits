"""
control EPICS IOC autosave
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Autosave(Device):
    """Control of autosave routine in EPICS IOC.

    This device manages the EPICS IOC autosave functionality, allowing control
    over the autosave feature and its timing parameters.

    Attributes:
        disable: EpicsSignal to disable autosave functionality
        max_time: EpicsSignal for maximum time in seconds before autosave
    """

    disable: Component[EpicsSignal] = Component(
        EpicsSignal, "SR_disable", auto_monitor=False
    )
    max_time: Component[EpicsSignal] = Component(EpicsSignal, "SR_disableMaxSecs")
