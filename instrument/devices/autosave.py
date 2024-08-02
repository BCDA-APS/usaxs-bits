
"""
control EPICS IOC autosave
"""

__all__ = [
    'lax_autosave',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component, Device, EpicsSignal


class Autosave(Device):
    """control of autosave routine in EPICS IOC"""
    disable = Component(EpicsSignal, "SR_disable", auto_monitor=False)
    max_time = Component(EpicsSignal, "SR_disableMaxSecs")

# autosave on LAX
lax_autosave = Autosave("9idcLAX:", name="lax_autosave")    # LAX is an IOC
