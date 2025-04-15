"""
automated data collection

To start the automatic data collection plan:

    RE(auto_collect.remote_ops())
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class AutoCollectDataDevice(Device):
    """Device for automated data collection control.

    This device manages the signals for automated data collection, including
    trigger signals, command inputs, and permission controls.

    Attributes:
        trigger_signal: EpicsSignal for starting the collection
        commands: EpicsSignal for string input commands
        permit: EpicsSignal for permission control
        idle_interval: Time interval in seconds between idle checks
    """

    trigger_signal: Component[EpicsSignal] = Component(
        EpicsSignal, "Start", string=True
    )
    commands: Component[EpicsSignal] = Component(EpicsSignal, "StrInput", string=True)
    permit: Component[EpicsSignal] = Component(EpicsSignal, "Permit", string=True)
    idle_interval: int = 2  # seconds
