"""
Linkam temperature controllers: T96 (tc1) & CI94 (older)
"""

__all__ = [
    #'linkam_ci94',
    'linkam_tc1',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

#from apstools.devices import Linkam_CI94_Device
#from apstools.devices import Linkam_T96_Device
from .linkam_support import Linkam_T96_Device
import warnings


#linkam_ci94 = Linkam_CI94_Device("usxLAX:ci94:", name="ci94")
linkam_tc1 = Linkam_T96_Device("usxLINKAM:tc1:", name="linkam_tc1")

try:
    linkam_tc1.wait_for_connection()
except Exception as exc:
    warnings.warn(f"Linkam controller {linkam_tc1.name} not connected.")
break



if linkam_tc1.connected:
    # set tolerance for "in position" (Python term, not an EPICS PV)
    # note: done = |readback - setpoint| <= tolerance
    linkam_tc1.temperature.tolerance.put(1.0)

    # sync the "inposition" computation
    linkam_tc1.temperature.cb_readback()

    # easy access to the engineering units
    linkam_tc1.units.put(linkam_tc1.temperature.readback.metadata["units"])
    linkam_tc1.ramp = linkam_tc1.ramprate


#for _o in (linkam_ci94, linkam_tc1):
# for _o in (linkam_tc1,):
#     try:
#         _o.wait_for_connection()
#     except Exception as exc:
#         warnings.warn(f"Linkam controller {_o.name} not connected.")
#         break

#     # set tolerance for "in position" (Python term, not an EPICS PV)
#     # note: done = |readback - setpoint| <= tolerance
#     _o.temperature.tolerance.put(1.0)

#     # sync the "inposition" computation
#     _o.temperature.cb_readback()

#     # easy access to the engineering units
#     _o.units.put(
#         _o.temperature.readback.metadata["units"]
#     )

# make a common term for the ramp rate (devices use different names)
#if linkam_ci94.connected:
#    linkam_ci94.ramp = linkam_ci94.rate
#if linkam_tc1.connected:
#    linkam_tc1.ramp = linkam_tc1.ramprate
