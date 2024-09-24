"""
APS only: insertion device
"""

__all__ = [
    "undulator",
]

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)

import apstools.devices

undulator = apstools.devices.aps_undulator.ApsUndulatorDual("S12ID:USID", name="undulator")
# undulator = apstools.devices.ApsUndulatorDual("ID45", name="undulator")
