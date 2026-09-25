"""
User-facing SAXS and WAXS acquisition plans.

Public entry points
-------------------
* ``saxsExp`` — collect a SAXS image at a given sample position.
* ``waxsExp`` — collect a WAXS image at a given sample position.
"""

import datetime
import logging
import os
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from apstools.plans import restorable_stage_sigs
from apstools.utils import cleanupText
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from ..suspenders.beam_guard import beam_guarded
from ..utils.constants import constants
from ..utils.override import user_override
from ..utils.user_sample_title import getSampleTitle
from ..utils.utils import techniqueSubdirectory
from .area_detector_plans import areaDetectorAcquire
from .command_list import after_plan
from .command_list import before_plan
from .filter_plans import insertSaxsFilters
from .filter_plans import insertWaxsFilters
from .fx4_autorange_plan import autoscale_amplifiers
from .fx4_setup import finish_gated_I0
from .fx4_setup import restore_upd_channel
from .fx4_setup import start_gated_I0
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
I0_controls = oregistry["I0_controls"]
lax_autosave = oregistry["lax_autosave"]
m_stage = oregistry["m_stage"]
mono_shutter = oregistry["mono_shutter"]
s_stage = oregistry["s_stage"]
saxs_det = oregistry["saxs_det"]
saxs_stage = oregistry["saxs_stage"]
terms = oregistry["terms"]
trd_controls = oregistry["trd_controls"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_data"]
waxs_det = oregistry["waxs_det"]

AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
user_override.register("useDynamicTime")

# Make sure these are not staged. For acquire_time,
# any change > 0.001 s takes ~0.5 s for Pilatus to complete!
DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
    acquire_time acquire_period num_images num_exposures
""".split()


@plan
@beam_guarded
def saxsExp(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    title: str,
    md=None,
):
    """Bluesky plan: collect a SAXS image at the given sample position.

    Moves to SAXS mode, positions the sample, sets up the Pilatus detector
    file paths, measures transmission, inserts SAXS filters, acquires an
    image, and records metadata.

    Parameters
    ----------
    pos_X : float
        Sample X position in mm.
    pos_Y : float
        Sample Y position in mm.
    thickness : float
        Sample thickness in mm.
    title : str
        Human-readable title used for the output file name.
    md : dict, optional
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(saxsExp(pos_X, pos_Y, thickness, title))``
    """

    if md is None:
        md = {}

    logger.info(f"Starting collection of SAXS for {title}")

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
    title = getSampleTitle(title)
    _md = md or OrderedDict()
    _md["plan_name"] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = title

    title_clean = cleanupText(title)

    # SPEC-compatibility
    # SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    SAXSscan_path = techniqueSubdirectory("saxs")
    SAXS_file_name = local_file_template % (
        title_clean,
        saxs_det.hdf1.file_number.get(),
    )
    _md["hdf5_path"] = str(SAXSscan_path)
    _md["hdf5_file"] = str(SAXS_file_name)

    pilatus_path = os.path.join("/mnt/usaxscontrol", *SAXSscan_path.split(os.path.sep)[2:])
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"
    local_name = os.path.join(SAXSscan_path, SAXS_file_name)
    pilatus_name = os.path.join(pilatus_path, SAXS_file_name)

    saxs_det.hdf1.file_path._auto_monitor = False
    saxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        # fmt: off
        saxs_det.hdf1.file_name,
        title_clean,
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
        title,
        user_data.sample_thickness,
        thickness,
        # user_data.spec_scan,
        # str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "SAXS",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from user_data.set_state_plan("starting SAXS collection")
    #yield from bps.mv(
        # fmt: off
        # user_data.spec_file,
        # os.path.split(specwriter.spec_filename)[-1],
     #   timeout=MASTER_TIMEOUT,
        # fmt: on
    #)
    # Filled in by _image_acquisition_steps below.  A dict rather than a
    # return value because the generator is wrapped by restorable_stage_sigs,
    # and a decorator is free not to pass one through.
    measured = {}

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
        # SCAN_N = RE.md["scan_id"] + 1
        yield from bps.mv(
            # fmt: off
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            # user_data.spec_scan,
            # str(SCAN_N),
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from user_data.set_state_plan(f"SAXS collection for {terms.SAXS.acquire_time.get()} s")

        yield from record_sample_image_on_demand("saxs", title_clean, _md)

        # Suspender rewind boundary.  Caps how far back a beam-loss resume can
        # replay: without it the RunEngine would re-issue every message since
        # the checkpoint inside measure_SAXS_Transmission, including the Blackfly
        # optical image setup above.  That replay runs outside the original
        # generator frames, so the try/except in record_sample_image_on_demand
        # cannot soften a camera failure and it aborts the command list.
        # No run is open here -- bp.count inside areaDetectorAcquire opens its
        # own and checkpoints again immediately (bluesky one_shot), so open_run
        # is never replayed.
        yield from bps.checkpoint()

        # Start the I0 integration and let it run under the exposure.  This is
        # the software stand-in for scaler1's hardware gate; see
        # fx4_setup.start_gated_I0.
        yield from start_gated_I0(terms.SAXS.acquire_time.get())
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)
        measured["I0_gated"] = yield from finish_gated_I0()

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        terms.SAXS_WAXS.I0_gated,
        measured.get("I0_gated", 0),
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        terms.SAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    logger.info("pre mono")

    yield from MONO_FEEDBACK_ON()

    yield from user_data.set_state_plan("Done SAXS")

    logger.info(f"Collected SAXS with HDF5 file: {local_name}")

    logger.debug(f"I0 value: {terms.SAXS_WAXS.I0_gated.get()}")
    yield from after_plan()


@plan
@beam_guarded
def waxsExp(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    title: str,
    md=None,
):
    """Bluesky plan: collect a WAXS image at the given sample position.

    Moves to WAXS mode, positions the sample, sets up the Pilatus detector
    file paths, inserts WAXS filters, acquires an image, and records metadata.

    Parameters
    ----------
    pos_X : float
        Sample X position in mm.
    pos_Y : float
        Sample Y position in mm.
    thickness : float
        Sample thickness in mm.
    title : str
        Human-readable title used for the output file name.
    md : dict, optional
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(waxsExp(pos_X, pos_Y, thickness, title))``
    """

    if md is None:
        md = {}

    logger.info(f"Starting collection of WAXS for {title}")

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
    title = getSampleTitle(title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = title
    _md["plan_name"] = "WAXS"

    title_clean = cleanupText(title)

    # SPEC-compatibility
    # SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    WAXSscan_path = techniqueSubdirectory("waxs")
    WAXS_file_name = local_file_template % (
        title_clean,
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
        title_clean,
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
        title,
        user_data.sample_thickness,
        thickness,
        # user_data.spec_scan,
        # str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "WAXS",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from user_data.set_state_plan("starting WAXS collection")
    #yield from bps.mv(
        # fmt: off
        # user_data.spec_file,
        # os.path.split(specwriter.spec_filename)[-1],
        #timeout=MASTER_TIMEOUT,
        # fmt: on
   # )
    # See the matching note in saxsExp.
    measured = {}

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

        # Capture the direct-beam readings here, with the shutter still open
        # and both channels freshly counted by the autoscale above.  The old
        # code read them from scaler0 at the very end of the plan, relying on
        # its free-running AutoCount; the FX4 only updates when triggered, so
        # the values have to be taken while they mean something.
        measured["diode"] = trd_controls.signal.get()
        measured["I0"] = I0_controls.signal.get()

        # Autoscaling TRD left usxFX4's shared Range pointed at it.  TRD is not
        # needed again in this plan, so hand it straight back to UPD.
        yield from restore_upd_channel()

        yield from bps.mv(
            # fmt: off
            usaxs_shutter,
            "close",
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )

        yield from bps.mv(
            # fmt: off
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            timeout=MASTER_TIMEOUT,
            # fmt: on
        )
        yield from user_data.set_state_plan(f"WAXS collection for {terms.WAXS.acquire_time.get()} s")

        yield from record_sample_image_on_demand("waxs", title_clean, _md)

        # Suspender rewind boundary -- see the matching comment in saxsExp.
        yield from bps.checkpoint()

        yield from start_gated_I0(terms.WAXS.acquire_time.get())
        yield from areaDetectorAcquire(waxs_det, create_directory=-5, md=_md)
        measured["I0_gated"] = yield from finish_gated_I0()

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    # The *_gain PVs stay at 1.0: the FX4 reading is already gain-independent
    # picoamps, so anything downstream that still divides by gain gets the
    # right answer.  See the matching note in sample_transmission.
    yield from bps.mv(
        # fmt: off
        terms.SAXS_WAXS.I0_gated,
        measured.get("I0_gated", 0),
        terms.SAXS_WAXS.diode_transmission,
        measured.get("diode", 0),
        terms.SAXS_WAXS.diode_gain,
        1.0,
        terms.SAXS_WAXS.I0_transmission,
        measured.get("I0", 0),
        terms.SAXS_WAXS.I0_gain,
        1.0,
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        terms.WAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from MONO_FEEDBACK_ON()

    yield from user_data.set_state_plan("Done WAXS")

    logger.info(f"Collected WAXS with HDF5 file: {local_name}")

    logger.debug(f"I0 value: {terms.SAXS_WAXS.I0_gated.get()}")
    yield from after_plan()
