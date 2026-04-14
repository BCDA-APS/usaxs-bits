"""
Beam-attenuating filter bank device for the 12-ID-E USAXS instrument.

``FilterBank`` wraps a 12-blade attenuator module.  Each bank exposes the
currently selected filter position, the resulting attenuation, and the
resulting transmission as read-only EPICS PVs.

Example::

    pfilter = FilterBank("ioc:", name="pfilter", bank="FL1")
"""

from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent


class FilterBank(Device):
    """A single 12-blade beam-attenuator module.

    Parameters
    ----------
    prefix : str
        EPICS PV prefix for the filter IOC (e.g. ``"ioc:"``).
    bank : str
        Bank identifier appended to PV names (e.g. ``"FL1"``).  Required —
        there is no meaningful default.

    Components
    ----------
    fPos
        Setpoint for the sorted filter-position index.
    fPos_RBV
        Read-back of the sorted filter-position index.
    attenuation
        Actual attenuation factor (read-only).
    transmission
        Transmission read-back (read-only), equal to ``1 / attenuation``.
    """

    fPos = FormattedComponent(EpicsSignal, "{prefix}{_bank}:sortedIndex")
    fPos_RBV = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:sortedIndex_RBV", kind="config"
    )
    attenuation = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:attenuation_actual", kind="config"
    )
    transmission = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:transmission_RBV", kind="config"
    )

    def __init__(self, prefix, bank=None, **kwargs):
        """Store the bank identifier before ophyd builds the Components."""
        self._bank = bank
        super().__init__(prefix, **kwargs)
