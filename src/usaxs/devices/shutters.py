"""
shutters
"""

from typing import List
from typing import Union

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
    open_signal: Component[EpicsSignal] = Component(EpicsSignal, "Open")
    close_signal: Component[EpicsSignal] = Component(EpicsSignal, "Close")
    # bi record ZNAM=OFF, ONAM=ON
    pss_state: FormattedComponent[EpicsSignalRO] = FormattedComponent(
        EpicsSignalRO, "{self.state_pv}"
    )
    pss_state_open_values: List[Union[int, str]] = [1, "ON"]
    pss_state_closed_values: List[Union[int, str]] = [0, "OFF"]

    # Configurable default timeout (can be overridden per instance)
    default_timeout = 20  # seconds

    def open(self, timeout=None):
        """request the shutter to open with configurable timeout"""
        if timeout is None:
            timeout = self.default_timeout
        return super().open(timeout=timeout)

    def close(self, timeout=None):
        """request the shutter to close with configurable timeout"""
        if timeout is None:
            timeout = self.default_timeout
        return super().close(timeout=timeout)


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
