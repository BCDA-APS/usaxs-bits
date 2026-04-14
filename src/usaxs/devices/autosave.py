"""
EPICS IOC autosave control device for the 12-ID-E USAXS instrument.

Wraps the standard synApps autosave ``SR_disable`` / ``SR_disableMaxSecs`` PVs
so that scans can temporarily suppress autosave activity while writing to PVs.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Autosave(Device):
    """Control the synApps autosave module on an EPICS IOC.

    ``disable`` (``SR_disable``)
        Write 1 to disable autosave saves for up to ``max_time`` seconds.
        Write 0 to re-enable immediately.  ``auto_monitor=False`` prevents
        unnecessary CA subscriptions on this rarely-changing PV.
    ``max_time`` (``SR_disableMaxSecs``)
        Maximum number of seconds autosave will stay disabled before the IOC
        re-enables it automatically.
    """

    disable = Component(EpicsSignal, "SR_disable", auto_monitor=False)
    max_time = Component(EpicsSignal, "SR_disableMaxSecs")
