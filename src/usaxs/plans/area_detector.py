"""Area detector plans for the USAXS instrument.

This module provides plans for controlling area detectors in the USAXS instrument,
including configuration, acquisition, and data collection.
"""

__all__ = [
    "areaDetectorAcquire",
]

import logging
import time
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky import plans as bp

from ..utils.reporter import remaining_time_reporter

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
user_data = oregistry["user_data"]


def areaDetectorAcquire(
    det: Any,
    create_directory: Optional[str] = None,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Acquire image(s) from the named area detector.

    This function configures and acquires images from a specified area detector,
    including setting up the acquisition parameters, creating output directories,
    and handling the data collection process.

    Parameters
    ----------
    det : Any
        The area detector to acquire from
    create_directory : Optional[str], optional
        Directory to create for the data, by default None
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

    USAGE:  ``RE(areaDetectorAcquire(det))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})
    acquire_time = det.cam.acquire_time.get()
    # Note: AD's HDF File Writer can use up to 5 seconds to finish writing the file

    t0 = time.time()
    yield from bps.mv(
        user_data.scanning,
        "scanning",  # we are scanning now (or will be very soon)
    )
    logger.debug(f"areaDetectorAcquire(): {det.hdf1.stage_sigs}")
    _md["method"] = "areaDetectorAcquire"
    _md["area_detector_name"] = det.name
    if _md.get("plan_name") is None:
        _md["plan_name"] = "image"

    if RE.state != "idle":
        remaining_time_reporter(_md["plan_name"], acquire_time)

    if create_directory is not None:
        yield from bps.mv(det.hdf1.create_directory, create_directory)

    if det.cam.num_images.get() > 1:
        image_mode = "Multiple"
    else:
        image_mode = "Single"
    det.cam.stage_sigs["image_mode"] = image_mode

    # Remember what we've got now and reset it after the bp.count().
    original_detector_staging = dict(cam=det.cam.stage_sigs.copy())
    # Since we have set certain detector parameters in EPICS,
    # make sure they are not staged (to something different).
    # Turns out this is an optimization for the Pilatus
    # since making a significant change (~0.001 or greater)
    # in acquire_time takes ~0.5s for camera to complete.
    for k in "acquire_time acquire_period".split():
        if k in det.cam.stage_sigs:
            # print(f"Removing {det.cam.name}.stage_sigs[{k}] before bp.count()")
            det.cam.stage_sigs.pop(k)

    if bec is not None:
        bec.disable_table()
    yield from bp.count(
        [det], md=_md
    )  # TODO: SPEC showed users incremental progress (1 Hz updates) #175
    if bec is not None:
        bec.enable_table()

    # Restore the original detector staging.
    det.cam.stage_sigs = original_detector_staging["cam"].copy()

    yield from bps.mv(
        user_data.scanning,
        "no",
    )  # we are done
    elapsed = time.time() - t0
    logger.info(f"Finished SAXS/WAXS data collection in {elapsed} seconds.")
