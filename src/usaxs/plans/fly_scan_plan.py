"""USAXS Fly Scan Plan Module.

This module implements the fly scan functionality for USAXS measurements.
During a fly scan the analyzer stage (a_stage) sweeps continuously while the
FX4 electrometers integrate, in contrast to a step scan where the stage stops
at each point.  The raw data are saved to an HDF5/NeXus file by
``SaveFlyScan`` and the Bluesky run is recorded via the SPEC file writer.

How the FX4 collects a fly scan
-------------------------------
The FX4 cannot be hardware-triggered.  Instead the quadEM driver watches the
PSO gate on digital input D1 and does the gating in software from the FX4's
own hardware timestamps, so the bin edges carry no IOC scheduling jitter.  In
``Ext. bulb`` mode with ``TriggerPolarity = Negative`` the integrating level
is LOW -- the interval *between* strobes -- and each rising edge emits one
average, appended to that channel's time series.  ``AveragingTime`` is ignored
in this mode; the gate defines the window.

Both electrometers take the same PSO train (the PRL-414B is a 1:4 driver), so
index ``i`` means the same interval on UPD and on I0 and the ratio is valid
point by point with no timing correction.  See
``docs/FX4_PSO_flyscan_setup.md``.

Sequence overview
-----------------
1. Record starting stage positions (ar, ax, dx) for later restoration.
2. Open a Bluesky run and write SPEC comments.
3. Hand usxFX4's shared Range to UPD and let the sequence program keep ranging.
4. Put both electrometers in bulb mode and arm their time series.
5. Launch a background thread to prepare the HDF5 output file.
6. Start acquisition, then trigger the hardware fly-scan via the busy record.
7. Launch a background thread to log periodic progress.
8. Set the ``flying`` software flag so the progress thread can track state.
9. Wait for the busy record to clear (scan complete).
10. Stop acquisition so the time-series arrays are stable, and check that the
    expected number of pulses arrived and that no ring buffer overflowed.
11. Launch a background thread to finalise and write the HDF5 file.
12. Restore all stage positions and close the USAXS shutter.
13. Close the Bluesky run.
"""

import datetime
import logging
import os
import time
import uuid
from collections import OrderedDict
from typing import Optional

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry
from apstools.utils import run_in_thread
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from ..devices.fx4_quadem import FX4AutorangeSettings as AutorangeSettings
from ..usaxs_flyscan_support.saveFlyData import SaveFlyScan
from .fx4_setup import check_ring_overflows
from .fx4_setup import enable_fx4_autorange
from .fx4_setup import fx4_flyscan_mode
from .fx4_setup import usaxs_electrometers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device instances retrieved from the ophyd device registry.
# These are module-level singletons used throughout the plan.
# ---------------------------------------------------------------------------
a_stage = oregistry["a_stage"]  # analyzer stage (r = rotation, x = lateral)
d_stage = oregistry["d_stage"]  # detector stage (x = lateral)
terms = oregistry["terms"]  # general run-time terms / GUI-facing PVs
flyscan_trajectories = oregistry["flyscan_trajectories"]  # PSO pulse positions
FX4_DETECTORS = usaxs_electrometers()  # [fx4 (UPD, TRD), fx42 (I0, I00)]
UPD_CHANNEL = oregistry["upd_controls"].channel_number
# Margin on TSNumPoints.  The series is "Fixed length", so it stops itself at
# this count; a few spare slots mean a trajectory that emits one extra strobe
# is recorded rather than truncated.
TS_POINTS_MARGIN = 16

# Floor on TSNumPoints.  Over-sizing a fixed-length time series costs nothing:
# it simply stops when acquisition does, and TSCurrentPoint reports how many
# pulses actually arrived.  Under-sizing silently truncates the scan.  Given
# that asymmetry -- and that `num_pulse_positions` is really NumPoints, the
# waypoint count, not the pulse count (see devices/trajectories.py) -- the size
# is floored well above the documented maximum of ~8000 pulses.
TS_POINTS_FLOOR = 8192
upd_controls = oregistry["upd_controls"]  # UPD (PIN diode) amplifier controls
usaxs_shutter = oregistry["usaxs_shutter"]  # USAXS in-vacuum shutter
user_data = oregistry["user_data"]  # run-state string PV visible in the GUI
usaxs_flyscan = oregistry["usaxs_flyscan"]  # UsaxsFlyScanDevice (busy, flying, …)


def _read_or_none(signal):
    """Return a signal's value, or None if it cannot be read.

    Progress reporting runs in a background thread while the scan is live; a
    momentary read failure there must not kill the thread.

    Parameters
    ----------
    signal : ophyd.Signal
        The signal to read.

    Returns
    -------
    object or None
    """
    try:
        return signal.get()
    except Exception as exc:  # noqa: BLE001 - a failed read is "unknown"
        logger.debug("could not read %s: %s", getattr(signal, "name", signal), exc)
        return None


def _expected_pulse_count():
    """Return how many PSO strobes this sweep should produce.

    Prefers ``NumPulses``, which is the pulse count.  Falls back to
    ``num_pulse_positions`` (really ``NumPoints``, the waypoint count) only if
    ``NumPulses`` cannot be read, and then the figure is an underestimate --
    which is why it is used for a warning threshold and never to size the time
    series.

    Returns
    -------
    int
        Expected pulse count; 0 when neither PV can be read.
    """
    pulses = _read_or_none(flyscan_trajectories.num_pulses)
    if pulses:
        return int(pulses)
    points = _read_or_none(flyscan_trajectories.num_pulse_positions)
    if points:
        logger.warning(
            "usxAERO:pm1:NumPulses unreadable; falling back to NumPoints (%s),"
            " which counts waypoints, not pulses",
            points,
        )
        return int(points)
    return 0


def _ts_current_point():
    """Return how many PSO pulses the UPD channel has captured so far.

    The replacement for the Struck's ``current_channel``.

    Returns
    -------
    int or None
    """
    stats = FX4_DETECTORS[0].channel_stats(UPD_CHANNEL)
    return _read_or_none(stats.ts_current_point)


@plan
def Flyscan_internal_plan(md: Optional[dict] = None):
    """Execute a USAXS fly scan.

    Coordinates hardware triggering, parallel HDF5 file preparation/saving,
    progress logging, and stage restoration.  Designed to be called by
    higher-level plans (e.g. ``Flyscan()``) that have already positioned the
    instrument.

    Parameters
    ----------
    md : dict, optional
        Additional metadata merged into the Bluesky run document.
        HDF5 file/path keys are added automatically.

    Yields
    ------
    Bluesky messages that the RunEngine consumes.
    """

    if md is None:
        md = {}

    # Check whether a RunEngine is actively driving this plan.
    # When RE.state is not "idle" we are inside a real scan; several
    # background-thread operations are only needed in that case.
    # bluesky_runengine_running = RE.state != "idle"

    # ------------------------------------------------------------------
    # Inner helper: build a single-line progress string
    # ------------------------------------------------------------------
    def _report_(t):
        """Return a formatted progress string for the current scan instant.

        Parameters
        ----------
        t : float
            Elapsed time in seconds since the scan started (``usaxs_flyscan.t0``).

        Returns
        -------
        str
            Columns: elapsed time | ar position | ax position | dx position
            | pulses captured | samples in the last interval.  Each column is
            11 chars wide.
        """
        # The Struck had its own elapsed-time register; the FX4 has none, so
        # the plan's own clock drives the GUI display.
        terms.FlyScan.elapsed_time.put(t)

        # TSCurrentPoint is the pulse count so far -- the direct replacement
        # for the Struck's current_channel.
        point = _ts_current_point()
        # NumAveraged is the sample count of the most recent interval.  It is
        # the live tuning-health readout: a tight spread means the AR sweep is
        # tracking, a scattered one means it is not.
        samples = _read_or_none(FX4_DETECTORS[0].num_averaged)

        values = [
            f"{t:.2f}",
        ]
        values.append(f"{a_stage.r.position:.7f}")
        values.append(f"{a_stage.x.position:.5f}")
        values.append(f"{d_stage.x.position:.5f}")
        missing = "-missing-"
        values.append(missing if point is None else f"{point}")
        values.append(missing if samples is None else f"{samples}")
        return "  ".join([f"{s:11}" for s in values])

    # ------------------------------------------------------------------
    # Background thread: log stage/channel progress while the scan runs
    # ------------------------------------------------------------------
    @run_in_thread
    def progress_reporting():
        """Periodically log scan progress until the fly scan finishes.

        Runs in a background thread (via ``@run_in_thread``) so it does not
        block the Bluesky RunEngine event loop.

        Uses ``usaxs_flyscan.flying`` as the loop sentinel; stops when that
        signal goes False or when the timeout is exceeded.
        """
        t = time.time()
        # Re-anchor the clock to *this* attempt.  After a suspender resume the
        # RunEngine replays the progress_kick write, so this runs again for the
        # restarted sweep; leaving the original t0 in place would report elapsed
        # times that include the beam outage and would expire the deadline below
        # partway through the new sweep.
        usaxs_flyscan.t0 = t
        usaxs_flyscan.update_time = t + usaxs_flyscan.update_interval_s
        # Total allowed wall time = scan duration + padding.
        timeout = (
            t + usaxs_flyscan.scan_time.get() + usaxs_flyscan.timeout_s
        )  # extra padded time
        # Brief startup window: give the plan time to set flying=True before
        # the main polling loop checks it.
        startup = t + usaxs_flyscan.update_interval_s / 2
        while (
            t < startup and not usaxs_flyscan.flying.get()
        ):  # wait for flyscan to start
            time.sleep(0.01)
        labels = (
            "flying, s",
            "ar, deg",
            "ax, mm",
            "dx, mm",
            "pulses",
            "samples",
        )
        logger.info("  ".join([f"{s:11}" for s in labels]))
        # Main loop: log a progress line every ``update_interval_s`` seconds.
        while t < timeout and usaxs_flyscan.flying.get():
            if t > usaxs_flyscan.update_time:
                usaxs_flyscan.update_time = t + usaxs_flyscan.update_interval_s
                msg = _report_(t - usaxs_flyscan.t0)
                logger.info(msg)
            time.sleep(0.01)
            t = time.time()
        # Log one final line after the loop exits.
        msg = _report_(time.time() - usaxs_flyscan.t0)
        logger.info(msg)
        if t > timeout:
            logger.error(
                f"{time.time()-usaxs_flyscan.t0}s - progress_reporting timeout!!"
            )
        else:
            logger.debug(
                f"{time.time()-usaxs_flyscan.t0}s - progress_reporting is done"
            )

    # ------------------------------------------------------------------
    # Background thread: create the HDF5 file and write preliminary data
    # ------------------------------------------------------------------
    @run_in_thread
    def prepare_HDF5_file():
        """Create the output HDF5 file and write the preliminary (header) data.

        Runs in a background thread so it overlaps with the hardware scan
        startup, minimising dead time.

        The target directory comes from ``usaxs_flyscan.saveFlyData_HDF5_dir``.
        If that directory does not exist the fallback directory is used instead.
        If the target file already exists a timestamp-based name is substituted.

        Side effects
        ------------
        Sets ``usaxs_flyscan._output_HDF5_file_`` to the resolved file path.
        Sets ``usaxs_flyscan.saveFlyData`` to the active ``SaveFlyScan`` instance.
        Updates ``user_data`` state string visible in the GUI.
        """
        fname = os.path.abspath(usaxs_flyscan.saveFlyData_HDF5_dir)
        # If the configured save directory does not exist, fall back gracefully.
        if not os.path.exists(fname):
            msg = f"Must save fly scan data to an existing directory.  Gave {fname}"
            fname = os.path.abspath(usaxs_flyscan.fallback_dir)
            msg += f"  Using fallback directory {usaxs_flyscan.fallback_dir}"
            logger.error(msg)

        s = (
            usaxs_flyscan.saveFlyData_HDF5_file
        )  # configured base filename, e.g. "sfs.h5"
        _s_ = os.path.join(fname, s)  # for testing here
        # If the file already exists, generate a unique name from the current timestamp.
        if os.path.exists(_s_):
            msg = f"File {_s_} exists.  Will not overwrite."
            s = datetime.datetime.isoformat(datetime.datetime.now(), sep="_").split(
                "."
            )[0]
            s = s.replace(":", "").replace("-", "")
            s = "flyscan_" + s + ".h5"
            _s_ = os.path.join(fname, s)
            msg += f"  Using fallback file name {_s_}"
            logger.error(msg)
        fname = os.path.join(fname, s)  # resolved final output path

        logger.debug(f"HDF5 config: {usaxs_flyscan.saveFlyData_config}")
        logger.info(f"HDF5 file : {fname}")
        usaxs_flyscan._output_HDF5_file_ = fname
        user_data.set_state_blocking("FlyScanning: " + os.path.split(fname)[-1])

        # Create the SaveFlyScan writer and write the NeXus skeleton immediately
        # so the file exists on disk before the scan finishes.
        usaxs_flyscan.saveFlyData = SaveFlyScan(
            fname, config_file=usaxs_flyscan.saveFlyData_config
        )
        usaxs_flyscan.saveFlyData.preliminaryWriteFile()

    # ------------------------------------------------------------------
    # Background thread: flush EPICS data into the HDF5 file after the scan
    # ------------------------------------------------------------------
    @run_in_thread
    def finish_HDF5_file():
        """Read EPICS PV arrays and write the final fly-scan data to HDF5.

        Must be called after ``prepare_HDF5_file()`` has completed and after
        the hardware scan has finished so the Struck arrays are fully populated.
        Clears ``usaxs_flyscan.saveFlyData`` when done.

        Raises
        ------
        RuntimeError
            If called before ``prepare_HDF5_file()`` (i.e. ``saveFlyData`` is None).
        """
        # prepare_HDF5_file() runs concurrently; wait for it to set saveFlyData.
        t_end = time.time() + 60  # 60-second timeout
        while usaxs_flyscan.saveFlyData is None and time.time() < t_end:
            time.sleep(0.05)
        if usaxs_flyscan.saveFlyData is None:
            raise RuntimeError("prepare_HDF5_file() did not complete in time")
        usaxs_flyscan.saveFlyData.saveFile()

        logger.info(f"HDF5 file complete: {usaxs_flyscan._output_HDF5_file_}")
        usaxs_flyscan.saveFlyData = None  # release the writer object

    ######################################################################
    # plan starts here

    # ------------------------------------------------------------------
    # Save starting stage positions so they can be restored after the scan.
    # Note: the device __init__ pre-declares ay0/dy0 but this plan uses
    # ax0/dx0 (Python allows dynamic attribute creation on ophyd Device
    # instances, so this works, but ax0/dx0 are undeclared in __init__).
    # ------------------------------------------------------------------
    usaxs_flyscan.ar0 = a_stage.r.position  # analyzer rotation angle, degrees
    usaxs_flyscan.ax0 = a_stage.x.position  # analyzer lateral position, mm
    usaxs_flyscan.dx0 = d_stage.x.position  # detector lateral position, mm

    # Merge HDF5 file info into the run metadata so it appears in the run document.
    _md = md or OrderedDict()
    _md["hdf5_file"] = usaxs_flyscan.saveFlyData_HDF5_file
    _md["hdf5_path"] = usaxs_flyscan.saveFlyData_HDF5_dir

    yield from bps.open_run(md=_md)

    # Suspender rewind boundary.  On resume the RunEngine replays every message
    # cached since the last checkpoint (run_engine.py: _rewind), so without this
    # a beam-loss suspension would replay the whole Flyscan setup -- mode_USAXS,
    # filters, stage moves and the Blackfly optical image.  That replay runs as a
    # flat Msg list outside the original generator frames, so the try/except in
    # record_sample_image_on_demand cannot catch a camera hiccup and it kills the
    # command list instead of logging a warning.
    # Placed *after* open_run so the replay never re-issues open_run (which would
    # raise IllegalMessageSequence).  The cached set is then just "arm the busy
    # record", so resuming re-triggers the AR sweep from the start and the scan
    # is redone in full rather than left with a dead segment.
    yield from bps.checkpoint()

    # specwriter._cmt("start USAXS Fly scan")
    # Hand usxFX4's shared Range to UPD and let the sequence program keep
    # ranging through the sweep -- the signal falls many decades from the
    # rocking-curve peak to high q.  Through enable_fx4_autorange because the
    # transmission measurement just before this leaves the channel on TRD.
    yield from enable_fx4_autorange(upd_controls, AutorangeSettings.auto_background)

    # Put both electrometers in PSO-gated mode and arm their time series.  Both
    # take the same PSO train, so index i means the same interval on each.
    expected_pulses = _expected_pulse_count()
    ts_points = max(expected_pulses + TS_POINTS_MARGIN, TS_POINTS_FLOOR)
    for det in FX4_DETECTORS:
        yield from fx4_flyscan_mode(det, ts_points)

    # Record the wall-clock start time and calculate the next progress log time.
    usaxs_flyscan.t0 = time.time()
    usaxs_flyscan.update_time = usaxs_flyscan.t0 + usaxs_flyscan.update_interval_s
    # Guard against a leftover True state from a previous aborted scan.
    if usaxs_flyscan.flying.get():
        logger.warning("Was flying. Setting that signal to False now.")
        yield from bps.abs_set(usaxs_flyscan.flying, False)

    # if bluesky_runengine_running:
        # prepare HDF5 file to save fly scan data (background thread)
        # Runs concurrently with the scan startup sequence to minimise dead time.
    prepare_HDF5_file()
    # specwriter._cmt(f"HDF5 configuration file: {usaxs_flyscan.saveFlyData_config}")

    # ------------------------------------------------------------------
    # Trigger the hardware fly scan via the EPICS busy record.
    # Writing the "busy" enum value to the PV tells the IOC to start the
    # trajectory and collect data.  The group ``g`` lets bps.wait() block
    # until the busy record returns to "done".
    # ------------------------------------------------------------------
    # Start the electrometers BEFORE the trajectory: the driver only sees gate
    # edges while it is acquiring, so any strobe that arrives first is lost.
    for det in FX4_DETECTORS:
        yield from bps.mv(det.acquire, 1)

    g = uuid.uuid4()
    yield from bps.abs_set(
        usaxs_flyscan.busy,
        usaxs_flyscan.busy.enum_strs[1],  # BusyStatus.busy,
        group=g,  # waits until done
        timeout=usaxs_flyscan.scan_time.get() + usaxs_flyscan.timeout_s,
    )

    # Start logging scan progress in a background thread, before flying=True is
    # set, because progress_reporting() has its own brief startup-wait loop.
    #
    # Driven through a signal write rather than a bare call so it survives a
    # suspender resume: the RunEngine replays cached Msg objects, not the Python
    # between them, so a bare call would leave a restarted sweep unmonitored and
    # the stale thread would expire mid-scan.  The handler is re-assigned each
    # time (it closes over this plan's _report_), and the replayed write finds it
    # still in place.
    usaxs_flyscan.progress_kick.handler = progress_reporting
    yield from bps.abs_set(usaxs_flyscan.progress_kick, 1)

    # ------------------------------------------------------------------
    # Set the software ``flying`` flag that the progress thread polls.
    # First resolve any lingering unfinished Status object from a previous
    # scan (issue #499) to avoid blocking the new set() call.
    # ------------------------------------------------------------------
    if (
        usaxs_flyscan.flying._status is not None
        and not usaxs_flyscan.flying._status.done
    ):
        # per https://github.com/APS-USAXS/ipython-usaxs/issues/499
        logger.warning("Clearing unfinished status object on 'usaxs_flyscan/flying'")
        usaxs_flyscan.flying._status.set_finished()
    if not usaxs_flyscan.flying.get():
        yield from bps.abs_set(usaxs_flyscan.flying, True)
    else:
        logger.warning("Already flying, should not be flying now.")

    # Block here until the busy record signals that the hardware scan is done.
    yield from bps.wait(group=g)
    # Clear the flying flag so the progress thread exits its polling loop.
    yield from bps.abs_set(usaxs_flyscan.flying, False)

    # Stop the electrometers before anything reads the arrays.  saveFlyData
    # harvests them from a background thread, and a series still acquiring
    # could grow underneath it.
    for det in FX4_DETECTORS:
        yield from bps.mv(det.acquire, 0)

    # Did every PSO pulse register?  Too few can mean the link dropped samples
    # (raise ValuesPerRead) or that neighbouring exposures merged because the
    # strobe was too narrow for the sample cadence (lower it).  The two look
    # identical in this count but differ in NumAveraged, which the progress log
    # has been printing all along: merged intervals show roughly double.
    captured = _ts_current_point()
    if captured is not None and expected_pulses and captured < expected_pulses:
        logger.warning(
            "Flyscan captured %d of %d PSO pulses (%d missing). Check the"
            " ValuesPerRead / strobe-width window -- see PLAN.md section 5.2.",
            captured,
            expected_pulses,
            expected_pulses - captured,
        )
    else:
        logger.info("Flyscan captured %s PSO pulses", captured)
    # A ring-buffer overflow biases every mean toward the end of its interval
    # and is invisible in the data itself.
    yield from check_ring_overflows(FX4_DETECTORS, "flyscan")
    # elapsed = time.time() - usaxs_flyscan.t0
    # specwriter._cmt(f"fly scan completed in {elapsed} s")

    # if bluesky_runengine_running:
    msg = f"writing fly scan HDF5 file: {usaxs_flyscan._output_HDF5_file_}"
    logger.debug(msg)
    try:
        yield from user_data.set_state_plan("writing fly scan HDF5 file")
    except Exception as exc:
        # do not fail the scan just because of updating program state
        logger.warning("Non-fatal error while %s\n%s\nPlan continues", msg, exc)
        # FIXME: hack to avoid `Another set() call is still in progress`
        # see: https://github.com/APS-USAXS/ipython-usaxs/issues/417
        user_data.state._set_thread = None
    # Finalise the HDF5 file in a background thread so the plan can
    # simultaneously restore stages (the next bps.mv call).
    finish_HDF5_file()  # finish saving data to HDF5 file (background thread)
    # specwriter._cmt(f"finished {msg}")
    logger.debug(f"finished {msg}")

    # ------------------------------------------------------------------
    # Restore all stages to their pre-scan positions, reset amplifier mode,
    # and close the USAXS in-vacuum shutter.
    # bps.mv() moves all signals concurrently (paired device/value args).
    # ------------------------------------------------------------------
    yield from bps.mv(
        # fmt: off
        a_stage.r.user_setpoint,
        usaxs_flyscan.ar0,
        a_stage.x.user_setpoint,
        usaxs_flyscan.ax0,
        d_stage.x.user_setpoint,
        usaxs_flyscan.dx0,
        usaxs_shutter,
        "close",
        # fmt: on
    )
    yield from enable_fx4_autorange(upd_controls, AutorangeSettings.auto_background)

    logger.debug(f"after return: {time.time() - usaxs_flyscan.t0}s")

    yield from user_data.set_state_plan("fly scan finished")
    yield from bps.close_run()
