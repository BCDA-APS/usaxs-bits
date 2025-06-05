"""
plans to control the beam filters
"""

import logging
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

from apsbits.core.instrument_init import oregistry
from apsbits.utils.config_loaders import get_config
from bluesky import plan_stubs as bps
from bluesky.utils import plan
from ophyd.scaler import ScalerCH

logger = logging.getLogger(__name__)


# Device instances
Filter_AlTi = oregistry["Filter_AlTi"]
terms = oregistry["terms"]
monochromator = oregistry["monochromator"]
user_data = oregistry["user_data"]

iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")

scaler0 = ScalerCH(scaler0_name, name="scaler0")
scaler0.stage_sigs["count_mode"] = "OneShot"
scaler0.select_channels()


@plan
def _insertFilters_(a: Union[int, float]):
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    a : Union[int, float]
        The filter position to set

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    current_filter = Filter_AlTi.fPos_RBV.get()
    if current_filter == a:
        # logger.info(f"Filter already set to {a}, no action taken.")
        return
    yield from bps.mv(Filter_AlTi.fPos, int(a))  # set filter position
    yield from bps.sleep(1.2)  # allow all blades to re-position


@plan
def insertBlackflyFilters():
    """
    Plan: insert the EPICS-specified filters.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.USAXS.blackfly.filters.Al.get(),  # Bank A: Al
        # terms.USAXS.blackfly.filters.Ti.get(),    # Bank B: Ti
    )


@plan
def insertRadiographyFilters():
    """
    Plan: insert the EPICS-specified filters.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.USAXS.img_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.img_filters.Ti.get(),    # Bank B: Ti
    )


@plan
def insertSaxsFilters():
    """
    Plan: insert the EPICS-specified filters.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.SAXS.filters.Al.get(),  # Bank A: Al
        # terms.SAXS.filters.Ti.get(),    # Bank B: Ti
    )


@plan
def insertScanFilters():
    """Insert the EPICS-specified filters for scanning.

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(insertScanFilters())``
    """
    yield from _insertFilters_(
        terms.USAXS.scan_filters.Al.get(),    # Bank A: Al
        #terms.USAXS.scan_filters.Ti.get(),    # Bank B: Ti
    )


@plan
def insertWaxsFilters():
    """
    Plan: insert the EPICS-specified filters.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.WAXS.filters.Al.get(),  # Bank A: Al
        # terms.WAXS.filters.Ti.get(),    # Bank B: Ti
    )


# def insertTransmissionFilters():
#     """
#     Set filters to reduce diode damage when measuring tranmission on guard slits etc.

#     Returns
#     -------
#     Generator[Any, None, None]
#         A generator that yields plan steps
#     """
#     yield from _insertFilters_(
#         terms.USAXS.transmission.filters.Al.get(),  # Bank A: Al
#         # terms.USAXS.transmission.filters.Ti.get(),    # Bank B: Ti
#     )


def insertTransmissionFilters():
    """
    set filters to reduce diode damage when measuring tranmission on guard slits etc
    """
    if monochromator.dcm.energy.position < 12.1:
        al_filters = 0
    elif monochromator.dcm.energy.position < 18.1:
        al_filters = 3
    else:
        al_filters = 7
    yield from _insertFilters_(al_filters)
