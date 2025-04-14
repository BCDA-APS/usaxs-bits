"""
Dectris Pilatus area detectors.
"""
#TODO: THis is an ad

# TODO review for newer code in APS tools

import logging

# from ophyd.areadetector.filestore_mixins import FileStoreHDF5IterativeWrite
# from apstools.devices import AD_EpicsHdf5FileName
import pathlib
import warnings

from apstools.devices import CamMixin_V34
from apstools.devices import SingleTrigger_V34
from apstools.devices.area_detector_support import AD_EpicsFileNameMixin
from ophyd import ADComponent
from ophyd import PilatusDetectorCam
from ophyd.areadetector import DetectorBase
from ophyd.areadetector.filestore_mixins import FileStoreHDF5SingleIterativeWrite
from ophyd.areadetector.filestore_mixins import FileStorePluginBase
from ophyd.areadetector.plugins import HDF5Plugin_V34 as HDF5Plugin
from ophyd.areadetector.plugins import ImagePlugin_V34 as ImagePlugin

from .area_detector_common import DATABROKER_ROOT_PATH
from .area_detector_common import BadPixelPlugin
from .area_detector_common import (
    _validate_AD_FileWriter_path_,
)
from .area_detector_common import (
    area_detector_EPICS_PV_prefix,
)

logger = logging.getLogger(__name__)

# path for HDF5 files (as seen by EPICS area detector HDF5 plugin)
# path seen by detector IOC
IMAGE_DIR = "test/pilatus/%Y/%m/%d"  # our choice for file arrangement
AD_IOC_MOUNT_PATH = pathlib.Path("/mnt/usaxscontrol/USAXS_data")
AD_IOC_MOUNT_PATH_WAXS = pathlib.Path("/mnt/share1/USAXS_data")

# WRITE_HDF5_FILE_PATH_PILATUS = "/mnt/usaxscontrol/USAXS_data/test/pilatus/%Y/%m/%d/"

# path seen by databroker
BLUESKY_MOUNT_PATH = pathlib.Path("/share1/USAXS_data")
# READ_HDF5_FILE_PATH_PILATUS = "/share1/USAXS_data/test/pilatus/%Y/%m/%d/"

# MUST end with a `/`, pathlib will NOT provide it
WRITE_PATH_TEMPLATE = f"{AD_IOC_MOUNT_PATH / IMAGE_DIR}/"
WRITE_PATH_TEMPLATE_WAXS = f"{AD_IOC_MOUNT_PATH_WAXS / IMAGE_DIR}/"
READ_PATH_TEMPLATE = f"{BLUESKY_MOUNT_PATH / IMAGE_DIR}/"

_validate_AD_FileWriter_path_(WRITE_PATH_TEMPLATE, DATABROKER_ROOT_PATH)
_validate_AD_FileWriter_path_(WRITE_PATH_TEMPLATE_WAXS, DATABROKER_ROOT_PATH)


class MyPilatusDetectorCam(CamMixin_V34, PilatusDetectorCam):
    """Revise SimDetectorCam for ADCore revisions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update(
            dict(
                acquire_time=0.01,
                acquire_period=0.015,  # a wee bit longer than acquire_time
                num_images=1,
                num_exposures=1,  # Exp./image
                wait_for_plugins="Yes",
                array_callbacks="Enable",
            )
        )


class CustomHDF5Plugin(
    AD_EpicsFileNameMixin, FileStoreHDF5SingleIterativeWrite, HDF5Plugin
):
    """
    Add data acquisition methods to HDF5Plugin.

    * ``stage()`` - prepare device PVs before data acquisition
    * ``unstage()`` - restore device PVs after data acquisition
    * ``generate_datum()`` - coordinate image storage metadata
    """

    def __init__(self, *args, **kwargs):
        # super().__init__(*args, **kwargs)
        # alternative from AD_EpicsHdf5FileName
        # Skip over the HDF5Plugin.__init__().
        FileStorePluginBase.__init__(self, *args, **kwargs)
        self.filestore_spec = "AD_HDF5"  # spec name stored in resource doc
        self.stage_sigs.update(
            dict(
                array_callbacks="Disable",
                auto_increment="Yes",
                auto_save="Yes",
                blocking_callbacks="No",
                compression="zlib",
                file_write_mode="Single",  # was Stream
                lazy_open="Yes",
                store_perform="No",
                zlevel=6,
            )
        )
        # capture is not used with Single mode
        # parent.cam.array_callbacks is staged once in the cam
        # create_directory must be set before file_path, which is set before staging
        # user must control file name & path in the plan
        these_attributes_should_not_be_staged = """
            array_counter
            capture
            create_directory
            file_name
            file_number
            file_path
            file_template
            num_capture
            parent.cam.array_callbacks
        """.split()
        for k in these_attributes_should_not_be_staged:
            if k in self.stage_sigs:
                self.stage_sigs.pop(k)

    def stage(self):
        # Again, do not press the Capture button in the HDF plugin
        if "capture" in self.stage_sigs:
            warnings.warn("Do not use capture with file_write_mode='Single'")
            self.stage_sigs.pop("capture")
        super().stage()


class MyPilatusDetector(SingleTrigger_V34, DetectorBase):
    """Pilatus detector(s) as used by 12-ID-E USAXS"""

    cam = ADComponent(MyPilatusDetectorCam, "cam1:")
    image = ADComponent(ImagePlugin, "image1:")

    hdf1 = ADComponent(
        CustomHDF5Plugin,
        "HDF1:",
        # root = DATABROKER_ROOT_PATH,
        write_path_template=WRITE_PATH_TEMPLATE,
        read_path_template=READ_PATH_TEMPLATE,
    )


class MyEigerDetector(SingleTrigger_V34, DetectorBase):
    """Eiger2 detector(s) as used by 12-ID-E USAXS"""

    cam = ADComponent(MyPilatusDetectorCam, "cam1:")
    image = ADComponent(ImagePlugin, "image1:")
    bad_pixel = ADComponent(BadPixelPlugin, "BadPix1:")

    hdf1 = ADComponent(
        CustomHDF5Plugin,
        "HDF1:",
        # root = DATABROKER_ROOT_PATH,
        write_path_template=WRITE_PATH_TEMPLATE_WAXS,
        read_path_template=READ_PATH_TEMPLATE,
    )


try:
    nm = "Pilatus 100k"
    prefix = area_detector_EPICS_PV_prefix[nm]
    saxs_det = MyPilatusDetector(
        prefix, name="saxs_det", labels=["camera", "area_detector"]
    )
    saxs_det.read_attrs.append("hdf1")
    saxs_det.image.stage_sigs["blocking_callbacks"] = "No"
except TimeoutError:
    msg = f"Timeout connecting with {nm} ({prefix})"
    logger.warning(msg)
    saxs_det = None

# try:
#     nm = "Pilatus 200kw"
#     prefix = area_detector_EPICS_PV_prefix[nm]
#     waxs_det = MyPilatusDetector(
#         prefix, name="waxs_det", labels=["camera", "area_detector"])
#     waxs_det.read_attrs.append("hdf1")
# except TimeoutError as exc_obj:
#     msg = f"Timeout connecting with {nm} ({prefix})"
#     logger.warning(msg)
#     waxs_det = None
try:
    nm = "Eiger 2X"
    prefix = area_detector_EPICS_PV_prefix[nm]
    waxs_det = MyEigerDetector(
        prefix, name="waxs_det", labels=["camera", "area_detector"]
    )
    waxs_det.read_attrs.append("hdf1")
except TimeoutError:
    msg = f"Timeout connecting with {nm} ({prefix})"
    logger.warning(msg)
    waxs_det = None
