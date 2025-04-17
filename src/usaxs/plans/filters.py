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

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
Filter_AlTi = oregistry["Filter_AlTi"]
terms = oregistry["terms"]
monochromator = oregistry["monochromator"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


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


def insertScanFilters(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Insert filters for scanning.

    This function inserts the appropriate filters for scanning operations,
    configuring the instrument for optimal data collection.

    Parameters
    ----------
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

    USAGE:  ``RE(insertScanFilters())``
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

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from user_data.set_state_plan("inserting scan filters")
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="filters")
        yield from bps.wait(group="filters")

    return (yield from _inner())


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
