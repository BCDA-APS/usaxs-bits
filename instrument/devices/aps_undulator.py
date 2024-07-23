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
# TODO: FIx this for 12IDE

undulator = apstools.devices.ApsUndulator("ID45", name="undulator")
# undulator = apstools.devices.ApsUndulatorDual("ID45", name="undulator")
