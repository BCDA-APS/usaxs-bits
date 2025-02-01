
"""
PSS, FE-EPS, BL-EPS, : diagnostics
"""

__all__ = [
    'diagnostics',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import apstools.synApps
from ophyd import Component, Device
from ophyd import EpicsSignalRO

from ..framework import sd


class PSS_Parameters(Device):
    a_beam_active = Component(EpicsSignalRO, "PA:12ID:A_BEAM_ACTIVE.VAL", string=True)
    a_shutter_open_chain_A_led = Component(EpicsSignalRO, "PA:12ID:STA_A_FES_OPEN_PL", string=True)

    e_beam_active = Component(EpicsSignalRO, "PA:12ID:STA_C_NO_ACCESS.VAL", string=True)
    e_beam_ready = Component(EpicsSignalRO, "PA:12ID:STA_C_BEAMREADY.VAL", string=True)
    e_shutter_closed_chain_B = Component(EpicsSignalRO, "PB:12ID:STA_C_SCS_CLSD_PL", string=True)
    e_shutter_open_chain_A = Component(EpicsSignalRO, "PA:12ID:STA_A_FES_OPEN_PL", string=True)

    #c_beam_ready_leds = Component(EpicsSignalRO, "PA:09ID:STA_C_BEAMREADY_PL", string=True)
    #c_shutter_closed_chain_A = Component(EpicsSignalRO, "PA:09ID:SCS_PS_CLSD_LS", string=True)
    #c_shutter_closed_chain_B = Component(EpicsSignalRO, "PB:09ID:SCS_PS_CLSD_LS", string=True)
    #c_station_door1_closed_switch_chain_A = Component(EpicsSignalRO, "PA:09ID:STA_C_DR1_CLOSE_LS", string=True)
    #c_station_door1_closed_switch_chain_B = Component(EpicsSignalRO, "PB:09ID:STA_C_DR1_CLOSE_LS", string=True)
    #c_station_door2_closed_switch_chain_A = Component(EpicsSignalRO, "PA:09ID:STA_C_DR2_CLOSE_LS", string=True)
    #c_station_door2_closed_switch_chain_B = Component(EpicsSignalRO, "PB:09ID:STA_C_DR2_CLOSE_LS", string=True)
    #c_station_no_access_chain_A = Component(EpicsSignalRO, "PA:09ID:STA_C_NO_ACCESS.VAL", string=True)
    #c_station_no_access_sign = Component(EpicsSignalRO, "PA:09ID:STA_C_NO_ACCESS", string=True)

    # other signals?

    @property
    def c_station_enabled(self):
        """
        this is really not needed on 12ID as both beamlines can work in parallel
        This was used at 9ID with hutches behind. 
        look at the switches: are we allowed to operate?
       
        #:Plug in place:
        ##  Cannot use beam in 20-ID-B.
        #  Should not use FE or mono shutters, monochromator, ti_filter_shutter...
        #:Plug removed:
          
          Operations in 12-ID-C are always allowed
        """
        #chain_A = self.c_shutter_closed_chain_A
        #chain_B = self.c_shutter_closed_chain_B
        #enabled = chain_A.get() == "OFF" or chain_B.get() == "OFF"
        return 1


# class BLEPS_Parameters(Device):
#     """Beam Line Equipment Protection System"""
#     red_light = Component(EpicsSignalRO, "9idBLEPS:RED_LIGHT")
#     station_shutter_b_permit = Component(EpicsSignalRO, "9idBLEPS:SBS_PERMIT", string=True)
#     station_shutter_b = Component(EpicsSignalRO, "9idBLEPS:SBS_CLOSED", string=True)
#     flow_1 = Component(EpicsSignalRO, "9idBLEPS:FLOW1_CURRENT")
#     flow_2 = Component(EpicsSignalRO, "9idBLEPS:FLOW2_CURRENT")
#     flow_1_setpoint = Component(EpicsSignalRO, "9idBLEPS:FLOW1_SET_POINT")
#     flow_2_setpoint = Component(EpicsSignalRO, "9idBLEPS:FLOW2_SET_POINT")

#     temperature_1_chopper = Component(EpicsSignalRO, "9idBLEPS:TEMP1_CURRENT")
#     temperature_2 = Component(EpicsSignalRO, "9idBLEPS:TEMP2_CURRENT")
#     temperature_3 = Component(EpicsSignalRO, "9idBLEPS:TEMP3_CURRENT")
#     temperature_4 = Component(EpicsSignalRO, "9idBLEPS:TEMP4_CURRENT")
#     temperature_5 = Component(EpicsSignalRO, "9idBLEPS:TEMP5_CURRENT")
#     temperature_6 = Component(EpicsSignalRO, "9idBLEPS:TEMP6_CURRENT")
#     temperature_7 = Component(EpicsSignalRO, "9idBLEPS:TEMP7_CURRENT")
#     temperature_8 = Component(EpicsSignalRO, "9idBLEPS:TEMP8_CURRENT")
#     temperature_1_chopper_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP1_SET_POINT")
#     temperature_2_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP2_SET_POINT")
#     temperature_3_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP3_SET_POINT")
#     temperature_4_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP4_SET_POINT")
#     temperature_5_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP5_SET_POINT")
#     temperature_6_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP6_SET_POINT")
#     temperature_7_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP7_SET_POINT")
#     temperature_8_setpoint = Component(EpicsSignalRO, "9idBLEPS:TEMP8_SET_POINT")
#     # other signals?

#     # technically, these come from the FE-EPS IOC, reading signals from the BL-EPS
#     shutter_permit = Component(EpicsSignalRO, "EPS:09:ID:BLEPS:SPER", string=True)
#     vacuum_permit = Component(EpicsSignalRO, "EPS:09:ID:BLEPS:VACPER", string=True)
#     vacuum_ok = Component(EpicsSignalRO, "EPS:09:ID:BLEPS:VAC", string=True)


# class FEEPS_Parameters(Device):
#     """Front End Equipment Protection System"""
#     fe_permit = Component(EpicsSignalRO, "EPS:09:ID:FE:PERM", string=True)
#     # major_fault = Component(EpicsSignalRO, "EPS:09:ID:Major", string=True)
#     # minor_fault = Component(EpicsSignalRO, "EPS:09:ID:Minor", string=True)
#     mps_permit = Component(EpicsSignalRO, "EPS:09:ID:MPS:RF:PERM", string=True)
#     photon_shutter_1 = Component(EpicsSignalRO, "EPS:09:ID:PS1:POSITION", string=True)
#     photon_shutter_2 = Component(EpicsSignalRO, "EPS:09:ID:PS2:POSITION", string=True)
#     safety_shutter_1 = Component(EpicsSignalRO, "EPS:09:ID:SS1:POSITION", string=True)
#     safety_shutter_2 = Component(EpicsSignalRO, "EPS:09:ID:SS2:POSITION", string=True)


class DiagnosticsParameters(Device):
    """for beam line diagnostics and post-mortem analyses"""
    beam_in_hutch_swait = Component(
        apstools.synApps.SwaitRecord,
        "usxLAX:blCalc:userCalc1")

    PSS = Component(PSS_Parameters)
    #BL_EPS = Component(BLEPS_Parameters)
    #FE_EPS = Component(FEEPS_Parameters)

    @property
    def beam_in_hutch(self):
        return self.beam_in_hutch_swait.calculated_value.get() #!= 0

diagnostics = DiagnosticsParameters(name="diagnostics")
sd.baseline.append(diagnostics)
