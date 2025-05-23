"""
Reset the instrument.
"""

import logging
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from ..devices import AutorangeSettings
from ..utils.emails import send_notification
from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_ON

from usaxs.utils.emails import NOTIFY_ON_RESET

logger = logging.getLogger(__name__)

# Device instances
I00 = oregistry["I00"]
I0 = oregistry["I0"]
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
trd = oregistry["trd"]
upd_controls = oregistry["upd_controls"]
user_data = oregistry["user_device"]


def reset_instrument(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """Reset the instrument to its default state.

    This function resets various components of the instrument to their
    default states, including detectors, motors, and other devices.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(reset_instrument())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner():
        yield from user_data.set_state_plan("resetting instrument")
        yield from bps.mv(scaler0.count_mode, "AutoCount")
        yield from bps.sleep(1)  # Allow time for reset

    return (yield from _inner())


def reset_USAXS():
    """
    bluesky plan to set USAXS instrument in safe configuration
    """
    logger.info("Resetting USAXS")
    yield from mode_USAXS()
    yield from user_data.set_state_plan("resetting motors")
    yield from MONO_FEEDBACK_ON()
    yield from bps.mv(
        scaler0.count_mode,
        SCALER_AUTOCOUNT_MODE,
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
        I0_controls.auto.mode,
        AutorangeSettings.manual,
        I00_controls.auto.mode,
        AutorangeSettings.manual,
        usaxs_shutter,
        "close",
        user_data.scanning,
        "no",
    )
    move_list = [
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
    ]
    if terms.USAXS.useSBUSAXS.get():
        pass
        # move_list += [
        #    as_stage.rp, terms.USAXS.ASRP0.get(),
        #    ]
    yield from bps.mv(*move_list)  # move all motors at once
    # fix omitted stuff from uascan see #584, #583
    trd.kind = "hinted"  # TODO: correct value?
    I00.kind = "hinted"  # TODO: correct value?
    I000.kind = "hinted"  # TODO: correct value?
    for obj in (m_stage.r, a_stage.r, a_stage.y, s_stage.y, d_stage.y):
        obj.kind = "normal"  # TODO: correct value?
        obj.user_setpoint.kind = "normal"  # TODO: correct value?
        obj.user_readback.kind = "hinted"  # TODO: correct value?

    yield from user_data.set_state_plan("USAXS reset complete")

    # Use the improved send_notification function
    send_notification(
        "USAXS has reset",
        "spec has encountered a problem and reset the USAXS.",
        notify_flag=NOTIFY_ON_RESET,
    )

    yield from bps.mv(
        user_data.collection_in_progress,
        0,  # despite the label, 0 means not collecting
    )
