
"""
permission to operate with X-rays
"""

__all__ = [
    'BeamInHutch',
    'operations_in_12ide',
    'usaxs_CheckBeamSpecial',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


from .diagnostics import diagnostics
from ophyd import EpicsSignalRO


def operations_in_12ide():
    """
    returns True if allowed to use X-ray beam in 12-ID-E station
    """
    #return diagnostics.PSS.b_station_enabled
    #return True 
    return False

"""
This EPICS PV calculates *BeamInHutch* boolean.
This is used to set the check beam PV to use I000 PD on Mirror window, limit is set
in user calc. This would fail for tune_dcmth and other macros, which may take
the intensity there down. For that use the other macro (?usaxs_CheckBeamSpecial?)...
"""
BeamInHutch = EpicsSignalRO(
    "9idcLAX:blCalc:userCalc1",
    name="usaxs_CheckBeamStandard",
    auto_monitor=False,
)


# TODO: needs some thought and refactoring
# this is used to set the check beam PV to use many PVs and conditions to decide,
# if there is chance to have beam. Uses also userCalc on lax
usaxs_CheckBeamSpecial = EpicsSignalRO(
	"9idcLAX:blCalc:userCalc2",
	name="usaxs_CheckBeamSpecial",
    auto_monitor=False,
	)
