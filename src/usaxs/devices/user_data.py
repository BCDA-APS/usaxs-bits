"""
EPICS data about the user
"""

# apsbss

import logging
from typing import Any
from typing import Callable
from typing import Optional

from apstools.utils import trim_string_for_EPICS
from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal

logger = logging.getLogger(__name__)

# from apstools.devices import ApsBssUserInfoDevice
# from apsbss.apsbss_ophyd import EpicsBssDevice

# TODO: bss is likely completely wrong, we have new support. Check with Pete.


class EpicsSampleNameDevice(EpicsSignal):
    """
    Enable the user to supply a function that modifies
    the sample name during execution of a plan.

    see: https://github.com/APS-USAXS/ipython-usaxs/issues/428

    EXAMPLE:

        >>> def handler(title):
        ...     return f"USAXS sample: {title}"

        >>> user_data.sample_title.register_handler(handler)

        >>> RE(bps.mv(user_data.sample_title, "Glassy Carbon"))
        >>> user_data.sample_title.get()
        USAXS sample: Glassy Carbon

    """

    _handler: Optional[Callable[[str], str]] = None

    def set(self, value: str, **kwargs: Any) -> Any:
        """Modify value per user function before setting the PV"""
        logger.debug("self._handler: %s", self._handler)
        if self._handler is not None:
            value = self._handler(value)
        return super().set(value, **kwargs)

    def register_handler(
        self, handler_function: Optional[Callable[[str], str]] = None
    ) -> None:
        """
        Register the supplied function to be called
        when this signal is to be written.  The function
        accepts the default sample title as the only argument
        and *must* return a string value (as shown in the
        example above).
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
    """
    Device for storing and retrieving user data during experiments.

    This device provides access to various user-related parameters such as
    sample information, user identification, and experiment state.
    """

    GUP_number: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:GUPNumber")
    macro_file: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:macroFile")
    macro_file_time: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:macroFileTime"
    )
    run_cycle: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:RunCycle")
    sample_thickness: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:sampleThickness"
    )
    sample_title: Component[EpicsSampleNameDevice] = Component(
        EpicsSampleNameDevice, "usxLAX:sampleTitle", string=True
    )
    scanning: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:USAXS:scanning")
    scan_macro: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:scanMacro")
    spec_file: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:specFile", string=True
    )
    spec_scan: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:specScan", string=True
    )
    state: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:state", string=True, write_timeout=0.1
    )
    time_stamp: Component[EpicsSignal] = Component(EpicsSignal, "usxLAX:timeStamp")
    user_dir: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:userDir", string=True
    )
    user_name: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:userName", string=True
    )

    # for GUI to know if user is collecting data: 0="On", 1="Off"
    collection_in_progress: Component[EpicsSignal] = Component(
        EpicsSignal, "usxLAX:dataColInProgress"
    )

    def set_state_plan(self, msg: str, confirm: bool = True):
        """plan: tell EPICS about what we are doing"""
        msg = trim_string_for_EPICS(msg)
        try:
            yield from bps.abs_set(self.state, msg, wait=confirm)
        except Exception as exc:
            logger.warning("Exception while reporting instrument state: %s", exc)

    def set_state_blocking(self, msg: str) -> None:
        """ophyd: tell EPICS about what we are doing"""
        msg = trim_string_for_EPICS(msg)
        try:
            if len(msg) > 39:
                logger.debug("truncating long status message: %s", msg)
                msg = msg[:35] + " ..."
            self.state.put(msg)
        except Exception as exc:
            logger.error("Could not put message (%s) to USAXS state PV: %s", msg, exc)
