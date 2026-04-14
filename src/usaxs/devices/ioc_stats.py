"""
IOC statistics device wrapping the synApps iocStats module.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignalRO


class IocInfoDevice(Device):
    """Read-only access to synApps iocStats PVs.

    ``iso8601``
        Current IOC timestamp in ISO-8601 format (string).
    ``uptime``
        IOC uptime string (e.g. ``"0 days, 01:23:45"``).
    """

    iso8601 = Component(EpicsSignalRO, "iso8601")
    uptime = Component(EpicsSignalRO, "UPTIME")
