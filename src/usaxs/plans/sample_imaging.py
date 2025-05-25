"""
take an image of the sample
"""

import logging
import os
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from ..utils.setup_new_user import techniqueSubdirectory

logger = logging.getLogger(__name__)


# Device instances
blackfly_optical = oregistry["blackfly_optical"]
saxs_det = oregistry["saxs_det"]
terms = oregistry["terms"]
waxs_det = oregistry["waxs_det"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_device"]


def record_sample_image_on_demand(
    technique_name: str,
    filename_base: str,
    _md: Dict[str, Any],
):
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

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
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


def image_sample(
    count_time: float = 1.0,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """Image a sample using the detector.

    This function images a sample by setting up the detector and
    collecting data for a specified count time.

    Parameters
    ----------
    count_time : float, optional
        Count time in seconds, by default 1.0
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(image_sample(count_time=1.0))``
    """
    if md is None:
        md = {}


    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner():
        yield from user_data.set_state_plan("imaging sample")
        yield from bps.mv(scaler0.preset_time, count_time)
        yield from bps.trigger(scaler0, group="imaging")
        yield from bps.wait(group="imaging")

    return (yield from _inner())
