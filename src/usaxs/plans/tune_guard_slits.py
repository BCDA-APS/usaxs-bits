"""
tune the guard slits
"""

__all__ = """
    GuardSlitTuneError
    tune_Gslits
    tune_GslitsCenter
    tune_GslitsSize
""".split()

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import datetime
from collections import defaultdict

import pyRestTable
from apstools.plans import TuneAxis
from bluesky import plan_stubs as bps
from ophyd import Kind

from ..devices import MONO_FEEDBACK_OFF
from ..devices import MONO_FEEDBACK_ON
from ..devices import UPD_SIGNAL
from ..devices import I0_controls
from ..devices import I00_controls
from ..devices import autoscale_amplifiers
from ..devices import guard_slit
from ..devices import monochromator
from ..devices import scaler0
from ..devices import terms
from ..devices import ti_filter_shutter
from ..devices import upd_controls
from ..devices import usaxs_slit
from ..devices import user_data
from ..framework import RE
from ..utils.derivative import numerical_derivative
from ..utils.peak_centers import peak_center
from .filters import insertTransmissionFilters
from .mode_changes import mode_USAXS
from .requested_stop import IfRequestedStopBeforeNextScan


class GuardSlitTuneError(RuntimeError): ...  # custom error


def tune_GslitsCenter():
    """
    plan: optimize the guard slits' position

    tune to the peak centers
    """
    yield from IfRequestedStopBeforeNextScan()
    title = "tuning USAXS Gslit center"
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title,
        title,
        user_data.spec_scan,
        str(RE.md["scan_id"] + 1 + 1),  # TODO: Why SCAN_N+1?
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "tune_GslitCenter",
    )
    yield from user_data.set_state_plan("tune Guard slits center")

    yield from mode_USAXS()
    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
    )
    yield from bps.mv(ti_filter_shutter, "open")
    yield from insertTransmissionFilters()
    yield from bps.sleep(0.1)
    yield from user_data.set_state_plan("autoranging the PD")
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])
    yield from user_data.set_state_plan(title)

    old_preset_time = scaler0.preset_time.get()
    yield from bps.mv(scaler0.preset_time, 0.2)

    def tune_guard_slit_motor(motor, width, steps):
        if steps < 10:
            raise GuardSlitTuneError(
                f"Not enough points ({steps}) to tune guard slits."
            )

        x_c = motor.position
        x_0 = x_c - abs(width) / 2
        x_n = x_c + abs(width) / 2

        scaler0.select_channels([UPD_SIGNAL.chname.get()])
        scaler0.channels.chan01.kind = Kind.config

        tuner = TuneAxis([scaler0], motor, signal_name=UPD_SIGNAL.chname.get())
        yield from tuner.tune(width=-width, num=steps + 1)

        bluesky_runengine_running = RE.state != "idle"

        if bluesky_runengine_running:
            found = tuner.peak_detected()
            center = tuner.peaks.com  # center of mass

            table = pyRestTable.Table()
            table.addLabel("tune parameter")
            table.addLabel("fitted value")
            table.addRow(("peak detected?", found))
            table.addRow(("center of mass", center))
            table.addRow(("center from half max", tuner.peaks.cen))
            table.addRow(("peak max (x,y)", tuner.peaks.max))
            table.addRow(("FWHM", tuner.peaks.fwhm))
            logger.info(table)

            def cleanup_then_GuardSlitTuneError(msg):
                logger.warning(f"{motor.name}: move to {x_c} (initial position)")
                scaler0.select_channels(None)
                yield from bps.mv(
                    motor,
                    x_c,
                    scaler0.preset_time,
                    old_preset_time,
                    ti_filter_shutter,
                    "close",
                )
                raise GuardSlitTuneError(msg)

            if not found:
                yield from cleanup_then_GuardSlitTuneError(
                    f"{motor.name} Peak not found."
                )
            if center < x_0:  # sanity check that start <= COM
                msg = f"{motor.name}: Computed center too low: {center} < {x_0}"
                yield from cleanup_then_GuardSlitTuneError(msg)
            if center > x_n:  # sanity check that COM  <= end
                msg = f"{motor.name}: Computed center too high: {center} > {x_n}"
                yield from cleanup_then_GuardSlitTuneError(msg)
            if max(tuner.peaks.y_data) <= guard_slit.tuning_intensity_threshold:
                msg = f"{motor.name}: Peak intensity not strong enough to tune."
                msg += f" {max(tuner.peaks.y_data)} < {guard_slit.tuning_intensity_threshold}"
                yield from cleanup_then_GuardSlitTuneError(msg)

            logger.info(f"{motor.name}: move to {center} (center of mass)")
            yield from bps.mv(motor, center)

    # Here is the MAIN EVENT
    yield from tune_guard_slit_motor(guard_slit.y, 2, 50)
    yield from tune_guard_slit_motor(guard_slit.x, 4, 20)

    yield from bps.mv(scaler0.preset_time, old_preset_time)

    yield from bps.mv(ti_filter_shutter, "close")


def _USAXS_tune_guardSlits():
    """
    plan: (internal) this performs the guard slit scan

    Called from tune_GslitsSize()
    """
    # # define proper counters and set the geometry...
    # plotselect upd2
    # counters cnt_num(I0) cnt_num(upd2)

    # remember original motor positons
    original_position = dict(
        top=guard_slit.top.position,
        bot=guard_slit.bot.position,
        out=guard_slit.outb.position,
        inb=guard_slit.inb.position,
    )
    h_step_away = guard_slit.h_step_away
    v_step_away = guard_slit.v_step_away
    # h_step_into = guard_slit.h_step_into
    # v_step_into = guard_slit.v_step_into
    h_step_into = 2 * guard_slit.top.position
    v_step_into = 2 * guard_slit.outb.position

    table = pyRestTable.Table()
    table.addLabel("guard slit blade")
    table.addLabel("starting position")
    table.addRow(("top", original_position["top"]))
    table.addRow(("bottom", original_position["bot"]))
    table.addRow(("Outboard", original_position["out"]))
    table.addRow(("Inboard", original_position["inb"]))
    logger.info(table)

    # Now move all guard slit motors back a bit
    yield from bps.mv(
        guard_slit.top,
        original_position["top"] + v_step_into,
        guard_slit.bot,
        original_position["bot"] - v_step_into,
    )
    # do in two steps
    # -- we locked up all four motor records when we did it all at the same time
    yield from bps.mv(
        guard_slit.outb,
        original_position["out"] + h_step_into,
        guard_slit.inb,
        original_position["inb"] - h_step_into,
    )

    yield from user_data.set_state_plan("autoranging the PD")
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])

    def cleanup(msg):
        """if scan is aborted, return motors to original positions"""
        logger.warning(
            "Returning the guard slit motors to original (pre-tune) positions"
        )
        yield from bps.mv(
            guard_slit.top,
            original_position["top"],
            guard_slit.bot,
            original_position["bot"],
            guard_slit.outb,
            original_position["out"],
            guard_slit.inb,
            original_position["inb"],
        )
        raise GuardSlitTuneError(msg)

    logger.info("And now we can tune all of the guard slits, blade-by-blade")

    def tune_blade_edge(axis, start, end, steps, ct_time, results):
        logger.info(f"{axis.name}: scan from {start} to {end}")
        old_ct_time = scaler0.preset_time.get()
        old_position = axis.position

        yield from bps.mv(  # move to center of scan range for tune
            scaler0.preset_time,
            ct_time,
            axis,
            (start + end) / 2,
        )
        scan_width = end - start

        scaler0.select_channels([UPD_SIGNAL.chname.get()])
        scaler0.channels.chan01.kind = Kind.config

        tuner = TuneAxis([scaler0], axis, signal_name=UPD_SIGNAL.chname.get())
        yield from tuner.tune(width=scan_width, num=steps + 1)

        diff = abs(tuner.peaks.y_data[0] - tuner.peaks.y_data[-1])
        if diff < guard_slit.tuning_intensity_threshold:
            msg = f"{axis.name}: Not enough intensity change from first to last point."
            msg += f" {diff} < {guard_slit.tuning_intensity_threshold}."
            msg += "  Did the guard slit move far enough to move into/out of the beam?"
            msg += "  Not tuning this axis."
            yield from cleanup(msg)

        x, y = numerical_derivative(tuner.peaks.x_data, tuner.peaks.y_data)
        position, width = peak_center(x, y)
        width *= guard_slit.scale_factor  # expand a bit

        # Check if movement was from unblocked to blocked
        # not necessary and makes this code fail
        # if tuner.peaks.y_data[0] > tuner.peaks.y_data[-1]:
        #     width *= -1     # flip the sign

        if position < min(start, end):
            msg = f"{axis.name}: Computed tune position {position} < {min(start, end)}."
            msg += "  Not tuning this axis."
            yield from cleanup(msg)
        if position > max(start, end):
            msg = f"{axis.name}: Computed tune position {position} > {max(start, end)}."
            msg += "  Not tuning this axis."
            yield from cleanup(msg)

        logger.info(f"{axis.name}: will be tuned to {position}")
        logger.info(f"{axis.name}: width = {width}")

        yield from bps.mv(
            scaler0.preset_time,
            old_ct_time,
            axis,
            old_position,  # reset position for other scans
        )

        results["width"] = width
        results["position"] = position

    tunes = defaultdict(dict)
    count_time = 0.2
    num_points = 100
    logger.info("*** 1. tune top guard slits")
    yield from tune_blade_edge(
        guard_slit.top,
        original_position["top"] + v_step_away,
        original_position["top"] - v_step_into,
        num_points,
        count_time,
        tunes["top"],
    )

    logger.info("*** 2. tune bottom guard slits")
    yield from tune_blade_edge(
        guard_slit.bot,
        original_position["bot"] - v_step_away,
        original_position["bot"] + v_step_into,
        num_points,
        count_time,
        tunes["bot"],
    )

    logger.info("*** 3. tune outboard guard slits")
    yield from tune_blade_edge(
        guard_slit.outb,
        original_position["out"] + h_step_away,
        original_position["out"] - h_step_into,
        num_points,
        count_time,
        tunes["out"],
    )

    logger.info("*** 4. tune inboard guard slits")
    yield from tune_blade_edge(
        guard_slit.inb,
        original_position["inb"] - h_step_away,
        original_position["inb"] + h_step_into,
        num_points,
        count_time,
        tunes["inb"],
    )

    # Tuning is done, now move the motors to the center of the beam found
    yield from bps.mv(
        guard_slit.top,
        tunes["top"]["position"],
        guard_slit.bot,
        tunes["bot"]["position"],
        guard_slit.outb,
        tunes["out"]["position"],
        guard_slit.inb,
        tunes["inb"]["position"],
    )

    # redefine the motor positions so the centers are 0
    def redefine(axis, pos):
        """set motor record's user coordinate to `pos`"""
        yield from bps.mv(axis.set_use_switch, 1)
        yield from bps.mv(axis.user_setpoint, pos)
        yield from bps.mv(axis.set_use_switch, 0)

    yield from redefine(guard_slit.top, 0)
    yield from redefine(guard_slit.bot, 0)
    yield from redefine(guard_slit.outb, 0)
    yield from redefine(guard_slit.inb, 0)

    # center of the slits is set to 0
    # now move the motors to the width found above
    # use average of the individual blade values.
    v = (tunes["top"]["width"] + tunes["bot"]["width"]) / 2
    h = (tunes["out"]["width"] + tunes["inb"]["width"]) / 2
    yield from bps.mv(
        guard_slit.top,
        v,
        guard_slit.bot,
        -v,
        guard_slit.outb,
        h,
        guard_slit.inb,
        -h,
    )

    # sync the slits software
    yield from bps.mv(
        guard_slit.h_sync_proc,
        1,
        guard_slit.v_sync_proc,
        1,
    )
    yield from guard_slit.process_motor_records()


def _unstick_GslitsSizeMotors():
    """Workaround for issue #425 (and #404)."""
    pause = 4
    logger.info("Workaround for Guard Slit 'motor stuck in moving'.")
    yield from bps.sleep(pause)  # activity pause, empirical

    logger.info("Sync H&V axes.")
    yield from bps.mv(
        guard_slit.h_sync_proc,
        1,
        guard_slit.v_sync_proc,
        1,
    )

    # NOTE: These steps did not affect the process outcome.
    # # write the .STUP field on each motor
    # for axis in "top bot inb outb".split():
    #     logger.info("Unstick %s.", axis)
    #     m = getattr(guard_slit, axis)
    #     try:
    #         yield from bps.abs_set(m.status_update, 1, timeout=.1)
    #         yield from bps.sleep(pause)     # activity pause, empirical
    #     except FailedStatus:
    #         pass
    #     except Exception as exc:
    #         logger.error("%s: %s", axis, exc)

    # move each motor *individually*
    for axis in "top bot inb outb".split():
        m = getattr(guard_slit, axis)
        logger.info("Move %s a little bit.\n", m.name)
        yield from bps.mvr(m, 0.1)
        logger.info("Move %s back.\n", m.name)
        yield from bps.mvr(m, -0.1)

    logger.info("Workaround Complete.")


def tune_GslitsSize():
    """
    plan: optimize the guard slits' gap

    tune to the slit edges (peak of the derivative of diode vs. position)
    """
    yield from IfRequestedStopBeforeNextScan()
    yield from mode_USAXS()
    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
        monochromator.feedback.on,
        MONO_FEEDBACK_OFF,
    )
    yield from bps.mv(
        upd_controls.auto.gainU,
        terms.FlyScan.setpoint_up.get(),
        upd_controls.auto.gainD,
        terms.FlyScan.setpoint_down.get(),
        ti_filter_shutter,
        "open",
    )
    # insertCCDfilters
    yield from insertTransmissionFilters()
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])
    yield from _USAXS_tune_guardSlits()
    yield from bps.mv(
        ti_filter_shutter,
        "close",
        terms.SAXS.guard_h_size,
        guard_slit.h_size.get(),
        terms.SAXS.guard_v_size,
        guard_slit.v_size.get(),
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
    )

    # workaround for issue #425 (#404)
    yield from _unstick_GslitsSizeMotors()

    logger.info(
        f"Guard slit now: V={guard_slit.v_size.get()} and H={guard_slit.h_size.get()}"
    )


def tune_Gslits():
    """
    plan: scan and find optimal guard slit positions
    """
    yield from tune_GslitsCenter()
    yield from tune_GslitsSize()
