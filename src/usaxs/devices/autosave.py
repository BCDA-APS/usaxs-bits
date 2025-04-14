"""
control EPICS IOC autosave
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Autosave(Device):
    """control of autosave routine in EPICS IOC"""

    disable = Component(EpicsSignal, "SR_disable", auto_monitor=False)
    max_time = Component(EpicsSignal, "SR_disableMaxSecs")
