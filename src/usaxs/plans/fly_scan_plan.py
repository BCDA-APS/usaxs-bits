"""USAXS Fly Scan Plan Module.

This module implements the fly scan functionality for USAXS measurements.
During a fly scan the analyzer stage (a_stage) sweeps continuously while the
Struck multi-channel scaler collects counts, in contrast to a step scan where
the stage stops at each point.  The raw data are saved to an HDF5/NeXus file
by ``SaveFlyScan`` and the Bluesky run is recorded via the SPEC file writer.

Sequence overview
-----------------
1. Record starting stage positions (ar, ax, dx) for later restoration.
2. Open a Bluesky run and write SPEC comments.
3. Switch the UPD amplifier to auto-background mode.
4. Launch a background thread to prepare the HDF5 output file.
5. Trigger the hardware fly-scan via the EPICS busy record.
6. Launch a background thread to log periodic progress.
7. Set the ``flying`` software flag so the progress thread can track state.
8. Wait for the busy record to clear (scan complete).
9. Clear the ``flying`` flag; record elapsed time.
10. Launch a background thread to finalise and write the HDF5 file.
11. Restore all stage positions and close the USAXS shutter.
12. Close the Bluesky run.
"""

import datetime
import logging
import os
import time
import uuid
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry
from apstools.utils import run_in_thread
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from usaxs.callbacks.demo_spec_callback import specwriter

from ..devices.amplifiers import AutorangeSettings
from ..startup import RE
from ..usaxs_flyscan_support.saveFlyData import SaveFlyScan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device instances retrieved from the ophyd device registry.
# These are module-level singletons used throughout the plan.
# ---------------------------------------------------------------------------
a_stage = oregistry["a_stage"]          # analyzer stage (r = rotation, x = lateral)
d_stage = oregistry["d_stage"]          # detector stage (x = lateral)
struck = oregistry["struck"]            # Struck multi-channel scaler (MCS)
terms = oregistry["terms"]              # general run-time terms / GUI-facing PVs
upd_controls = oregistry["upd_controls"]  # UPD (PIN diode) amplifier controls
usaxs_shutter = oregistry["usaxs_shutter"]  # USAXS in-vacuum shutter
user_data = oregistry["user_data"]      # run-state string PV visible in the GUI
usaxs_flyscan = oregistry["usaxs_flyscan"]  # UsaxsFlyScanDevice (busy, flying, …)


@plan
def Flyscan_internal_plan(md: Optional[Dict[str, Any]] = None):
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
    bluesky_runengine_running = RE.state != "idle"

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
            | struck channel | struck elapsed time.  Each column is 11 chars wide.
        """
        # Read instantaneous elapsed time from the Struck hardware register.
        elapsed = struck.elapsed_real_time.get()
        channel = None
        if elapsed is not None:
            channel = struck.current_channel.get()
            # If the Struck timer shows more time than our scan time, it must
            # be left over from the *previous* fly scan — reset the display.
            if elapsed > t:  # looking at previous fly scan
                elapsed = 0
                channel = 0
            terms.FlyScan.elapsed_time.put(elapsed)  # for our GUI display

        # Build the list of formatted column values.
        values = [
            f"{t:.2f}",
        ]
        values.append(f"{a_stage.r.position:.7f}")
        values.append(f"{a_stage.x.position:.5f}")
        values.append(f"{d_stage.x.position:.5f}")
        missing = "-missing-"
        if channel is None:
            values.append(missing)
        else:
            values.append(f"{channel}")
        if elapsed is None:
            values.append(missing)
        else:
            values.append(f"{elapsed:.2f}")
        # values.append(resource_usage())
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
        # logger.debug("progress_reporting has arrived")
        t = time.time()
        # Total allowed wall time = scan duration + generous padding.
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
            "channel",
            "elapsed, s",
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
        # user_data.set_state_blocking(msg.split()[0])
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

        s = usaxs_flyscan.saveFlyData_HDF5_file  # configured base filename, e.g. "sfs.h5"
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

        # logger.debug(resource_usage("before SaveFlyScan()"))
        # Create the SaveFlyScan writer and write the NeXus skeleton immediately
        # so the file exists on disk before the scan finishes.
        usaxs_flyscan.saveFlyData = SaveFlyScan(
            fname, config_file=usaxs_flyscan.saveFlyData_config
        )
        # logger.debug(resource_usage("before saveFlyData.preliminaryWriteFile()"))
        usaxs_flyscan.saveFlyData.preliminaryWriteFile()
        # logger.debug(resource_usage("after saveFlyData.preliminaryWriteFile()"))

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
        if usaxs_flyscan.saveFlyData is None:
            raise RuntimeError("Must first call prepare_HDF5_file()")
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
    usaxs_flyscan.ar0 = a_stage.r.position   # analyzer rotation angle, degrees
    usaxs_flyscan.ax0 = a_stage.x.position   # analyzer lateral position, mm
    usaxs_flyscan.dx0 = d_stage.x.position   # detector lateral position, mm

    # Merge HDF5 file info into the run metadata so it appears in the run document.
    _md = md or OrderedDict()
    _md["hdf5_file"] = usaxs_flyscan.saveFlyData_HDF5_file
    _md["hdf5_path"] = usaxs_flyscan.saveFlyData_HDF5_dir

    yield from bps.open_run(md=_md)
    # specwriter._cmt("start", "start USAXS Fly scan")   # old two-arg API
    specwriter._cmt("start USAXS Fly scan")
    # Switch UPD amplifier to auto-background mode for the scan.
    yield from bps.mv(
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
    )

    # Record the wall-clock start time and calculate the next progress log time.
    usaxs_flyscan.t0 = time.time()
    usaxs_flyscan.update_time = usaxs_flyscan.t0 + usaxs_flyscan.update_interval_s
    # Guard against a leftover True state from a previous aborted scan.
    if usaxs_flyscan.flying.get():
        logger.warning("Was flying. Setting that signal to False now.")
        yield from bps.abs_set(usaxs_flyscan.flying, False)

    if bluesky_runengine_running:
        # prepare HDF5 file to save fly scan data (background thread)
        # Runs concurrently with the scan startup sequence to minimise dead time.
        prepare_HDF5_file()
    # path = os.path.abspath(usaxs_flyscan.saveFlyData_HDF5_dir)
    # specwriter._cmt("start", f"HDF5 configuration file: {
    # usaxs_flyscan.saveFlyData_config}")   # old two-arg API
    specwriter._cmt(f"HDF5 configuration file: {usaxs_flyscan.saveFlyData_config}")

    # ------------------------------------------------------------------
    # Trigger the hardware fly scan via the EPICS busy record.
    # Writing the "busy" enum value to the PV tells the IOC to start the
    # trajectory and collect data.  The group ``g`` lets bps.wait() block
    # until the busy record returns to "done".
    # ------------------------------------------------------------------
    g = uuid.uuid4()
    yield from bps.abs_set(
        usaxs_flyscan.busy,
        usaxs_flyscan.busy.enum_strs[1],  # BusyStatus.busy,
        group=g,  # waits until done
        timeout=usaxs_flyscan.scan_time.get() + usaxs_flyscan.timeout_s,
    )

    if bluesky_runengine_running:
        # Start logging scan progress in a background thread.
        # This is launched here, before flying=True is set, because
        # progress_reporting() has its own brief startup-wait loop.
        progress_reporting()

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
    elapsed = time.time() - usaxs_flyscan.t0
    # specwriter._cmt("stop", f"fly scan completed in {elapsed} s")   # old two-arg API
    specwriter._cmt(f"fly scan completed in {elapsed} s")

    if bluesky_runengine_running:
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
        # logger.debug(resource_usage("before saveFlyData.finish_HDF5_file()"))
        # Finalise the HDF5 file in a background thread so the plan can
        # simultaneously restore stages (the next bps.mv call).
        finish_HDF5_file()  # finish saving data to HDF5 file (background thread)
        # logger.debug(resource_usage("after saveFlyData.finish_HDF5_file()"))
        # specwriter._cmt("stop", f"finished {msg}")   # old two-arg API
        specwriter._cmt(f"finished {msg}")
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
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
        usaxs_shutter,
        "close",
        # fmt: on
    )

    #yield from write_stream([struck.mca1, struck.mca2, struck.mca3], "mca")
    logger.debug(f"after return: {time.time() - usaxs_flyscan.t0}s")

    yield from user_data.set_state_plan("fly scan finished")
    yield from bps.close_run()
