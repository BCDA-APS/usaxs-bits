"""
IOC statistics: synApps iocStats
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignalRO


class IocInfoDevice(Device):
    """Device for monitoring IOC statistics.

    This device provides read-only access to IOC statistics including
    timestamp and uptime information.

    Attributes:
        iso8601: Read-only EpicsSignal for ISO8601 formatted timestamp
        uptime: Read-only EpicsSignal for IOC uptime
    """

    iso8601: Component[EpicsSignalRO] = Component(EpicsSignalRO, "iso8601")
    uptime: Component[EpicsSignalRO] = Component(EpicsSignalRO, "UPTIME")
