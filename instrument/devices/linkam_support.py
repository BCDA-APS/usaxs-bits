"""
Linkam temperature controllers
This is modified version of APS tools devices code
for new linkam TC1 version
++++++++++++++++++++++++++++++

.. autosummary::

   ~Linkam_T96_Device
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import EpicsSignalWithRBV
from ophyd import Signal

#from apstools.devices import PVPositionerSoftDoneWithStop
from apstools.devices import PVPositionerSoftDone



#this makes temperature to automatically start heating when changed
class T96Temperature(PVPositionerSoftDoneWithStop):
    actuate = Component(EpicsSignal, "STARTHEAT", kind="config", string=True)
    actuate_value = "On"



class Linkam_T96_Device(Device):
    """
    Linkam model T96 temperature controller
    Linux ioc version

    EXAMPLE::

        tc1 = Linkam_T96("IOC:tc1:", name="tc1")
    
    to get temperature, ramprate etc:
    linkam_tc1.temperature.position which returns the current T in C

    """
    #use linkam.temperature.position to get the value, this is positoner... 
    controller_name = "Linkam T96"
    temperature = Component(
        T96Temperature,
        "",
        readback_pv="TEMP",
        setpoint_pv="SETPOINT:SET",
        tolerance=1.0,
        kind="hinted",
    )
    ramprate = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="RAMPRATE",
        setpoint_pv="RAMPRATE:SET",
        tolerance=1.0,
        kind="hinted",
    )
    units = Component(Signal, value="C", kind="config")
    controller_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    heater_power = Component(EpicsSignalRO, "POWER", kind="omitted")
    lnp_mode = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="LNP_MODE",
        setpoint_pv="LNP_MODE:SET",
        #tolerance=1.0,
        kind="omitted",
    )
    lnp_speed = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="LNP_SPEED",
        setpoint_pv="LNP_SPEED:SET",
        #tolerance=1.0,
        kind="omitted",
    )
    pressure = Component(EpicsSignalRO, "PRESSURE", kind="omitted")
    vacuum = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="VACUUM",
        setpoint_pv="VACUUM:SET",
        #tolerance=1.0,
        kind="omitted",
    )
    humidity = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="HUMIDITY",
        setpoint_pv="HUMIDITY:SET",
        #tolerance=1.0,
        kind="omitted",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # temperature component is the main value
        self.temperature.name = self.name

    # these are unused or old things we are not using
    # # #ramp_at_limit = Component(EpicsSignalRO, "rampAtLimit_RBV", kind="omitted")
    # stage_config = Component(EpicsSignalRO, "STAGE:CONFIG", kind="omitted")
    # status_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    # vacuum = Component(EpicsSignal, "VACUUM:SET", kind="omitted")
    # vacuum_at_limit = Component(EpicsSignalRO, "VACUUM", kind="omitted")
    # # #vacuum_limit_readback = Component(EpicsSignalWithRBV, "vacuumLimit", kind="omitted")
    # vacuum_status = Component(EpicsSignalRO, "STAT:VAC:CNTRL", kind="omitted")  # calc
    # controller_config = Component(EpicsSignalRO, "CONFIG", kind="omitted")
    # controller_status = Component(EpicsSignalRO, "STATUS", kind="omitted")
    #humidity = Component(EpicsSignalRO, "HUMIDITY", kind="omitted")
    # lnp_mode = Component(EpicsSignal, "LNP_MODE:SET", kind="omitted")
    # lnp_speed = Component(EpicsSignalWithRBV, "LNP_SPEED:SET", kind="omitted")
    # lnp_status = Component(EpicsSignalRO, "STAT:LNP:PUMPING", kind="omitted")
    #vacuum = Component(EpicsSignalRO, "VACUUM", kind="omitted")

        # alias("$(P):CTRLLR:ERR", "$(PA)$(TA):controllerError_RBV")
        # alias("$(P):CONFIG", "$(PA)$(TA):controllerConfig_RBV")
        # alias("$(P):STATUS", "$(PA)$(TA):controllerStatus_RBV")
        # alias("$(P):STAGE:CONFIG", "$(PA)$(TA):stageConfig_RBV")
        # alias("$(P):TEMP", "$(PA)$(TA):temperature_RBV")
        # alias("$(P):STARTHEAT", "$(PA)$(TA):heating")
        # alias("$(P):RAMPRATE:SET", "$(PA)$(TA):rampRate")
        # alias("$(P):RAMPRATE", "$(PA)$(TA):rampRate_RBV")
        # alias("$(P):SETPOINT:SET", "$(PA)$(TA):rampLimit")
        # alias("$(P):SETPOINT", "$(PA)$(TA):rampLimit_RBV")
        # alias("$(P):POWER", "$(PA)$(TA):heaterPower_RBV")
        # alias("$(P):LNP_SPEED", "$(PA)$(TA):lnpSpeed_RBV")
        # alias("$(P):LNP_MODE:SET", "$(PA)$(TA):lnpMode")
        # alias("$(P):LNP_SPEED:SET", "$(PA)$(TA):lnpSpeed")
