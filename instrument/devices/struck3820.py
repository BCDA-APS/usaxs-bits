
"""
Struck/SIS 3820 Multi-channel scaler

used with USAXS fly scans
"""

__all__ = [
    'struck',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import Struck3820
from ophyd import Component, EpicsSignal

struck = Struck3820("9idcLAX:3820:", name="struck")
