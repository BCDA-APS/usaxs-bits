"""
instrument constants
"""

__all__ = [
    "constants",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

constants = {
    "SAXS_TR_PINY_OFFSET": 10.5,  # measured on 1-31-2025 JIL on 12ID...
    "SAXS_TR_TIME": 2,  # how long to measure transmission
    "SAXS_PINZ_OFFSET": 5,  # move of saxs_z before any sample or saxs_x move
    "TR_MAX_ALLOWED_COUNTS": 980000,  # maximum allowed counts for upd before assume topped up
    "USAXS_AY_OFFSET": 8,  # USAXS transmission diode AX offset, calibrated by JIL 2022/11/08 For Delhi crystals center is 8mm+brag angle correction = 12*sin(Theta)
    "MEASURE_DARK_CURRENTS": True,  # MEASURE dark currents on start of data collection
    "SYNC_ORDER_NUMBERS": True,  # sync order numbers among devices on start of collect data sequence
}
