"""
IOC statistics: synApps iocStats
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignalRO


class IocInfoDevice(Device):
    iso8601 = Component(EpicsSignalRO, "iso8601")
    uptime = Component(EpicsSignalRO, "UPTIME")
