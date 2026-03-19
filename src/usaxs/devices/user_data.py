"""
User and experiment metadata device for the 12-ID-E USAXS instrument.

``EpicsSampleNameDevice``
    EpicsSignal subclass that allows a user-supplied function to transform
    the sample name before it is written to EPICS (e.g. to prepend a prefix).

``UserDataDevice``
    Composite device exposing all user/experiment metadata PVs: GUP number,
    sample title, user name, run cycle, state string, file paths, etc.
"""

import logging
from typing import Callable
from typing import Optional

from apstools.utils import trim_string_for_EPICS
from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal

logger = logging.getLogger(__name__)


class EpicsSampleNameDevice(EpicsSignal):
    """EpicsSignal subclass that applies a user function before writing.

    Allows the user to register a callable that transforms the sample name
    before it is written to the EPICS PV.  If no handler is registered the
    value is passed through unchanged.

    Example::

        def handler(title):
            return f"USAXS sample: {title}"

        user_data.sample_title.register_handler(handler)

        RE(bps.mv(user_data.sample_title, "Glassy Carbon"))
        user_data.sample_title.get()
        # -> "USAXS sample: Glassy Carbon"

    See also: https://github.com/APS-USAXS/ipython-usaxs/issues/428
    """

    _handler: Optional[Callable[[str], str]] = None

    def set(self, value: str, **kwargs):
        """Apply the registered handler (if any) then write *value* to the PV."""
        logger.debug("self._handler: %s", self._handler)
        if self._handler is not None:
            value = self._handler(value)
        return super().set(value, **kwargs)

    def register_handler(
        self, handler_function: Optional[Callable[[str], str]] = None
    ) -> None:
        """Register (or clear) the sample-name transform function.

        Parameters
        ----------
        handler_function : callable or None
            A function that accepts the default sample title as its only
            argument and **must** return a ``str``.  Pass ``None`` to clear
            a previously registered handler and restore pass-through behaviour.

        Raises
        ------
        ValueError
            If *handler_function* does not return a ``str`` when called with
            the test string ``"test"``.
        """
        if handler_function is None:
            # clear the handler
            self._handler = None
        else:
            # Test the proposed handler before accepting it.
            # Next call will raise exception if user code has an error.
            test = handler_function("test")

            # User function must return a str result.
            if not isinstance(test, str):
                raise ValueError(
                    f"Sample name function '{handler_function.__name__}'"
                    "must return 'string' type,"
                    f" received {type(test).__name__}"
                )

            logger.debug(
                "Accepted Sample name handler function: %s", handler_function.__name__
            )
            self._handler = handler_function


class UserDataDevice(Device):
    """EPICS PVs holding user and experiment metadata for the current session.

    ``GUP_number``           — APS General User Proposal number.
    ``macro_file``           — name of the current command/macro file.
    ``macro_file_time``      — last-modified timestamp of the macro file.
    ``run_cycle``            — APS run cycle string (e.g. ``"2025-1"``).
    ``sample_thickness``     — sample thickness (mm).
    ``sample_title``         — sample name (:class:`EpicsSampleNameDevice`).
    ``sample_dir``           — sample working directory (:class:`EpicsSampleNameDevice`).
    ``scanning``             — non-zero while a USAXS scan is in progress.
    ``scan_macro``           — name of the currently running scan macro.
    ``spec_file``            — SPEC data file name.
    ``spec_scan``            — current SPEC scan number.
    ``state``                — free-form status string (max ~40 chars, ``write_timeout=0.1``).
    ``time_stamp``           — epoch timestamp of last update.
    ``user_dir``             — user data directory path.
    ``user_name``            — user name string.
    ``collection_in_progress``— 1 while data collection is active (GUI indicator).
    """

    GUP_number = Component(EpicsSignal, "usxLAX:GUPNumber")
    macro_file = Component(EpicsSignal, "usxLAX:macroFile")
    macro_file_time = Component(EpicsSignal, "usxLAX:macroFileTime")
    run_cycle = Component(EpicsSignal, "usxLAX:RunCycle")
    sample_thickness = Component(EpicsSignal, "usxLAX:sampleThickness")
    sample_title = Component(EpicsSampleNameDevice, "usxLAX:sampleTitle", string=True)
    sample_dir = Component(EpicsSampleNameDevice, "usxLAX:sampleDir", string=True)
    scanning = Component(EpicsSignal, "usxLAX:USAXS:scanning")
    scan_macro = Component(EpicsSignal, "usxLAX:scanMacro")
    spec_file = Component(EpicsSignal, "usxLAX:specFile", string=True)
    spec_scan = Component(EpicsSignal, "usxLAX:specScan", string=True)
    state = Component(EpicsSignal, "usxLAX:state", string=True, write_timeout=0.1)
    time_stamp = Component(EpicsSignal, "usxLAX:timeStamp")
    user_dir = Component(EpicsSignal, "usxLAX:userDir", string=True)
    user_name = Component(EpicsSignal, "usxLAX:userName", string=True)

    # 0 = collecting, 1 = idle (GUI indicator)
    collection_in_progress = Component(EpicsSignal, "usxLAX:dataColInProgress")

    def set_state_plan(self, msg: str, confirm: bool = True):
        """Bluesky plan: write *msg* to the EPICS state PV.

        The string is trimmed to EPICS character-field limits before writing.
        Exceptions are caught and logged as warnings so that a failed status
        update never aborts the enclosing plan.

        Parameters
        ----------
        msg : str
            Human-readable description of the current instrument activity.
        confirm : bool
            If ``True`` (default), wait for the PV to acknowledge the write
            before yielding control back to the RunEngine.
        """
        msg = trim_string_for_EPICS(msg)
        try:
            yield from bps.abs_set(self.state, msg, wait=confirm)
        except Exception as exc:
            logger.warning("Exception while reporting instrument state: %s", exc)

    def set_state_blocking(self, msg: str) -> None:
        """Write *msg* to the EPICS state PV outside of a Bluesky plan.

        Truncates *msg* to 39 characters (appending ``" ..."`` if truncated)
        to fit within the PV's character-field limit.  Exceptions are caught
        and logged as errors so that a failed status update never raises.

        Parameters
        ----------
        msg : str
            Human-readable description of the current instrument activity.
        """
        msg = trim_string_for_EPICS(msg)
        try:
            if len(msg) > 39:
                logger.debug("truncating long status message: %s", msg)
                msg = msg[:35] + " ..."
            self.state.put(msg)
        except Exception as exc:
            logger.error("Could not put message (%s) to USAXS state PV: %s", msg, exc)
