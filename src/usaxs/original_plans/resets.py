"""
Reset the instrument.
"""

__all__ = [
    "reset_USAXS",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps

from ..devices import I00
from ..devices import I000
from ..devices import NOTIFY_ON_RESET
from ..devices import AutorangeSettings
from ..devices import I0_controls
from ..devices import I00_controls
from ..devices import a_stage  # as_stage
from ..devices import d_stage  # as_stage
from ..devices import email_notices
from ..devices import m_stage  # as_stage
from ..devices import s_stage  # as_stage
from ..devices import scaler0
from ..devices import terms
from ..devices import usaxs_shutter
from ..devices import trd
from ..devices import upd_controls
from ..devices import user_data
from .mode_changes import mode_USAXS
from .mono_feedback import DCMfeedbackON


def reset_USAXS():
    """
    bluesky plan to set USAXS instrument in safe configuration
    """
    logger.info("Resetting USAXS")
    yield from mode_USAXS()
    yield from user_data.set_state_plan("resetting motors")
    yield from DCMfeedbackON()
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
    if NOTIFY_ON_RESET:
        email_notices.send(
            "USAXS has reset", "spec has encountered a problem and reset the USAXS."
        )

    yield from bps.mv(
        user_data.collection_in_progress,
        0,  # despite the label, 0 means not collecting
    )
