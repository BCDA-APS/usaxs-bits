"""
Test SAXS acquisition plan for the USAXS instrument.

``test_plan`` collects a single SAXS image with fixed 5 s exposure and
hardcoded ``scan_title="test"``, useful for verifying detector setup without
a full sample scan.
"""

import os
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from apstools.plans import restorable_stage_sigs
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from usaxs.utils.utils import techniqueSubdirectory

from .amplifiers_plan import autoscale_amplifiers
from .area_detector_plans import areaDetectorAcquire
from .sample_imaging import record_sample_image_on_demand

saxs_det = oregistry["saxs_det"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
I0_controls = oregistry["I0_controls"]

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
    """Bluesky plan: collect a test SAXS image using the area detector.

    Acquires a single 5 s SAXS image with ``scan_title="test"``.  Intended
    for verifying detector file paths and staging without a full sample scan.

    Parameters
    ----------
    md : dict, optional
        Extra metadata merged into the run's start document.
    thickness : float, optional
        Sample thickness in mm, by default 0.0.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    scan_title = "test"
    _md = md or OrderedDict()
    _md["plan_name"] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = scan_title

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
    )
    saxs_det.hdf1.file_path._auto_monitor = True
    saxs_det.hdf1.file_template._auto_monitor = True

    @restorable_stage_sigs([saxs_det.cam, saxs_det.hdf1])
    def _image_acquisition_steps():
        yield from bps.mv(
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
                saxs_det.cam.stage_sigs.pop(k)
        saxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        saxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        saxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls])

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
            # this is needed to make sure we get as up to date I0 number as possible for
            # AD software.
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
            timeout=60,
        )

        yield from record_sample_image_on_demand("saxs", scan_title_clean, _md)
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()
