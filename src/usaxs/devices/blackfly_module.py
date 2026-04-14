"""
Point Grey BlackFly area detector support for the 12-ID-E USAXS instrument.

Provides two concrete detector classes built on ``MyPointGreyDetector``:

``MyPointGreyDetectorJPEG``
    Saves images as JPEG via the ``JPEG1:`` plugin.  File path and name are
    set by EPICS (``EpicsDefinesJpegFileNames``).
``MyPointGreyDetectorTIFF``
    Saves images as TIFF via the ``TIFF1:`` plugin.  File path and name are
    set by EPICS (``EpicsDefinesTiffFileNames``).

Both classes share ``image_prep()``, ``should_save_image``, and ``take_image()``
helpers.  The ``should_save_image`` property reads the
``usxLAX:saveFLY2Image`` PV to decide whether to acquire.
"""

import os
import warnings

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
    """Base PointGrey BlackFly detector used at 12-ID-E USAXS."""

    cam = ADComponent(PointGreyDetectorCam, "cam1:")
    image = ADComponent(ImagePlugin, "image1:")


class MyPointGreyDetectorJPEG(MyPointGreyDetector, AreaDetector):
    """BlackFly detector variant that saves images as JPEG.

    To save an image (using existing configuration)::

        blackfly_optical.stage()
        blackfly_optical.trigger()
        blackfly_optical.unstage()
    """

    jpeg1 = ADComponent(
        EpicsDefinesJpegFileNames,
        suffix="JPEG1:",
        root=DATABROKER_ROOT_PATH,
        write_path_template=WRITE_IMAGE_FILE_PATH,
        read_path_template=READ_IMAGE_FILE_PATH,
        kind="normal",
    )
    trans1 = ADComponent(TransformPlugin, "Trans1:")
    cc1 = ADComponent(ColorConvPlugin, "CC1:")
    proc1 = ADComponent(ProcessPlugin, "Proc1:")

    def __init__(self, *args, **kwargs):
        """Initialize; add ``jpeg1`` to read attrs and set capture mode."""
        super().__init__(*args, **kwargs)
        self.read_attrs.append("jpeg1")
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
        """Return the full path of the most-recently written JPEG file."""
        return self.jpeg1.full_file_name.get()

    def image_prep(self, path: str, filename_base: str, order_number: int):
        """Set file path, name, and number on the JPEG plugin.

        Parameters
        ----------
        path : str
            Directory path as seen by the host OS.  ``/mnt`` is prepended to
            convert it to the path seen by the IOC.  A trailing ``/`` is added
            automatically.
        filename_base : str
            Base name for the image file (without extension).
        order_number : int
            Sequential file number written into the AD filename template.

        Yields
        ------
        Bluesky messages.
        """
        plugin = self.jpeg1
        ioc_path = "/mnt" + os.path.abspath(path) + "/"  # MUST end with "/"
        # fmt: off
        yield from bps.mv(
            plugin.file_path,    ioc_path,
            plugin.file_name,    filename_base,
            plugin.file_number,  order_number,
        )
        # fmt: on

    @property
    def should_save_image(self) -> bool:
        """Return True if the ``usxLAX:saveFLY2Image`` PV is set to 1 / ``"Yes"``."""
        return _flag_save_sample_image_.get() in (1, "Yes")

    def take_image(self):
        """Stage, trigger (wait for completion), then unstage the detector.

        Yields
        ------
        Bluesky messages.
        """
        yield from bps.stage(self)
        yield from bps.trigger(self, wait=True)
        yield from bps.unstage(self)


class MyPointGreyDetectorTIFF(MyPointGreyDetector, AreaDetector):
    """BlackFly detector variant that saves images as TIFF.

    To save an image (using existing configuration)::

        blackfly_optical.stage()
        blackfly_optical.trigger()
        blackfly_optical.unstage()
    """

    tiff1 = ADComponent(
        EpicsDefinesTiffFileNames,
        suffix="TIFF1:",
        root=DATABROKER_ROOT_PATH,
        write_path_template=WRITE_IMAGE_FILE_PATH,
        read_path_template=READ_IMAGE_FILE_PATH,
        kind="normal",
    )

    @property
    def image_file_name(self) -> str:
        """Return the full path of the most-recently written TIFF file."""
        return self.tiff1.full_file_name.get()

    def image_prep(self, path: str, filename_base: str, order_number: int):
        """Set file path, name, and number on the TIFF plugin.

        Parameters
        ----------
        path : str
            Directory path as seen by the host OS.  ``/mnt`` is prepended to
            convert it to the path seen by the IOC.  A trailing ``/`` is added
            automatically.
        filename_base : str
            Base name for the image file (without extension).
        order_number : int
            Sequential file number written into the AD filename template.

        Yields
        ------
        Bluesky messages.
        """
        plugin = self.tiff1
        ioc_path = "/mnt" + os.path.abspath(path) + "/"  # MUST end with "/"
        # fmt: off
        yield from bps.mv(
            plugin.file_path,    ioc_path,
            plugin.file_name,    filename_base,
            plugin.file_number,  order_number,
        )
        # fmt: on

    @property
    def should_save_image(self) -> bool:
        """Return True if the ``usxLAX:saveFLY2Image`` PV is set to 1 / ``"Yes"``."""
        return _flag_save_sample_image_.get() in (1, "Yes")

    def take_image(self):
        """Stage, trigger (wait for completion), then unstage the detector.

        Yields
        ------
        Bluesky messages.
        """
        yield from bps.stage(self)
        yield from bps.trigger(self, wait=True)
        yield from bps.unstage(self)


_flag_save_sample_image_ = EpicsSignal(
    "usxLAX:saveFLY2Image",
    string=True,
    name="_flag_save_sample_image_",
)
