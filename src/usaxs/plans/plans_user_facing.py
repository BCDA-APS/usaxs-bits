"""
user-facing scans
"""

import datetime
import logging
import os
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apstools.plans import restorable_stage_sigs
from apstools.utils import cleanupText
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import plan

# from ..startup import bec
from usaxs.callbacks.spec_data_file_writer import specwriter

from ..startup import RE
from ..startup import suspend_BeamInHutch
from ..startup import suspend_FE_shutter
from ..utils.constants import constants
from ..utils.override import user_override
from ..utils.user_sample_title import getSampleTitle
from ..utils.utils import techniqueSubdirectory
from .amplifiers_plan import autoscale_amplifiers
from .area_detector_plans import areaDetectorAcquire
from .command_list import after_plan
from .command_list import before_plan
from .filter_plans import insertSaxsFilters
from .filter_plans import insertWaxsFilters
from .mode_changes import mode_SAXS
from .mode_changes import mode_WAXS
from .mono_feedback import MONO_FEEDBACK_OFF
from .mono_feedback import MONO_FEEDBACK_ON
from .requested_stop import IfRequestedStopBeforeNextScan
from .sample_imaging import record_sample_image_on_demand
from .sample_transmission import measure_SAXS_Transmission

logger = logging.getLogger(__name__)

MASTER_TIMEOUT = 60
a_stage = oregistry["a_stage"]
ar_start = oregistry["ar_start"]
d_stage = oregistry["d_stage"]
flyscan_trajectories = oregistry["flyscan_trajectories"]
guard_slit = oregistry["guard_slit"]
guard_slit = oregistry["guard_slit"]
I0_controls = oregistry["I0_controls"]
lax_autosave = oregistry["lax_autosave"]
m_stage = oregistry["m_stage"]
mono_shutter = oregistry["mono_shutter"]
mono_shutter = oregistry["mono_shutter"]
monochromator = oregistry["monochromator"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
saxs_det = oregistry["saxs_det"]
saxs_stage = oregistry["saxs_stage"]
scaler0 = oregistry["scaler0"]
scaler1 = oregistry["scaler1"]
struck = oregistry["struck"]
terms = oregistry["terms"]
trd_controls = oregistry["trd_controls"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_data"]
waxs_det = oregistry["waxs_det"]

AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
MASTER_TIMEOUT = 60
user_override.register("useDynamicTime")

# Make sure these are not staged. For acquire_time,
# # any change > 0.001 s takes ~0.5 s for Pilatus to complete!
DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
    acquire_time acquire_period num_images num_exposures
""".split()


@plan
def saxsExp(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
):
    """
    Execute a SAXS scan at the specified position.

    Parameters
    ----------
    pos_X : float
        X position for the scan
    pos_Y : float
        Y position for the scan
    thickness : float
        Sample thickness in mm
    scan_title : str
        Title for the scan
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(SAXS(pos_X, pos_Y, thickness, scan_title))``
    """
    if md is None:
        md = {}

    logger.info(f"Starting collection of SAXS for {scan_title}")

    yield from IfRequestedStopBeforeNextScan()

    yield from before_plan()

    yield from mode_SAXS()

    pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]

    yield from bps.mv(  # move saxs_z out for sample move, other is unimportant check
        # here.
        # fmt: off
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        saxs_stage.z,
        pinz_target,
        user_data.sample_thickness,
        thickness,
        terms.SAXS.collecting,
        1,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from bps.mv(  # move sampel in position
        # fmt: off
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    # setup AD names, paths and set metadata
    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md.update(md or {})
    _md["plan_name"] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    SAXSscan_path = techniqueSubdirectory("saxs")
    SAXS_file_name = local_file_template % (
        scan_title_clean,
        saxs_det.hdf1.file_number.get(),
    )
    _md["hdf5_path"] = str(SAXSscan_path)
    _md["hdf5_file"] = str(SAXS_file_name)

    pilatus_path = os.path.join(
        "/mnt/usaxscontrol", *SAXSscan_path.split(os.path.sep)[2:]
    )
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"
    local_name = os.path.join(SAXSscan_path, SAXS_file_name)
    logger.debug(f"SAXS HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, SAXS_file_name)
    logger.debug(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    saxs_det.hdf1.file_path._auto_monitor = False
    saxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        # fmt: off
        saxs_det.hdf1.file_name,
        scan_title_clean,
        saxs_det.hdf1.file_path,
        pilatus_path,
        saxs_det.hdf1.file_template,
        ad_file_template,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    saxs_det.hdf1.file_path._auto_monitor = True
    saxs_det.hdf1.file_template._auto_monitor = True
    # done with names and paths for AD by now...

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.sample_title,
        scan_title,
        user_data.sample_thickness,
        thickness,
        user_data.spec_scan,
        str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "SAXS",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from user_data.set_state_plan("starting SAXS collection")
    yield from bps.mv(
        # fmt: off
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([saxs_det.cam, saxs_det.hdf1])
    def _image_acquisition_steps():
        yield from measure_SAXS_Transmission()
        yield from insertSaxsFilters()

        yield from bps.mv(
            # fmt: off
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
            saxs_det.cam.num_images,
            terms.SAXS.num_images.get(),
            saxs_det.cam.acquire_time,
            terms.SAXS.acquire_time.get(),
            saxs_det.cam.acquire_period,
            terms.SAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from MONO_FEEDBACK_OFF()

        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in saxs_det.cam.stage_sigs:
                saxs_det.cam.stage_sigs.pop(k)
        saxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        saxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        saxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls])

        yield from bps.mv(
            # fmt: off
            usaxs_shutter,
            "close",
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )

        # SPEC-compatibility
        SCAN_N = RE.md["scan_id"] + 1
        yield from bps.mv(
            # fmt: off
            scaler1.preset_time,
            terms.SAXS.acquire_time.get() + 1,
            scaler0.preset_time,
            1.2 * terms.SAXS.acquire_time.get() + 1,
            scaler0.count_mode,
            "OneShot",
            scaler1.count_mode,
            "OneShot",
            scaler0.update_rate,
            60,
            scaler1.update_rate,
            60,
            scaler0.count,
            0,
            scaler0.delay,
            0,
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            user_data.spec_scan,
            str(SCAN_N),
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from user_data.set_state_plan(
            f"SAXS collection for {terms.SAXS.acquire_time.get()} s"
        )

        yield from record_sample_image_on_demand("saxs", scan_title_clean, _md)
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        scaler0.count,
        0,
        scaler1.count,
        0,
        terms.SAXS_WAXS.I0_gated,
        scaler1.channels.chan02.s.get(),
        scaler0.update_rate,
        5,
        scaler1.update_rate,
        5,
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        scaler0.delay,
        old_delay,
        terms.SAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from MONO_FEEDBACK_ON()

    yield from user_data.set_state_plan("Done SAXS")

    logger.info(f"Collected SAXS with HDF5 file: {local_name}")

    logger.debug(f"I0 value: {terms.SAXS_WAXS.I0_gated.get()}")
    yield from after_plan()


@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
@plan
def waxsExp(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
):
    """
    Execute a WAXS scan at the specified position.

    Parameters
    ----------
    pos_X : float
        X position for the scan
    pos_Y : float
        Y position for the scan
    thickness : float
        Sample thickness in mm
    scan_title : str
        Title for the scan
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(WAXS(pos_X, pos_Y, thickness, scan_title))``
    """
    if md is None:
        md = {}

    logger.info(f"Starting collection of WAXS for {scan_title}")

    yield from IfRequestedStopBeforeNextScan()

    yield from before_plan()

    yield from mode_WAXS()

    # move all in place.
    yield from bps.mv(
        # fmt: off
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        user_data.sample_thickness,
        thickness,
        terms.WAXS.collecting,
        1,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    # setup names and paths here...
    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title
    _md["plan_name"] = "WAXS"

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    WAXSscan_path = techniqueSubdirectory("waxs")
    WAXS_file_name = local_file_template % (
        scan_title_clean,
        waxs_det.hdf1.file_number.get(),
    )
    _md["hdf5_path"] = str(WAXSscan_path)
    _md["hdf5_file"] = str(WAXS_file_name)

    pilatus_path = os.path.join("/mnt/share1", *WAXSscan_path.split(os.path.sep)[2:])
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"
    local_name = os.path.join(WAXSscan_path, WAXS_file_name)
    logger.debug(f"WAXS HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, WAXS_file_name)
    logger.debug(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    waxs_det.hdf1.file_path._auto_monitor = False
    waxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        # fmt: off
        waxs_det.hdf1.file_name,
        scan_title_clean,
        waxs_det.hdf1.file_path,
        pilatus_path,
        waxs_det.hdf1.file_template,
        ad_file_template,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    waxs_det.hdf1.file_path._auto_monitor = True
    waxs_det.hdf1.file_template._auto_monitor = True
    # paths and names done by now

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.sample_title,
        scan_title,
        user_data.sample_thickness,
        thickness,
        user_data.spec_scan,
        str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "WAXS",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from user_data.set_state_plan("starting WAXS collection")
    yield from bps.mv(
        # fmt: off
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([waxs_det.cam, waxs_det.hdf1])
    def _image_acquisition_steps():
        yield from insertWaxsFilters()

        yield from bps.mv(
            # fmt: off
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
            waxs_det.cam.num_images,
            terms.WAXS.num_images.get(),
            waxs_det.cam.acquire_time,
            terms.WAXS.acquire_time.get(),
            waxs_det.cam.acquire_period,
            terms.WAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from MONO_FEEDBACK_OFF()

        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in waxs_det.cam.stage_sigs:
                waxs_det.cam.stage_sigs.pop(k)
        waxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        waxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        waxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls, trd_controls])

        yield from bps.mv(
            # fmt: off
            usaxs_shutter,
            "close",
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )

        yield from bps.mv(
            # fmt: off
            scaler1.preset_time,
            terms.WAXS.acquire_time.get() + 1,
            scaler0.preset_time,
            1.2 * terms.WAXS.acquire_time.get() + 1,
            scaler0.count_mode,
            "OneShot",
            scaler1.count_mode,
            "OneShot",
            scaler0.update_rate,
            60,
            scaler1.update_rate,
            60,
            scaler0.count,
            0,
            scaler0.delay,
            0,
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from user_data.set_state_plan(
            f"WAXS collection for {terms.WAXS.acquire_time.get()} s"
        )

        yield from record_sample_image_on_demand("waxs", scan_title_clean, _md)

        yield from areaDetectorAcquire(waxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        scaler0.count,
        0,
        scaler1.count,
        0,
        terms.SAXS_WAXS.I0_gated,
        scaler1.channels.chan02.s.get(),
        terms.SAXS_WAXS.diode_transmission,
        scaler0.channels.chan05.s.get(),
        terms.SAXS_WAXS.diode_gain,
        trd_controls.femto.gain.get(),
        terms.SAXS_WAXS.I0_transmission,
        scaler0.channels.chan02.s.get(),
        terms.SAXS_WAXS.I0_gain,
        I0_controls.femto.gain.get(),
        scaler0.update_rate,
        5,
        scaler1.update_rate,
        5,
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        scaler0.delay,
        old_delay,
        terms.WAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
    )
    yield from MONO_FEEDBACK_ON()

    yield from user_data.set_state_plan("Done WAXS")

    logger.info(f"Collected WAXS with HDF5 file: {local_name}")

    logger.debug(f"I0 value: {terms.SAXS_WAXS.I0_gated.get()}")
    yield from after_plan()
