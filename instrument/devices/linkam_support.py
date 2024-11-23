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

from apstools.devices import PVPositionerSoftDoneWithStop



class T96Temperature(PVPositionerSoftDoneWithStop):
    actuate = Component(EpicsSignalWithRBV, "heating", kind="config", string=True)
    actuate_value = "On"



class Linkam_T96_Device(Device):
    """
    Linkam model T96 temperature controller
    Linux ioc version

    EXAMPLE::

        tc1 = Linkam_T96("IOC:tc1:", name="tc1")
    """

    controller_name = "Linkam T96"

    temperature = Component(
        T96Temperature,
        "",
        readback_pv="TEMP",
        setpoint_pv="SETPOINT:SET",
        tolerance=1.0,
        kind="hinted",
    )

    ramprate = Component(EpicsSignalWithRBV, "RAMPRATE:SET", kind="config")
    units = Component(Signal, value="C", kind="config")

    controller_config = Component(EpicsSignalRO, "CONFIG", kind="omitted")
    controller_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    controller_status = Component(EpicsSignalRO, "STATUS", kind="omitted")
    heater_power = Component(EpicsSignalRO, "POWER", kind="omitted")
    lnp_mode = Component(EpicsSignalWithRBV, "LNP_MODE:SET", kind="omitted")
    lnp_speed = Component(EpicsSignalWithRBV, "LNP_SPEED:SET", kind="omitted")
    lnp_status = Component(EpicsSignalRO, "STAT:LNP:PUMPING", kind="omitted")
    pressure = Component(EpicsSignalRO, "PRESSURE", kind="omitted")
    #ramp_at_limit = Component(EpicsSignalRO, "rampAtLimit_RBV", kind="omitted")
    stage_config = Component(EpicsSignalRO, "STAGE:CONFIG", kind="omitted")
    status_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    vacuum = Component(EpicsSignal, "VACUUM:SET", kind="omitted")
    vacuum_at_limit = Component(EpicsSignalRO, "VACUUM", kind="omitted")
    #vacuum_limit_readback = Component(EpicsSignalWithRBV, "vacuumLimit", kind="omitted")
    vacuum_status = Component(EpicsSignalRO, "STAT:VAC:CNTRL", kind="omitted")  # calc

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # temperature component is the main value
        self.temperature.name = self.name

