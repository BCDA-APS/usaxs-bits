"""
Plans for USAXS scan operations.

This module provides plans for performing USAXS (Ultra Small Angle X-ray
Scattering) scans, including both standard USAXS and side-bounce USAXS (SBUSAXS)
configurations.
"""

import logging
import math
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry
from apstools.plans import write_stream
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import plan

from ..utils.emails import NOTIFY_ON_SCAN_DONE
from ..utils.emails import send_notification

# Add these imports at the top of the file
from ..utils.ustep import Ustep
from .mono_feedback import MONO_FEEDBACK_ON

# Device instances
# I0 = oregistry["I0"]
I00 = oregistry["I00"]
trd = oregistry["TRD"]
upd = oregistry["UPD"]

I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
trd_controls = oregistry["trd_controls"]
upd_controls = oregistry["upd_controls"]

a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]

logger = logging.getLogger(__name__)


@plan
def uascan(
    start: float,
    reference: float,
    finish: float,
    minStep: float,
    exponent: float,
    intervals: int,
    count_time: float,
    dx0: float,
    SDD_mm: float,
    ax0: float,
    SAD_mm: float,
    useDynamicTime: bool = True,
    md: Optional[Dict[str, Any]] = None,
):
    """Execute a USAXS scan with variable step size.

    This function performs a USAXS scan with step size that varies with distance
    from a reference point. It supports both standard USAXS and side-bounce USAXS
    (SBUSAXS) configurations.

    Parameters
    ----------
    start : float
        Starting position in degrees
    reference : float
        Reference position in degrees
    finish : float
        Finishing position in degrees
    minStep : float
        Minimum step size in degrees
    exponent : float
        Exponent for step size calculation
    intervals : int
        Number of intervals for the scan
    count_time : float
        Count time per point in seconds
    dx0 : float
        Initial dx position in mm
    SDD_mm : float
        Sample to detector distance in mm
    ax0 : float
        Initial ax position in mm
    SAD_mm : float
        Sample to analyzer distance in mm
    useDynamicTime : bool, optional
        Whether to use dynamic time adjustment, by default True
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

    USAGE:  ``RE(uascan(start, reference, finish, minStep, exponent, intervals,
    count_time, dx0, SDD_mm, ax0, SAD_mm))``
    """
    from ..startup import bec

    if md is None:
        md = {}

    if intervals <= 0:
        raise ValueError(f"intervals must be >0, given: {intervals}")

    # set heading for scans to show if we are running USAXS or SBUSAXS
    scan_cmd = (
        "uascan"
        f" ar {start} {reference} {finish} {minStep}"
        f" {dx0} {SDD_mm}"
        f" {ax0} {SAD_mm}"
        f" {exponent} {intervals} {count_time}"
    )
    plan_args = dict(
        start=start,
        reference=reference,
        finish=finish,
        minStep=minStep,
        dx0=dx0,
        SDD_mm=SDD_mm,
        ax0=ax0,
        SAD_mm=SAD_mm,
        exponent=exponent,
        intervals=intervals,
        count_time=count_time,
    )

    count_time_base = count_time

    # stop scaler, if it is counting
    yield from bps.mv(
        scaler0.count,
        0,
        scaler0.preset_time,
        count_time,
        scaler0.count_mode,
        "OneShot",
        upd_controls.auto.mode,
        "automatic",
        I0_controls.auto.mode,
        "manual",
        I00_controls.auto.mode,
        "manual",
        usaxs_shutter,
        "open",
    )

    # original values before scan
    prescan_positions = {
        "sy": s_stage.y.position,
        "dx": d_stage.x.position,
        "ax": a_stage.x.position,
        "ar": a_stage.r.position,
    }

    # devices which are recorded in the "primary" stream
    read_devices = [
        m_stage.r.user_readback,
        a_stage.r.user_readback,
        a_stage.x.user_readback,
        s_stage.y.user_readback,
        d_stage.x.user_readback,
        scaler0,
        upd_controls.auto.gain,
        I0_controls.auto.gain,
        I00_controls.auto.gain,
        trd_controls.auto.gain,
        upd_controls.auto.reqrange,
        I0_controls.auto.reqrange,
        I00_controls.auto.reqrange,
        trd_controls.auto.reqrange,
    ]

    bec.enable_table()

    # do not report the "quiet" detectors/stages during a uascan
    quiet_detectors = [
        I00,
        trd,
    ]
    quiet_stages = [
        m_stage.r,
        m_stage.x,
        m_stage.y,
        a_stage.y,
        s_stage.x,
        s_stage.y,
        d_stage.y,
    ]
    for obj in quiet_detectors:
        obj.kind = "omitted"
    for obj in quiet_stages:
        obj.kind = "omitted"
        obj.user_setpoint.kind = "omitted"
        obj.user_readback.kind = "omitted"

    if terms.USAXS.useSBUSAXS.get():
        scan_cmd = "sb" + scan_cmd

    ar_series = Ustep(start, reference, finish, intervals, exponent, minStep)

    _md = OrderedDict()
    _md.update(md or {})
    _p = scan_cmd.find(" ")
    _md["plan_name"] = scan_cmd[:_p]
    _md["plan_args"] = plan_args
    _md["uascan_factor"] = ar_series.factor
    _md["uascan_direction"] = ar_series.sign
    _md["useSBUSAXS"] = str(terms.USAXS.useSBUSAXS.get())
    _md["start"] = start
    _md["center"] = reference
    _md["finish"] = finish
    _md["intervals"] = intervals
    _md["exponent"] = exponent
    _md["minStep"] = minStep
    _md["dx0"] = dx0
    _md["SDD_mm"] = SDD_mm
    _md["ax0"] = ax0
    _md["SAD_mm"] = SAD_mm
    _md["useDynamicTime"] = str(useDynamicTime)

    def _triangulate_(angle: float, dist: float) -> float:
        """Calculate triangulated offset given angle of rotation.

        Parameters
        ----------
        angle : float
            Angle of rotation in degrees
        dist : float
            Distance in mm

        Returns
        -------
        float
            Triangulated offset in mm
        """
        return dist * math.tan(angle * math.pi / 180)

    @bpp.run_decorator(md=_md)
    def _scan_():
        count_time = count_time_base

        ar0 = terms.USAXS.center.AR.get()
        sy0 = s_stage.y.position
        for i, target_ar in enumerate(ar_series.stepper()):
            if useDynamicTime:
                if i / intervals < 0.33:
                    count_time = count_time_base / 3
                elif i / intervals < 0.66:
                    count_time = count_time_base
                else:
                    count_time = count_time_base * 2

            # track ay & dy on scattered beam position
            target_ax = ax0 + _triangulate_(target_ar - ar0, SAD_mm)
            target_dx = dx0 + _triangulate_(target_ar - ar0, SDD_mm)

            # re-position the sample before each step
            target_sy = sy0 + i * terms.USAXS.sample_y_step.get()

            moves = [
                a_stage.r,
                target_ar,
                a_stage.x,
                target_ax,
                d_stage.x,
                target_dx,
                s_stage.y,
                target_sy,
                scaler0.preset_time,
                count_time,
            ]

            if terms.USAXS.useSBUSAXS.get():
                # adjust the ASRP piezo on the AS side-bounce stage
                # tanBragg = math.tan(reference * math.pi / 180)
                # cosScatAngle = math.cos((reference - target_ar) * math.pi / 180)
                pass

            yield from user_data.set_state_plan(f"moving motors {i + 1}/{intervals}")
            yield from bps.mv(*moves)

            # count
            yield from user_data.set_state_plan(f"counting {i + 1}/{intervals}")
            yield from bps.trigger(scaler0, group="uascan_count")  # start the scaler
            yield from bps.wait(group="uascan_count")  # wait for the scaler

            # collect data for the primary stream
            yield from write_stream(read_devices, "primary")

            if useDynamicTime:
                if i < intervals / 3:
                    count_time = count_time_base / 2
                elif intervals / 3 <= i < intervals * 2 / 3:
                    count_time = count_time_base
                else:
                    count_time = 2 * count_time_base

    def _after_scan_():
        yield from bps.mv(
            # indicate USAXS scan is not running
            terms.USAXS.scanning,
            0,
            # monochromator.feedback.on,
            # MONO_FEEDBACK_ON,
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
            I0_controls.auto.mode,
            "manual",
            I00_controls.auto.mode,
            "manual",
            # close the shutter after each scan to preserve the detector
            usaxs_shutter,
            "close",
        )
        yield from MONO_FEEDBACK_ON()
        yield from user_data.set_state_plan("returning AR, AX, SY, and DX")

        motor_resets = [
            # reset motors to pre-scan positions: AY, SY, DY, and "the first motor" (AR)
            s_stage.y,
            prescan_positions["sy"],
            d_stage.x,
            prescan_positions["dx"],
            a_stage.x,
            prescan_positions["ax"],
            a_stage.r,
            prescan_positions["ar"],
        ]
        yield from bps.mv(*motor_resets)  # all at once

        for obj in quiet_detectors:
            obj.kind = "hinted"  # TODO: correct value?
        for obj in quiet_stages:
            obj.kind = 3  # config|normal
            obj.user_setpoint.kind = "normal"
            obj.user_readback.kind = "hinted"

    # run the scan
    yield from _scan_()
    yield from _after_scan_()

    yield from user_data.set_state_plan("USAXS scan complete")

    # Use the improved send_notification function
    send_notification(
        "USAXS scan complete",
        f"USAXS scan from {start} to {finish} with {intervals} points is complete.",
        notify_flag=NOTIFY_ON_SCAN_DONE,
    )

    yield from bps.mv(
        user_data.collection_in_progress,
        0,  # despite the label, 0 means not collecting
    )
