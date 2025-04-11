"""
control EPICS IOC autosave
"""

import logging

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal

logger = logging.getLogger(__name__)
logger.info(__file__)


class Autosave(Device):
    """control of autosave routine in EPICS IOC"""

    disable = Component(EpicsSignal, "SR_disable", auto_monitor=False)
    max_time = Component(EpicsSignal, "SR_disableMaxSecs")


# autosave on LAX
lax_autosave = Autosave("usxLAX:", name="lax_autosave")  # LAX is an IOC
