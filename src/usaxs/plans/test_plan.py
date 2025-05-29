"""
Test plans for USAXS.
"""

import os
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from apsbits.utils.config_loaders import get_config
from apstools.plans import restorable_stage_sigs
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from ..utils.setup_new_user import techniqueSubdirectory
from .amplifiers_plan import autoscale_amplifiers
from .area_detector_plans import areaDetectorAcquire
from .sample_imaging import record_sample_image_on_demand

saxs_det = oregistry["saxs_det"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
I0_controls = oregistry["I0_controls"]


iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")
scaler1_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER1_NAME")

scaler0 = oregistry["scaler0"]
scaler1 = oregistry["scaler1"]

scaler0.stage_sigs["count_mode"] = "OneShot"
scaler0.select_channels()
scaler1.select_channels()

I0 = oregistry["I0"]
I0_SIGNAL = oregistry["I0_SIGNAL"]
I00 = oregistry["I00"]
I00_SIGNAL = oregistry["I00_SIGNAL"]
TRD_SIGNAL = oregistry["TRD_SIGNAL"]
UPD_SIGNAL = oregistry["UPD_SIGNAL"]


AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
    acquire_time acquire_period num_images num_exposures
""".split()


@plan
def test_plan(md=None, thickness=0.0):
    """
    Plan for collecting a test SAXS image using the area detector.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    thickness : float, optional
        Sample thickness in mm.
    """
    scan_title = "test"
    # _md = apsbss.update_MD(md or {})
    _md = md or OrderedDict()
    _md.update(md or {})
    _md["plan_name"] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = scan_title

    # SPEC-compatibility

    # these two templates match each other, sort of
    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    # path on local file system
    SAXSscan_path = techniqueSubdirectory("saxs")
    sfn_args = (
        scan_title_clean,
        saxs_det.hdf1.file_number.get(),
    )
    SAXS_file_name = local_file_template % sfn_args
    _md["hdf5_path"] = str(SAXSscan_path)
    _md["hdf5_file"] = str(SAXS_file_name)

    # NFS-mounted path as the Pilatus detector sees it
    pilatus_path = os.path.join(
        "/mnt/usaxscontrol", *SAXSscan_path.split(os.path.sep)[2:]
    )
    # area detector will create this path if needed ("Create dir. depth" setting)
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"  # area detector needs this
    # local_name = os.path.join(SAXSscan_path, SAXS_file_name)
    # pilatus_name = os.path.join(pilatus_path, SAXS_file_name)
    # logger.info(f"Area Detector HDF5 file: {local_name}")
    # logger.info(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    saxs_det.hdf1.file_path._auto_monitor = False
    saxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        saxs_det.hdf1.file_name,
        scan_title_clean,
        saxs_det.hdf1.file_path,
        pilatus_path,
        saxs_det.hdf1.file_template,
        ad_file_template,
        timeout=60,
        # auto_monitor=False,
    )
    saxs_det.hdf1.file_path._auto_monitor = True
    saxs_det.hdf1.file_template._auto_monitor = True

    @restorable_stage_sigs([saxs_det.cam, saxs_det.hdf1])
    def _image_acquisition_steps():
        # yield from measure_SAXS_Transmission()
        # yield from insertSaxsFilters()

        yield from bps.mv(
            # mono_shutter, "open",
            # monochromator.feedback.on, MONO_FEEDBACK_OFF,
            # usaxs_shutter, "open",
            saxs_det.cam.num_images,
            1,
            saxs_det.cam.acquire_time,
            5,
            saxs_det.cam.acquire_period,
            5 + 0.004,
            timeout=60,
        )
        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in saxs_det.cam.stage_sigs:
                # print(f"Removing {saxs_det.cam.name}.stage_sigs[{k}].")
                saxs_det.cam.stage_sigs.pop(k)
        saxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        saxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        saxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls])

        # yield from bps.mv(
        #     usaxs_shutter, "close",
        #     timeout=MASTER_TIMEOUT,
        # )

        yield from bps.mv(
            scaler1.preset_time,
            terms.SAXS.acquire_time.get() + 1,
            scaler0.preset_time,
            1.2 * terms.SAXS.acquire_time.get() + 1,
            scaler0.count_mode,
            "OneShot",
            scaler1.count_mode,
            "OneShot",
            # update as fast as hardware will allow
            # this is needed to make sure we get as up to date I0 number as possible for AD software.
            scaler0.update_rate,
            60,
            scaler1.update_rate,
            60,
            scaler0.count,
            0,
            scaler1.count,
            0,
            scaler0.delay,
            0,
            # terms.SAXS_WAXS.start_exposure_time, ts,
            timeout=60,
        )

        yield from record_sample_image_on_demand("saxs", scan_title_clean, _md)
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()
