"""
Instrument-wide numerical constants for the 12-ID-E USAXS beamline.

These values are calibrated hardware offsets, thresholds, and operational
flags.  They are collected here so that a single edit propagates everywhere
they are used.  Update the inline comments when a value is re-calibrated.

# Instrument Constants
CONSTANTS:
    SAXS_TR_PINY_OFFSET: 10.5  # measured on 1-31-2025 JIL on 12ID...
    SAXS_TR_TIME: 2 # how long to measure transmission
    SAXS_PINZ_OFFSET: 5 # move of saxs_z before any sample or saxs_x move
    TR_MAX_FRACTION_OF_RANGE: 0.90  # above this fraction of the FX4 range full scale, assume topped up
    USAXS_AY_OFFSET: 8 # USAXS transmission diode AX offset, calibrated by JIL 2022/11/08 For Delhi crystals center is 8mm+brag angle correction = 12*sin(Theta)
    MEASURE_DARK_CURRENTS: true  # dark currents after the first SAXS/WAXS of a command file, then when stale
    DARK_CURRENT_MAX_AGE_H: 3  # SAXS/WAXS exposures re-measure darks older than this; 0 disables
    DARK_CURRENT_AFTER_EVERY_WAXS: true  # TESTING: dark after every WAXS exposure, for a record
    SYNC_ORDER_NUMBERS: true  # sync order numbers among devices on start of collect data sequence

"""  # noqa: E501

constants = {
    "SAXS_TR_PINY_OFFSET": 10.5,  # measured on 1-31-2025 JIL on 12ID...
    "SAXS_TR_TIME": 2,  # how long to measure transmission
    "SAXS_PINZ_OFFSET": 5,  # move of saxs_z before any sample or saxs_x move
    "TR_MAX_FRACTION_OF_RANGE": 0.90,  # above this fraction of the FX4 range full scale, assume topped up and re-autoscale
    "USAXS_AY_OFFSET": 8,  # USAXS transmission diode AX offset, calibrated by JIL 2022/11/08 For Delhi crystals center is 8mm+brag angle correction = 12*sin(Theta)  # noqa: E501
    "MEASURE_DARK_CURRENTS": True,  # dark currents after the first SAXS/WAXS of a command file, then when stale  # noqa: E501
    "DARK_CURRENT_MAX_AGE_H": 3,  # SAXS/WAXS exposures re-measure darks older than this; 0 disables  # noqa: E501
    "DARK_CURRENT_AFTER_EVERY_WAXS": True,  # TESTING: dark after every WAXS exposure, for a record  # noqa: E501
    "SYNC_ORDER_NUMBERS": True,  # sync order numbers among devices on start of collect data sequence  # noqa: E501
}
