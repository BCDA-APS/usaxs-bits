"""
PSS shutter device for the 12-ID-E USAXS instrument.

``My12IdPssShutter``
    Subclass of ``ApsPssShutterWithStatus`` with configurable open/close/status
    PVs (supplied via YAML config) and a configurable default timeout.
"""

from typing import List
from typing import Union

from apstools.devices import ApsPssShutterWithStatus
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent


class My12IdPssShutter(ApsPssShutterWithStatus):
    """APS PSS shutter at 12-ID-E with configurable PVs and timeout.

    Open and close PVs are bo records that self-reset after a short time;
    write ``1`` to command a move.  The status PV is a bi record with
    ``ZNAM=OFF`` (closed) and ``ONAM=ON`` (open).

    ======  =================  =====
    action  FormattedComponent value
    ======  =================  =====
    open    ``open_signal``    1
    close   ``close_signal``   1
    ======  =================  =====

    PV strings (``open_pv``, ``close_pv``, ``state_pv``) are set per instance
    via YAML configuration and interpolated by ``FormattedComponent``.
    """

    # bo records that reset after a short time, set to 1 to move
    # Use FormattedComponent so open_pv/close_pv can be set per instance via YAML config
    open_signal = FormattedComponent(EpicsSignal, "{self.open_pv}")
    close_signal = FormattedComponent(EpicsSignal, "{self.close_pv}")
    # bi record ZNAM=OFF, ONAM=ON
    pss_state = FormattedComponent(EpicsSignalRO, "{self.state_pv}")
    pss_state_open_values: List[Union[int, str]] = [1, "ON"]
    pss_state_closed_values: List[Union[int, str]] = [0, "OFF"]

    # Configurable default timeout (can be overridden per instance)
    default_timeout = 20  # seconds

    def __init__(self, prefix, state_pv, *args, default_timeout: float = 20, **kwargs):
        # open_pv and close_pv are passed through **kwargs to ApsPssShutter.__init__,
        # which sets self.open_pv and self.close_pv before Device.__init__ creates signals.
        super().__init__(prefix, state_pv, *args, **kwargs)
        self.default_timeout = default_timeout

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


