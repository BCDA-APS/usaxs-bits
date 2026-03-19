"""
Dectris Pilatus and Eiger area detector support for the 12-ID-E USAXS instrument.

``MyPilatusDetectorCam``
    Pilatus camera mixin with ADCore V3.4 staging defaults.
``CustomHDF5Plugin``
    HDF5 plugin with EPICS-controlled file names and ``file_write_mode='Single'``.
    Builds on ``AD_EpicsFileNameMixin`` + ``FileStoreHDF5SingleIterativeWrite``.
``MyPilatusDetector``
    Complete Pilatus detector device (cam + image + HDF5).
``MyEigerDetector``
    Complete Eiger 2X detector device (cam + image + bad-pixel + HDF5).

File-system paths
-----------------
* SAXS (Pilatus): ``/mnt/usaxscontrol/USAXS_data/test/pilatus/%Y/%m/%d/``
* WAXS (Eiger):  ``/mnt/share1/USAXS_data/test/pilatus/%Y/%m/%d/``
* Databroker read path: ``/share1/USAXS_data/test/pilatus/%Y/%m/%d/``
"""

import logging
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
from .area_detector_common import _validate_AD_FileWriter_path_

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
    """Pilatus camera with ADCore V3.4 staging defaults.

    Sets conservative acquisition defaults on staging: 10 ms exposure,
    1 image, 1 exposure per image, plugins enabled.  Also used for the
    Eiger camera because it shares the same ADCore cam interface.
    """

    def __init__(self, *args, **kwargs):
        """Set default stage_sigs for a single short acquisition."""
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
        """Configure staging defaults; bypass HDF5Plugin.__init__().

        Calls ``FileStorePluginBase.__init__`` directly to avoid the default
        HDF5Plugin initialisation which conflicts with EPICS-controlled file
        naming.  Several attributes (``capture``, ``file_name``, etc.) are
        removed from ``stage_sigs`` because they must be set by the plan,
        not during staging.
        """
        # Skip over the HDF5Plugin.__init__() — use FileStorePluginBase instead.
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

    def stage(self) -> None:
        """Stage the plugin; guard against ``capture`` with ``file_write_mode='Single'``."""
        # Again, do not press the Capture button in the HDF plugin
        if "capture" in self.stage_sigs:
            warnings.warn(
                "Do not use capture with file_write_mode='Single'", stacklevel=2
            )
            self.stage_sigs.pop("capture")
        super().stage()


class MyPilatusDetector(SingleTrigger_V34, DetectorBase):
    """Pilatus 100k detector for 12-ID-E USAXS (SAXS mode).

    Writes HDF5 files to ``WRITE_PATH_TEMPLATE`` (IOC view) / ``READ_PATH_TEMPLATE``
    (databroker view).
    """

    def __init__(self, *args, **kwargs):
        """Add ``hdf1`` to read attrs and disable image blocking callbacks."""
        super().__init__(*args, **kwargs)
        self.read_attrs.append("hdf1")
        self.image.stage_sigs["blocking_callbacks"] = "No"

    cam = ADComponent(MyPilatusDetectorCam, "cam1:")
    image = ADComponent(ImagePlugin, "image1:")
    hdf1 = ADComponent(
        CustomHDF5Plugin,
        "HDF1:",
        write_path_template=WRITE_PATH_TEMPLATE,
        read_path_template=READ_PATH_TEMPLATE,
    )


class MyEigerDetector(SingleTrigger_V34, DetectorBase):
    """Eiger 2X detector for 12-ID-E USAXS (WAXS mode).

    Uses ``MyPilatusDetectorCam`` because the Eiger shares the same ADCore
    cam interface at this beamline.  Includes a ``bad_pixel`` plugin
    (ADCore NDBadPixel, new in AD 3.13).  Writes to ``WRITE_PATH_TEMPLATE_WAXS``.
    """

    def __init__(self, *args, **kwargs):
        """Add ``hdf1`` to read attrs."""
        super().__init__(*args, **kwargs)
        self.read_attrs.append("hdf1")

    cam = ADComponent(MyPilatusDetectorCam, "cam1:")
    image = ADComponent(ImagePlugin, "image1:")
    bad_pixel = ADComponent(BadPixelPlugin, "BadPix1:")
    hdf1 = ADComponent(
        CustomHDF5Plugin,
        "HDF1:",
        write_path_template=WRITE_PATH_TEMPLATE,
        read_path_template=READ_PATH_TEMPLATE,
    )
