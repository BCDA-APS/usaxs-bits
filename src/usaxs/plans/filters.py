"""
plans to control the beam filters
"""

__all__ = """
    insertBlackflyFilters
    insertRadiographyFilters
    insertSaxsFilters
    insertScanFilters
    insertTransmissionFilters
    insertWaxsFilters
""".split()

import logging
from typing import Any
from typing import Generator
from typing import Union

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
Filter_AlTi = oregistry["Filter_AlTi"]
terms = oregistry["terms"]
monochromator = oregistry["monochromator"]


def _insertFilters_(a: Union[int, float]) -> Generator[Any, None, None]:
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
    yield from bps.mv(Filter_AlTi.fPos, int(a))
    yield from bps.sleep(0.5)  # allow all blades to re-position


def insertBlackflyFilters() -> Generator[Any, None, None]:
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


def insertRadiographyFilters() -> Generator[Any, None, None]:
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


def insertSaxsFilters() -> Generator[Any, None, None]:
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


def insertScanFilters() -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.USAXS.scan_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.scan_filters.Ti.get(),    # Bank B: Ti
    )


def insertWaxsFilters() -> Generator[Any, None, None]:
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


def insertTransmissionFilters() -> Generator[Any, None, None]:
    """
    Set filters to reduce diode damage when measuring tranmission on guard slits etc.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from _insertFilters_(
        terms.USAXS.transmission.filters.Al.get(),  # Bank A: Al
        # terms.USAXS.transmission.filters.Ti.get(),    # Bank B: Ti
    )
