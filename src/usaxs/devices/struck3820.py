"""
Struck/SIS 3820 Multi-channel scaler

used with USAXS fly scans
"""

__all__ = [
    "struck",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import Struck3820

struck = Struck3820("usxLAX:3820:", name="struck")
