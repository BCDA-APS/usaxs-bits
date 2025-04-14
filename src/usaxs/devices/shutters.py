"""
shutters
"""

from apstools.devices import ApsPssShutterWithStatus
from ophyd import Component
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent


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
    pss_state_open_values = [1, "ON"]
    pss_state_closed_values = [0, "OFF"]


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
# pvstatus = PA:20ID:STA_A_FES_OPEN_PL or B_SBS results on "OFF" or "ON"
