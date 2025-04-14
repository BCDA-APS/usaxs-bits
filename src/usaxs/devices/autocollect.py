"""
automated data collection

To start the automatic data collection plan:

    RE(auto_collect.remote_ops())
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class AutoCollectDataDevice(Device):
    trigger_signal = Component(EpicsSignal, "Start", string=True)
    commands = Component(EpicsSignal, "StrInput", string=True)
    permit = Component(EpicsSignal, "Permit", string=True)
    idle_interval = 2  # seconds
