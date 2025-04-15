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

from bluesky import plan_stubs as bps

from ..devices.filters import Filter_AlTi
from ..devices.general_terms import terms
from ..devices.monochromator import monochromator

logger = logging.getLogger(__name__)
logger.info(__file__)


def _insertFilters_(a: Union[int, float]) -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from bps.mv(Filter_AlTi.fPos, int(a))
    yield from bps.sleep(0.5)  # allow all blades to re-position


def insertBlackflyFilters() -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from _insertFilters_(
        terms.USAXS.blackfly.filters.Al.get(),  # Bank A: Al
        # terms.USAXS.blackfly.filters.Ti.get(),    # Bank B: Ti
    )


def insertRadiographyFilters() -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from _insertFilters_(
        terms.USAXS.img_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.img_filters.Ti.get(),    # Bank B: Ti
    )


def insertSaxsFilters() -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from _insertFilters_(
        terms.SAXS.filters.Al.get(),  # Bank A: Al
        # terms.SAXS.filters.Ti.get(),    # Bank B: Ti
    )


def insertScanFilters() -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from _insertFilters_(
        terms.USAXS.scan_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.scan_filters.Ti.get(),    # Bank B: Ti
    )


def insertWaxsFilters() -> Generator[Any, None, None]:
    """plan: insert the EPICS-specified filters"""
    yield from _insertFilters_(
        terms.WAXS.filters.Al.get(),  # Bank A: Al
        # terms.WAXS.filters.Ti.get(),    # Bank B: Ti
    )


def insertTransmissionFilters() -> Generator[Any, None, None]:
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
