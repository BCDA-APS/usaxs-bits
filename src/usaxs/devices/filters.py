"""
beam attenuating filters
"""

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
        """A derived signal that calculates transmission from attenuation."""

        def forward(self, value):
            """
            Calculate transmission from attenuation.

            Args:
                value: The attenuation value

            Returns:
                float: The transmission value (1/attenuation)
            """
            return 1 / value

        def inverse(self, value):
            """
            Calculate attenuation from transmission.

            Args:
                value: The transmission value

            Returns:
                float: The attenuation value (1/transmission)
            """
            return 1 / value

    fPos = FormattedComponent(
        EpicsSignal, "{prefix}{_bank}:sortedIndex"
    )  # , kind="config")
    # control = FormattedComponent(EpicsSignalRO, "{prefix}bank{_bank}", string=True,
    #                              kind="config")
    # bits = FormattedComponent(EpicsSignalRO, "{prefix}bitFlag{_bank}", kind="config")
    attenuation = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:attenuation_actual", kind="config"
    )
    # transmission = Component(TransmDerivedSignal,derived_from="attenuation")
    transmission = FormattedComponent(
        EpicsSignalRO, "{prefix}{_bank}:transmission_RBV", kind="config"
    )

    def __init__(self, prefix, bank=None, **kwargs):
        """
        Initialize the FilterBank device.

        Args:
            prefix: The EPICS PV prefix
            bank: The bank identifier
            **kwargs: Additional keyword arguments passed to Device
        """
        self._bank = bank
        super().__init__(prefix, **kwargs)
