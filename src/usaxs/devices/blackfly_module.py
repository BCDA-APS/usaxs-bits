"""
Point Grey Blackfly area detector

note: this is one of the easiest area detector setups in Ophyd
"""
# TODO: THis is an ad

import os
import warnings

# from apstools.devices import AD_prime_plugin2
from bluesky import plan_stubs as bps
from ophyd import ADComponent
from ophyd import AreaDetector
from ophyd import ColorConvPlugin
from ophyd import EpicsSignal
from ophyd import ImagePlugin
from ophyd import PointGreyDetectorCam
from ophyd import ProcessPlugin
from ophyd import SingleTrigger
from ophyd import TransformPlugin

from .area_detector_common import DATABROKER_ROOT_PATH
from .area_detector_common import EpicsDefinesJpegFileNames
from .area_detector_common import EpicsDefinesTiffFileNames
from .area_detector_common import Override_AD_plugin_primed
from .area_detector_common import _validate_AD_FileWriter_path_

# path for image files (as seen by EPICS area detector writer plugin)
# path seen by detector IOC
PATH_BASE = "/share1/USAXS_data/test/blackfly_optical"
WRITE_IMAGE_FILE_PATH = PATH_BASE + "/%Y/%m/%d/"
# path seen by databroker
READ_IMAGE_FILE_PATH = WRITE_IMAGE_FILE_PATH

_validate_AD_FileWriter_path_(WRITE_IMAGE_FILE_PATH, DATABROKER_ROOT_PATH)
_validate_AD_FileWriter_path_(READ_IMAGE_FILE_PATH, DATABROKER_ROOT_PATH)


class MyPointGreyDetector(SingleTrigger, AreaDetector):
    """PointGrey Black Fly detector(s) as used by 12-ID-E USAXS"""

    cam: ADComponent[PointGreyDetectorCam] = ADComponent(PointGreyDetectorCam, "cam1:")
    image: ADComponent[ImagePlugin] = ADComponent(ImagePlugin, "image1:")


class MyPointGreyDetectorJPEG(MyPointGreyDetector, AreaDetector):
    """
    Variation to write image as JPEG

    To save an image (using existing configuration)::

        blackfly_optical.stage()
        blackfly_optical.trigger()
        blackfly_optical.unstage()

    """

    jpeg1: ADComponent[EpicsDefinesJpegFileNames] = ADComponent(
        EpicsDefinesJpegFileNames,
        suffix="JPEG1:",
        root=DATABROKER_ROOT_PATH,
        write_path_template=WRITE_IMAGE_FILE_PATH,
        read_path_template=READ_IMAGE_FILE_PATH,
        kind="normal",
    )
    trans1: ADComponent[TransformPlugin] = ADComponent(TransformPlugin, "Trans1:")
    cc1: ADComponent[ColorConvPlugin] = ADComponent(ColorConvPlugin, "CC1:")
    proc1: ADComponent[ProcessPlugin] = ADComponent(ProcessPlugin, "Proc1:")

    def __init__(self, *args, **kwargs):
        """
        Initialize the detector with specific settings.
        """
        super().__init__(*args, **kwargs)
        # Add jpeg1 to read_attrs
        self.read_attrs.append("jpeg1")
        # Configure jpeg1 stage_sigs
        self.jpeg1.stage_sigs["file_write_mode"] = "Capture"

        if not Override_AD_plugin_primed(self.jpeg1):
            warnings.warn(
                "NOTE: blackfly_optical.jpeg1 has not been primed yet."
                "  BEFORE using this detector in bluesky, call: "
                "  AD_prime_plugin2(blackfly_optical.jpeg1)",
                stacklevel=2,
            )

    @property
    def image_file_name(self) -> str:
        """Get the full file name of the JPEG image.

        Returns:
            str: Full path and name of the JPEG image file.
        """
        return self.jpeg1.full_file_name.get()

    def image_prep(self, path: str, filename_base: str, order_number: int):
        """Prepare image file path and name settings.

        Args:
            path: Directory path where image will be saved.
            filename_base: Base name for the image file.
            order_number: Sequential number for the image file.

        Yields:
            Generator for setting file path and name parameters.
        """
        plugin = self.jpeg1
        path = "/mnt" + os.path.abspath(path) + "/"  # MUST end with "/"
        yield from bps.mv(
            plugin.file_path,
            path,
            plugin.file_name,
            filename_base,
            plugin.file_number,
            order_number,
        )

    @property
    def should_save_image(self) -> bool:
        """Check if the image should be saved.

        Returns:
            bool: True if image should be saved, False otherwise.
        """
        return _flag_save_sample_image_.get() in (1, "Yes")

    def take_image(self):
        """Take an image using the detector.

        Yields:
            Generator for staging, triggering, and unstaging the detector.
        """
        yield from bps.stage(self)
        yield from bps.trigger(self, wait=True)
        yield from bps.unstage(self)


class MyPointGreyDetectorTIFF(MyPointGreyDetector, AreaDetector):
    """
    Variation to write image as TIFF

    To save an image (using existing configuration)::

        blackfly_optical.stage()
        blackfly_optical.trigger()
        blackfly_optical.unstage()

    """

    tiff1: ADComponent[EpicsDefinesTiffFileNames] = ADComponent(
        EpicsDefinesTiffFileNames,
        suffix="TIFF1:",
        root=DATABROKER_ROOT_PATH,
        write_path_template=WRITE_IMAGE_FILE_PATH,
        read_path_template=READ_IMAGE_FILE_PATH,
        kind="normal",
    )
    #trans1: ADComponent[TransformPlugin] = ADComponent(TransformPlugin, "Trans1:")
    #cc1: ADComponent[ColorConvPlugin] = ADComponent(ColorConvPlugin, "CC1:")
    #proc1: ADComponent[ProcessPlugin] = ADComponent(ProcessPlugin, "Proc1:")

    @property
    def image_file_name(self) -> str:
        """Get the full file name of the TIFF image.

        Returns:
            str: Full path and name of the TIFF image file.
        """
        return self.tiff1.full_file_name.get()

    def image_prep(self, path: str, filename_base: str, order_number: int):
        """Prepare image file path and name settings.

        Args:
            path: Directory path where image will be saved.
            filename_base: Base name for the image file.
            order_number: Sequential number for the image file.

        Yields:
            Generator for setting file path and name parameters.
        """
        plugin = self.tiff1
        path = "/mnt" + os.path.abspath(path) + "/"  # MUST end with "/"
        yield from bps.mv(
            # fmt: off
            plugin.file_path,             path,
            plugin.file_name,             filename_base,
            plugin.file_number,           order_number,
            # fmt: on
        )

    @property
    def should_save_image(self) -> bool:
        """Check if the image should be saved.

        Returns:
            bool: True if image should be saved, False otherwise.
        """
        return _flag_save_sample_image_.get() in (1, "Yes")

    def take_image(self):
        """Take an image using the detector.

        Yields:
            Generator for staging, triggering, and unstaging the detector.
        """
        yield from bps.stage(self)
        yield from bps.trigger(self, wait=True)
        yield from bps.unstage(self)


_flag_save_sample_image_ = EpicsSignal(
    "usxLAX:saveFLY2Image",
    string=True,
    name="_flag_save_sample_image_",
)
