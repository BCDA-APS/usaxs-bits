"""
APS only: insertion device
"""

__all__ = [
    "undulator",
]

import logging

from apstools.devices import PlanarUndulator

logger = logging.getLogger(__name__)

logger.info(__file__)


undulator = PlanarUndulator("S12ID:USID:", name="undulator")
# undulator = apstools.devices.PlanarUndulator("ID45", name="undulator")
