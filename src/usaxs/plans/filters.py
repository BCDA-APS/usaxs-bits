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
from typing import Dict
from typing import Generator
from typing import Optional
from typing import Union

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)


def _insertFilters_(
    a: Union[int, float], oregistry: Optional[Dict[str, Any]] = None
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    a : Union[int, float]
        The filter position to set
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    Filter_AlTi = oregistry["Filter_AlTi"]

    yield from bps.mv(Filter_AlTi.fPos, int(a))
    yield from bps.sleep(0.5)  # allow all blades to re-position


def insertBlackflyFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    terms = oregistry["terms"]

    yield from _insertFilters_(
        terms.USAXS.blackfly.filters.Al.get(),  # Bank A: Al
        # terms.USAXS.blackfly.filters.Ti.get(),    # Bank B: Ti
        oregistry,
    )


def insertRadiographyFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    terms = oregistry["terms"]

    yield from _insertFilters_(
        terms.USAXS.img_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.img_filters.Ti.get(),    # Bank B: Ti
        oregistry,
    )


def insertSaxsFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    terms = oregistry["terms"]

    yield from _insertFilters_(
        terms.SAXS.filters.Al.get(),  # Bank A: Al
        # terms.SAXS.filters.Ti.get(),    # Bank B: Ti
        oregistry,
    )


def insertScanFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    terms = oregistry["terms"]

    yield from _insertFilters_(
        terms.USAXS.scan_filters.Al.get(),  # Bank A: Al
        # terms.USAXS.scan_filters.Ti.get(),    # Bank B: Ti
        oregistry,
    )


def insertWaxsFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: insert the EPICS-specified filters.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    terms = oregistry["terms"]

    yield from _insertFilters_(
        terms.WAXS.filters.Al.get(),  # Bank A: Al
        # terms.WAXS.filters.Ti.get(),    # Bank B: Ti
        oregistry,
    )


def insertTransmissionFilters(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set filters to reduce diode damage when measuring tranmission on guard slits etc.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    monochromator = oregistry["monochromator"]

    if monochromator.dcm.energy.position < 12.1:
        al_filters = 0
    elif monochromator.dcm.energy.position < 18.1:
        al_filters = 3
    else:
        al_filters = 7
    yield from _insertFilters_(al_filters, oregistry)
