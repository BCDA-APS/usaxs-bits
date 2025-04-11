"""
beam attenuating filters
"""

__all__ = [
    "Filter_AlTi",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import DerivedSignal
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent


class FilterBank(Device):
    """
    A single module of filters (12-blades).

    .. index:: Ophyd Device; FilterBank

    EXAMPLES::

        pfilter = FilterBank("ioc:", name="pfilter", bank="FL1")

    :see:
    """

    class TransmDerivedSignal(DerivedSignal):
        def forward(self, value):
            return 1 / value

        def inverse(self, value):
            return 1 / value

    fPos = FormattedComponent(
        EpicsSignal, "{prefix}{_bank}:sortedIndex"
    )  # , kind="config")
    # control = FormattedComponent(EpicsSignalRO, "{prefix}bank{_bank}", string=True, kind="config")
    # bits = FormattedComponent(EpicsSignalRO, "{prefix}bitFlag{_bank}", kind="config")
    attenuation = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:attenuation_actual", kind="config"
    )
    # transmission = Component(TransmDerivedSignal,derived_from="attenuation")
    transmission = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:transmission_RBV", kind="config"
    )

    def __init__(self, prefix, bank=None, **kwargs):
        self._bank = bank
        super().__init__(prefix, **kwargs)


Filter_AlTi = FilterBank("12idPyFilter:", name="Filter_AlTi", bank="FL1")

# pf4_glass = DualPf4FilterBox("usxRIO:pf42:", name="pf4_glass")


# class FilterCommon(Device):
#     """
#     Filters - common support.

#     .. index:: Ophyd Device; FilterCommon

#     Use ``FilterCommon`` to build support for a configuration
#     of filters (such as 3 or 4 filter banks).

#     EXAMPLE::

#         class MyTripleFilter(FilterCommon):
#             A = Component(FilterBank, "", bank="FL1")
#             B = Component(FilterBank, "", bank="FL2")
#             C = Component(FilterBank, "", bank="FL3")

#         pfilter = MyTripleFilter("ioc:", name="pfilter")

#     :see: pydev_filter from Max
#     """

#     attenuation = Component(EpicsSignalRO, "attenuation_actual", kind="hinted")
#     #inverse_transmission = Component(EpicsSignalRO, "invTrans", kind="normal")

#     attenuation_index = Component(EpicsSignalRO, "sortedIndex_RBV", kind="config")
#     attenuation = Component(EpicsSignal, "sortedIndex", kind="config")
#     #thickness_Ti_mm = Component(EpicsSignalRO, "filterTi", kind="config")
#     #thickness_glass_mm = Component(EpicsSignalRO, "filterGlass", kind="config")

#     energy_keV_local = Component(EpicsSignal, "EnergyLocal", kind="config")
#     energy_keV_mono = Component(EpicsSignal, "EnergyBeamline", kind="config")

#     mode = Component(EpicsSignal, "EnergySelect", string=True, kind="config")
