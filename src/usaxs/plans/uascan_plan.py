"""
Variable step-size USAXS scan plan.

``uascan`` performs a USAXS scan whose step size grows geometrically with
distance from the beam centre, implementing the logarithmic q-space sampling
used at 12-ID-E.
"""

import logging
import math
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from apstools.plans import write_stream
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import plan

from ..utils.count_time import quantize_count_time
from ..utils.emails import NOTIFY_ON_SCAN_DONE
from ..utils.emails import send_notification
from ..utils.ustep import Ustep
from .fx4_setup import check_ring_overflows
from .fx4_setup import enable_fx4_autorange
from .fx4_setup import prepare_fx4_counting
from .fx4_setup import usaxs_electrometers
from .mono_feedback import MONO_FEEDBACK_ON

# Device instances
I0 = oregistry["I0"]
I00 = oregistry["I00"]
trd = oregistry["TRD"]
# fx4 carries UPD and TRD, fx42 carries I0 and I00.  Both are read at every
# point, so I0 lands in the same document as UPD -- the shared scaler gate used
# to give that for free.
FX4_DETECTORS = usaxs_electrometers()

upd_controls = oregistry["upd_controls"]

a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
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
    md=None,
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
        If ``True``, count time is scaled by thirds across the scan range
        (shorter near the centre, longer at high q), by default True.
    md : dict, optional
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(uascan(start, reference, finish, minStep, exponent, intervals,
    count_time, dx0, SDD_mm, ax0, SAD_mm))``
    """
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

    yield from prepare_fx4_counting(count_time)
    # UPD ranges live through the scan: the signal falls many decades from the
    # rocking-curve peak out to high q.  Through enable_fx4_autorange so
    # seq01:channel is pointed at UPD first -- the transmission measurement
    # that runs just before this leaves it on TRD, and one Range serves both.
    yield from enable_fx4_autorange(upd_controls, "automatic")
    # I0 and I00 stay on their fixed range; they have no sequence program.
    yield from bps.mv(usaxs_shutter, "open")

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
        *FX4_DETECTORS,
        # Range diagnostics.  Nothing downstream divides by these -- the FX4
        # reading is gain-independent -- but a range that railed mid-scan has
        # to be visible afterwards.  Only UPD has a sequence program.
        upd_controls.auto.lurange,
        upd_controls.auto.reqrange,
    ]

    # Do not report the "quiet" detectors/stages during a uascan.
    # TRD shares usxFX4's single Range with UPD, which the autoranger is
    # optimising for the scattered beam, so TRD is railed for the whole scan
    # and its value is meaningless here.  I00 has nothing connected.  Setting
    # them "omitted" keeps them out of the parent electrometer's read.
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
    # Recorded in the "primary" stream but NOT plotted by BestEffortCallback.
    # Anything left "hinted" gets its own LivePlot axes; for a uascan the only
    # useful plot is UPD vs AR, so demote every other hinted field to "normal".
    # (I0 stays hinted: it is named in the "dimensions" hint below, which keeps
    # it in the LiveTable while excluding it from the plot columns.)
    unplotted_signals = [
        a_stage.x.user_readback,
        d_stage.x.user_readback,
    ]

    # remember every kind we touch so it can be restored after the scan
    new_kinds = {}
    for obj in quiet_detectors:
        new_kinds[obj] = "omitted"
    for obj in quiet_stages:
        new_kinds[obj] = "omitted"
        new_kinds[obj.user_setpoint] = "omitted"
        new_kinds[obj.user_readback] = "omitted"
    for obj in unplotted_signals:
        new_kinds[obj] = "normal"

    original_kinds = {obj: obj.kind for obj in new_kinds}
    for obj, kind in new_kinds.items():
        obj.kind = kind

    if terms.USAXS.useSBUSAXS.get():
        scan_cmd = "sb" + scan_cmd

    ar_series = Ustep(start, reference, finish, intervals, exponent, minStep)

    _md = OrderedDict(md or {})
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
    # Same marker name as the fly-scan and areaDetector files: signals that
    # UPD / I0 are gain-independent picoamps, not counts per second.
    _md["counting_chain"] = "FX4"
    # Tell BestEffortCallback that AR is the independent variable.  Without this
    # hint BEC guesses "time" as the x axis and plots every hinted field.
    # The first field is the x axis; the rest are shown in the LiveTable only.
    _md["hints"] = {"dimensions": [[["a_stage_r", "I0"], "primary"]]}

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
            ]
            # Same dwell on both electrometers, set alongside the stage moves
            # the way scaler0.preset_time used to be.  Quantised to whole mains
            # cycles: useDynamicTime divides the base by three, which otherwise
            # lands mid-cycle and leaves 60 Hz pickup that averaging cannot
            # remove.
            dwell = quantize_count_time(count_time)
            for det in FX4_DETECTORS:
                moves += [det.averaging_time, dwell]

            # Suspender rewind boundary, one per point.  The run is already open
            # here (see the run_decorator above), so the checkpoint must live
            # inside the loop rather than before uascan() -- a replay that
            # re-issued open_run would raise IllegalMessageSequence.  A beam-loss
            # suspension therefore redoes only the current point instead of
            # replaying the whole USAXSscanStep setup (filters, stage moves,
            # Blackfly optical image).
            yield from bps.checkpoint()

            yield from user_data.set_state_plan(f"moving motors {i + 1}/{intervals}")
            yield from bps.mv(*moves)

            # count
            yield from user_data.set_state_plan(f"counting {i + 1}/{intervals}")
            # Fire both electrometers before waiting on either, so the two
            # integration windows are offset by one channel-access round trip
            # rather than by a whole exposure.  UPD and I0 are on separate
            # boxes now; the scaler used to gate them from one clock.
            for det in FX4_DETECTORS:
                yield from bps.trigger(det, group="uascan_count")
            yield from bps.wait(group="uascan_count")

            # collect data for the primary stream
            yield from write_stream(read_devices, "primary")

    def _after_scan_():
        yield from bps.mv(
            # indicate USAXS scan is not running
            terms.USAXS.scanning,
            0,
            # close the shutter after each scan to preserve the detector
            usaxs_shutter,
            "close",
        )
        yield from enable_fx4_autorange(upd_controls, "auto+background")
        # A ring-buffer overflow biases every mean toward the end of its count
        # and shows up nowhere else in the data.
        yield from check_ring_overflows(FX4_DETECTORS, "uascan")
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

        for obj, kind in original_kinds.items():
            obj.kind = kind

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
