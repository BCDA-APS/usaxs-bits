"""USAXS Fly Scan Plan Module.

This module implements the fly scan functionality for USAXS measurements.
It handles the coordination of stage movements, data acquisition, and
data saving during fly scans.
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
from apstools.plans import write_stream
from apstools.utils import run_in_thread
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from usaxs.callbacks.demo_spec_callback import specwriter

from ..devices.amplifiers import AutorangeSettings
from ..startup import RE
from ..usaxs_flyscan_support.saveFlyData import SaveFlyScan

logger = logging.getLogger(__name__)

# Device instances
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
struck = oregistry["struck"]
terms = oregistry["terms"]
upd_controls = oregistry["upd_controls"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]
usaxs_flyscan = oregistry["usaxs_flyscan"]


@plan
def Flyscan_internal_plan(
    md: Optional[Dict[str, Any]] = None,
):
    """
    Execute a USAXS fly scan.

    This function coordinates the execution of a USAXS fly scan, including:
    - Setting up the HDF5 file for data storage
    - Managing the fly scan state
    - Reporting progress
    - Handling data acquisition

    Args:
        md (dict, optional): Metadata to be associated with the scan.
            Defaults to None.
        RE (Any, optional): The RunEngine instance to use for the scan.
            Defaults to None.
        bec (Any, optional): The Bluesky Live Callbacks instance.
            Defaults to None.
        specwriter (Any, optional): The SPEC file writer instance.
            Defaults to None.

    Yields:
        Generator: Control flow for the fly scan execution
    """
    if md is None:
        md = {}

    bluesky_runengine_running = RE.state != "idle"

    def _report_(t):
        elapsed = struck.elapsed_real_time.get()
        channel = None
        if elapsed is not None:
            channel = struck.current_channel.get()
            if elapsed > t:  # looking at previous fly scan
                elapsed = 0
                channel = 0
            terms.FlyScan.elapsed_time.put(elapsed)  # for our GUI display

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

    @run_in_thread
    def progress_reporting():
        # logger.debug("progress_reporting has arrived")
        t = time.time()
        timeout = (
            t + usaxs_flyscan.scan_time.get() + usaxs_flyscan.timeout_s
        )  # extra padded time
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
        while t < timeout and usaxs_flyscan.flying.get():
            if t > usaxs_flyscan.update_time:
                usaxs_flyscan.update_time = t + usaxs_flyscan.update_interval_s
                msg = _report_(t - usaxs_flyscan.t0)
                logger.info(msg)
            time.sleep(0.01)
            t = time.time()
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

    @run_in_thread
    def prepare_HDF5_file():
        fname = os.path.abspath(usaxs_flyscan.saveFlyData_HDF5_dir)
        if not os.path.exists(fname):
            msg = f"Must save fly scan data to an existing directory.  Gave {fname}"
            fname = os.path.abspath(usaxs_flyscan.fallback_dir)
            msg += f"  Using fallback directory {usaxs_flyscan.fallback_dir}"
            logger.error(msg)

        s = usaxs_flyscan.saveFlyData_HDF5_file
        _s_ = os.path.join(fname, s)  # for testing here
        if os.path.exists(_s_):
            msg = f"File {_s_} exists.  Will not overwrite."
            s = datetime.datetime.isoformat(datetime.datetime.now(), sep="_").split(
                "."
            )[0]
            s = s.replace(":", "").replace("-", "")
            # s = "flyscan_" + s + ".h5"
            _s_ = os.path.join(fname, s)
            msg += f"  Using fallback file name {_s_}"
            logger.error(msg)
        fname = os.path.join(fname, s)

        logger.debug(f"HDF5 config: {usaxs_flyscan.saveFlyData_config}")
        logger.info(f"HDF5 file : {fname}")
        usaxs_flyscan._output_HDF5_file_ = fname
        user_data.set_state_blocking("FlyScanning: " + os.path.split(fname)[-1])

        # logger.debug(resource_usage("before SaveFlyScan()"))
        usaxs_flyscan.saveFlyData = SaveFlyScan(
            fname, config_file=usaxs_flyscan.saveFlyData_config
        )
        # logger.debug(resource_usage("before saveFlyData.preliminaryWriteFile()"))
        usaxs_flyscan.saveFlyData.preliminaryWriteFile()
        # logger.debug(resource_usage("after saveFlyData.preliminaryWriteFile()"))

    @run_in_thread
    def finish_HDF5_file():
        if usaxs_flyscan.saveFlyData is None:
            raise RuntimeError("Must first call prepare_HDF5_file()")
        usaxs_flyscan.saveFlyData.saveFile()

        logger.info(f"HDF5 file complete: {usaxs_flyscan._output_HDF5_file_}")
        usaxs_flyscan.saveFlyData = None

    ######################################################################
    # plan starts here

    # remember our starting conditions
    usaxs_flyscan.ar0 = a_stage.r.position
    usaxs_flyscan.ax0 = a_stage.x.position
    usaxs_flyscan.dx0 = d_stage.x.position

    _md = md or OrderedDict()
    _md["hdf5_file"] = usaxs_flyscan.saveFlyData_HDF5_file
    _md["hdf5_path"] = usaxs_flyscan.saveFlyData_HDF5_dir

    yield from bps.open_run(md=_md)
    # specwriter._cmt("start", "start USAXS Fly scan")
    specwriter._cmt("start USAXS Fly scan")
    yield from bps.mv(
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
    )

    usaxs_flyscan.t0 = time.time()
    usaxs_flyscan.update_time = usaxs_flyscan.t0 + usaxs_flyscan.update_interval_s
    if usaxs_flyscan.flying.get():
        logger.warning("Was flying. Setting that signal to False now.")
        yield from bps.abs_set(usaxs_flyscan.flying, False)

    if bluesky_runengine_running:
        # prepare HDF5 file to save fly scan data (background thread)
        prepare_HDF5_file()
    # path = os.path.abspath(usaxs_flyscan.saveFlyData_HDF5_dir)
    # specwriter._cmt("start", f"HDF5 configuration file: {
    # usaxs_flyscan.saveFlyData_config}")
    specwriter._cmt(f"HDF5 configuration file: {usaxs_flyscan.saveFlyData_config}")

    g = uuid.uuid4()
    yield from bps.abs_set(
        usaxs_flyscan.busy,
        usaxs_flyscan.busy.enum_strs[1],  # BusyStatus.busy,
        group=g,  # waits until done
        timeout=usaxs_flyscan.scan_time.get() + usaxs_flyscan.timeout_s,
    )

    if bluesky_runengine_running:
        progress_reporting()

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

    yield from bps.wait(group=g)
    yield from bps.abs_set(usaxs_flyscan.flying, False)
    elapsed = time.time() - usaxs_flyscan.t0
    # specwriter._cmt("stop", f"fly scan completed in {elapsed} s")
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
        finish_HDF5_file()  # finish saving data to HDF5 file (background thread)
        # logger.debug(resource_usage("after saveFlyData.finish_HDF5_file()"))
        # specwriter._cmt("stop", f"finished {msg}")
        specwriter._cmt(f"finished {msg}")
        logger.debug(f"finished {msg}")

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
