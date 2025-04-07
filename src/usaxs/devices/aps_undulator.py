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

undulator = apstools.devices.PlanarUndulator("S12ID:USID:", name="undulator")
# undulator = apstools.devices.PlanarUndulator("ID45", name="undulator")
