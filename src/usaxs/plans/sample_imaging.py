"""
take an image of the sample
"""

__all__ = [
    "record_sample_image_on_demand",
]

import logging
import os
from typing import Any
from typing import Dict
from typing import Generator

from bluesky import plan_stubs as bps

from ..utils.setup_new_user import techniqueSubdirectory

logger = logging.getLogger(__name__)
logger.info(__file__)


def record_sample_image_on_demand(
    technique_name: str,
    filename_base: str,
    _md: Dict[str, Any],
    oregistry: Dict[str, Any] = None,
) -> Generator[Any, None, None]:
    """
    take an image of the sample

    If a sample image is taken, the full path to the image
    is added to the (RunEngine) metadata.

    Parameters
    ----------
    technique_name : str
        Used to pick the subdirectory. One of "saxs", "usaxs", or "waxs"
    filename_base : str
        Base part of image file name
    _md : Dict[str, Any]
        Metadata dictionary additions from the calling plan
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    blackfly_optical = oregistry["blackfly_optical"]
    saxs_det = oregistry["saxs_det"]
    terms = oregistry["terms"]
    waxs_det = oregistry["waxs_det"]

    if blackfly_optical is not None and blackfly_optical.should_save_image:
        det = blackfly_optical  # define once here, in case it ever changes
        path = techniqueSubdirectory(technique_name)

        xref = dict(
            usaxs=terms.FlyScan.order_number,
            saxs=saxs_det.hdf1.file_number,
            waxs=waxs_det.hdf1.file_number,
        )
        order_number = xref.get(technique_name, xref["usaxs"]).get()

        try:
            yield from det.image_prep(path, filename_base, order_number)
            yield from bps.sleep(
                0.1
            )  # avoid timeouts when staging, guess that this fixes it
            yield from det.take_image()

            image_name = det.image_file_name
            if image_name.startswith("/mnt/share1"):
                image_name = image_name[4:]
            if os.path.exists(image_name):
                # update the provided dictionary
                _md["sample_image_name"] = image_name
                logger.info("sample image file: %s", image_name)
        except Exception as exc:
            logger.warning(
                ("Could not take sample image:" "path=%s, file=%s, order#=%d, exc=%s"),
                path,
                filename_base,
                order_number,
                exc,
            )
    else:
        yield from bps.null()
