
"""
shutters
"""

__all__ = [
    'ccd_shutter',
    'FE_shutter',
    'mono_shutter',
    'ti_filter_shutter',
    'usaxs_shutter',
    'a_shutter_autoopen',
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


from apstools.devices import ApsPssShutterWithStatus
from apstools.devices import ApsPssShutter
from apstools.devices import EpicsOnOffShutter
from apstools.devices import SimulatedApsPssShutterWithStatus
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent
from ophyd import Component
from ophyd import Signal
import time

from .aps_source import aps
from .permit import operations_in_12ide

# TODO fix this for 12IDE
class My12IdPssShutter(ApsPssShutterWithStatus):
    """
    Controls a single APS PSS shutter at 12IDE.

    ======  =========  =====
    action  PV suffix  value
    ======  =========  =====
    open    _opn       1
    close   _cls       1
    ======  =========  =====
    """
    # bo records that reset after a short time, set to 1 to move
    open_signal = Component(EpicsSignal, "_opn")
    close_signal = Component(EpicsSignal, "_cls")
    # bi record ZNAM=OFF, ONAM=ON
    pss_state = FormattedComponent(EpicsSignalRO, "{self.state_pv}")
    pss_state_open_values = [1,"ON"]
    pss_state_closed_values = [0,"OFF"]


# class PssShutters(Device):
#     """
#     20ID A & B APS PSS shutters.

#     =======  =============
#     shutter  P, PV prefix
#     =======  =============
#     A        20id:shutter0
#     B        20id:shutter1
#     =======  =============
#     """
#     a_shutter = Component(My20IdPssShutter, "20id:shutter0")
#     b_shutter = Component(My20IdPssShutter, "20id:shutter1")

# pss_shutters = PssShutters("", name="pss_shutters")
#pvstatus = PA:20ID:STA_A_FES_OPEN_PL or B_SBS results on "OFF" or "ON"

if aps.inUserOperations and operations_in_12ide():
    FE_shutter = My12IdPssShutter(
        #12id:shutter0_opn and 12id:shutter0_cls
        "A shutter",  
        state_pv = "PA:12ID:STA_A_FES_OPEN_PL",
        name="FE_shutter")

    mono_shutter = ApsPssShutterWithStatus(
         #20id:shutter1_opn and 20id:shutter1_cls
        "E shutter", 
        state_pv = "PA:12ID:STA_C_SCS_OPEN_PL",   
        name="mono_shutter",
        open_pv="12ida2:rShtrC:Open",
        close_pv="12ida2:rShtrC:Close")
    

    #usaxs_shutter = EpicsOnOffShutter(
    #    "usxLAX:userTran3.A",
    #    name="usaxs_shutter")

    usaxs_shutter = ApsPssShutter(
        "Mono beam shutter",
        name="usaxs_shutter",
        open_pv="12idc:uniblitz:shutter:open",
        close_pv="12idc:uniblitz:shutter:close")

    a_shutter_autoopen = EpicsSignal(
        "12ida2:AShtr:Enable",
        name="a_shutter_autoopen")

else:
    logger.warning("!"*30)
    if operations_in_12ide():
        logger.warning("Session started when APS not operating.")
    else:
        logger.warning("Session started when BlueSky is not enabled.")
    logger.warning("Using simulators for all shutters.")
    logger.warning("!"*30)
    FE_shutter = SimulatedApsPssShutterWithStatus(name="FE_shutter")
    mono_shutter = SimulatedApsPssShutterWithStatus(name="mono_shutter")
    usaxs_shutter = SimulatedApsPssShutterWithStatus(name="usaxs_shutter")
    a_shutter_autoopen = Signal(name="a_shutter_autoopen", value=0)


ti_filter_shutter = usaxs_shutter       # alias
ti_filter_shutter.delay_s = 0.1         # shutter needs some recovery time

#ccd_shutter = EpicsOnOffShutter("usxRIO:Galil2Bo0_CMD", name="ccd_shutter")
ccd_shutter = usaxs_shutter       # alias


connect_delay_s = 1
while not mono_shutter.pss_state.connected:
    logger.info(f"Waiting {connect_delay_s}s for mono shutter PV to connect")
    time.sleep(connect_delay_s)


