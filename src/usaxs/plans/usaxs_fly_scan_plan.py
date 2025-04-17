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
from typing import Generator
from typing import Optional

# Get devices from oregistry
from apsbits.utils.controls_setup import oregistry
from apstools.plans import write_stream
from apstools.utils import run_in_thread
from bluesky import plan_stubs as bps

from ..devices.amplifiers import AutorangeSettings
from ..devices.amplifiers import upd_controls
from ..devices.general_terms import terms
from ..devices.shutters import ti_filter_shutter
from ..devices.stages import a_stage
from ..devices.stages import d_stage
from ..devices.struck3820 import struck
from ..devices.user_data import user_data
from ..usaxs_support.saveFlyData import SaveFlyScan

logger = logging.getLogger(__name__)

# Device instances
upd_controls = oregistry["upd_controls"]
terms = oregistry["terms"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
struck = oregistry["struck"]
user_data = oregistry["user_data"]


def plan(
    self,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, None]:
    """Execute a USAXS fly scan.

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
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

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
        timeout = t + self.scan_time.get() + self.timeout_s  # extra padded time
        startup = t + self.update_interval_s / 2
        while t < startup and not self.flying.get():  # wait for flyscan to start
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
        while t < timeout and self.flying.get():
            if t > self.update_time:
                self.update_time = t + self.update_interval_s
                msg = _report_(t - self.t0)
                logger.debug(msg)
            time.sleep(0.01)
            t = time.time()
        msg = _report_(time.time() - self.t0)
        logger.info(msg)
        # user_data.set_state_blocking(msg.split()[0])
        if t > timeout:
            logger.error(f"{time.time()-self.t0}s - progress_reporting timeout!!")
        else:
            logger.debug(f"{time.time()-self.t0}s - progress_reporting is done")

    @run_in_thread
    def prepare_HDF5_file():
        fname = os.path.abspath(self.saveFlyData_HDF5_dir)
        if not os.path.exists(fname):
            msg = f"Must save fly scan data to an existing directory.  Gave {fname}"
            fname = os.path.abspath(self.fallback_dir)
            msg += f"  Using fallback directory {self.fallback_dir}"
            logger.error(msg)

        s = self.saveFlyData_HDF5_file
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

        logger.info(f"HDF5 config: {self.saveFlyData_config}")
        logger.info(f"HDF5 output: {fname}")
        self._output_HDF5_file_ = fname
        user_data.set_state_blocking("FlyScanning: " + os.path.split(fname)[-1])

        # logger.debug(resource_usage("before SaveFlyScan()"))
        self.saveFlyData = SaveFlyScan(fname, config_file=self.saveFlyData_config)
        # logger.debug(resource_usage("before saveFlyData.preliminaryWriteFile()"))
        self.saveFlyData.preliminaryWriteFile()
        # logger.debug(resource_usage("after saveFlyData.preliminaryWriteFile()"))

    @run_in_thread
    def finish_HDF5_file():
        if self.saveFlyData is None:
            raise RuntimeError("Must first call prepare_HDF5_file()")
        self.saveFlyData.saveFile()

        logger.info(f"HDF5 output complete: {self._output_HDF5_file_}")
        self.saveFlyData = None

    ######################################################################
    # plan starts here

    # remember our starting conditions
    self.ar0 = a_stage.r.position
    self.ax0 = a_stage.x.position
    self.dx0 = d_stage.x.position

    _md = md or OrderedDict()
    _md["hdf5_file"] = self.saveFlyData_HDF5_file
    _md["hdf5_path"] = self.saveFlyData_HDF5_dir

    yield from bps.open_run(md=_md)
    specwriter._cmt("start", "start USAXS Fly scan")
    yield from bps.mv(
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
    )

    self.t0 = time.time()
    self.update_time = self.t0 + self.update_interval_s
    if self.flying.get():
        logger.warning("Was flying.  Setting that signal to False now.")
        yield from bps.abs_set(self.flying, False)

    if bluesky_runengine_running:
        # prepare HDF5 file to save fly scan data (background thread)
        prepare_HDF5_file()
    # path = os.path.abspath(self.saveFlyData_HDF5_dir)
    specwriter._cmt("start", f"HDF5 configuration file: {self.saveFlyData_config}")

    g = uuid.uuid4()
    yield from bps.abs_set(
        self.busy,
        self.busy.enum_strs[1],  # BusyStatus.busy,
        group=g,  # waits until done
        timeout=self.scan_time.get() + self.timeout_s,
    )

    if bluesky_runengine_running:
        progress_reporting()

    if self.flying._status is not None and not self.flying._status.done:
        # per https://github.com/APS-USAXS/ipython-usaxs/issues/499
        logger.warning("Clearing unfinished status object on 'usaxs_flyscan/flying'")
        self.flying._status.set_finished()
    if not self.flying.get():
        yield from bps.abs_set(self.flying, True)
    else:
        logger.warning("Already flying, should not be flying now.")

    yield from bps.wait(group=g)
    yield from bps.abs_set(self.flying, False)
    elapsed = time.time() - self.t0
    specwriter._cmt("stop", f"fly scan completed in {elapsed} s")

    if bluesky_runengine_running:
        msg = f"writing fly scan HDF5 file: {self._output_HDF5_file_}"
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
        specwriter._cmt("stop", f"finished {msg}")
        logger.info(f"finished {msg}")

    yield from bps.mv(
        a_stage.r.user_setpoint,
        self.ar0,
        a_stage.x.user_setpoint,
        self.ax0,
        d_stage.x.user_setpoint,
        self.dx0,
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
        ti_filter_shutter,
        "close",
    )

    yield from write_stream([struck.mca1, struck.mca2, struck.mca3], "mca")
    logger.debug(f"after return: {time.time() - self.t0}s")

    yield from user_data.set_state_plan("fly scan finished")
    yield from bps.close_run()
