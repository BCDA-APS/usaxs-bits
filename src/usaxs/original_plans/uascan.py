"""
USAXS step scan
"""

__all__ = [
    "uascan",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import math
from collections import OrderedDict

from apstools.plans import write_stream
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from ..devices import I00
from ..devices import I000
from ..devices import MONO_FEEDBACK_ON
from ..devices import I0_controls
from ..devices import I00_controls
from ..devices import a_stage  # , as_stage
from ..devices import d_stage  # , as_stage

# from ..devices import fuel_spray_bit
from ..devices import m_stage  # , as_stage
from ..devices import monochromator
from ..devices import s_stage  # , as_stage
from ..devices import scaler0
from ..devices import terms
from ..devices import usaxs_shutter
from ..devices import trd
from ..devices import trd_controls
from ..devices import upd_controls
from ..devices import user_data
from ..usaxs_support.ustep import Ustep

### notes for preliminary testing
# uascan()
# center: 8.746588
# start: -0.0003 1/A (Q) --> -0.0008 degrees = 8.7474
# finish: 0.3 1/A (Q) --> 0.8 degrees = 7.9
# minstep = 0.000025 degrees
# exponent = 1.0
# intervals = 200
# count time = 1 s
# DX0 = 12.83
# SDD = 910
# ax0 = 0
# SAD = 215

# Ustep(8.7474, 8.746588, 7.9, 200, 1, 0.000025)
# uascan(8.7474, 8.746588, 7.9, 0.000025, 1, 200, 1, 12.83, 910, 0, 215)


def uascan(
    start,
    reference,
    finish,
    minStep,
    exponent,
    intervals,
    count_time,
    dx0,
    SDD_mm,
    ax0,
    SAD_mm,
    useDynamicTime=True,
    md={},
):
    """
    USAXS ascan (step size varies with distance from a reference point)
    """
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
    # asrp0 = as_stage.rp.position
    prescan_positions = {
        "sy": s_stage.y.position,
        "dx": d_stage.x.position,
        "ax": a_stage.x.position,
        "ar": a_stage.r.position,
        #'asrp' : asrp0,
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

    # do not report the "quiet" detectors/stages during a uascan
    quiet_detectors = [
        # I0,
        I00,
        I000,
        # upd2,
        trd,
    ]
    quiet_stages = [
        m_stage.r,
        m_stage.x,
        m_stage.y,
        # a_stage.r,
        # a_stage.x,
        a_stage.y,
        s_stage.x,
        s_stage.y,
        # d_stage.x,
        d_stage.y,
    ]
    for obj in quiet_detectors:
        obj.kind = "omitted"
    for obj in quiet_stages:
        obj.kind = "omitted"
        obj.user_setpoint.kind = "omitted"
        obj.user_readback.kind = "omitted"

    if terms.USAXS.useSBUSAXS.get():
        # read_devices.append(as_stage.rp)
        scan_cmd = "sb" + scan_cmd
        # TODO: anything else?

    ar_series = Ustep(start, reference, finish, intervals, exponent, minStep)
    # print(f"factor={ar_series.factor} for {len(ar_series.series())} points")

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

    def _triangulate_(angle, dist):
        """triangulate offset, given angle of rotation"""
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
                tanBragg = math.tan(reference * math.pi / 180)
                cosScatAngle = math.cos((reference - target_ar) * math.pi / 180)
                diff = math.atan(tanBragg / cosScatAngle) * 180 / math.pi - reference

                # Note on asrp adjustment:  NOTE: seems wrong, but may need to be revisited???
                #   use "-" when reflecting  inboard towards storage ring (single bounce setup)
                #   use "+" when reflecting outboard towards experimenters (channel-cut setup)
                ### on 2/06/2002 Andrew realized, that we are moving in wrong direction
                ## the sign change to - moves ASRP towards larger Bragg angles...
                ## verified experimentally - higher voltage on piezo = lower Bragg angle...
                ## and we need to INCREASE the Bragg Angle with increasing Q, to correct for tilt down...

                # asrp_vdc = asrp0 - diff/terms.usaxs.asrp_degrees_per_VDC.get()
                # moves += [as_stage.rp, asrp_vdc]

            # added for fuel spray users as indication that we are counting...
            # moves += [fuel_spray_bit, 1]

            yield from user_data.set_state_plan(f"moving motors {i+1}/{intervals}")
            yield from bps.mv(*moves)

            # count
            yield from user_data.set_state_plan(f"counting {i+1}/{intervals}")
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
            #monochromator.feedback.on,
            #MONO_FEEDBACK_ON,
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
        # if terms.USAXS.useSBUSAXS.get():
        # motor_resets += [as_stage.rp, prescan_positions["asrp"]]
        yield from bps.mv(*motor_resets)  # all at once

        for obj in quiet_detectors:
            obj.kind = "hinted"  # TODO: correct value?
        for obj in quiet_stages:
            obj.kind = 3  # config|normal
            obj.user_setpoint.kind = "normal"
            obj.user_readback.kind = "hinted"

        # TODO: #588 reduce 1-D data in NX file

    # run the scan
    # TODO: implement try..except..else..finally stanza for error handling
    yield from _scan_()
    yield from _after_scan_()
