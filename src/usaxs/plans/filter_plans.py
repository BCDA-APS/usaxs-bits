"""
Beam-filter insertion plans for the 12-ID-E USAXS instrument.

Each public plan reads the appropriate EPICS PV for the desired Al filter
position and delegates to ``_insertFilters_``, which moves the ``Filter_AlTi``
device only if the position has changed and then waits 1.2 s for the blades
to settle.

Public entry points
-------------------
* ``insertBlackflyFilters``     — filters for Blackfly camera imaging.
* ``insertRadiographyFilters``  — filters for radiography mode.
* ``insertSaxsFilters``         — filters for SAXS measurements.
* ``insertScanFilters``         — filters for USAXS scanning.
* ``insertWaxsFilters``         — filters for WAXS measurements.
* ``insertTransmissionFilters`` — energy-dependent filters for transmission
                                   measurements (protects the diode).
"""

import logging

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
def _insertFilters_(a: int | float):
    """Plan (internal): move the Al/Ti filter bank to position *a*.

    A no-op if the filter is already at position *a*.  Otherwise moves
    ``Filter_AlTi.fPos`` and waits 1.2 s for all blades to re-settle.

    Parameters
    ----------
    a : int or float
        Target filter position index.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    current_filter = Filter_AlTi.fPos_RBV.get()
    if current_filter == a:
        return
    yield from bps.mv(Filter_AlTi.fPos, int(a))  # set filter position
    yield from bps.sleep(1.2)  # allow all blades to re-position


@plan
def insertBlackflyFilters():
    """Bluesky plan: insert filters for Blackfly camera imaging.

    Reads the Al filter position from ``terms.USAXS.blackfly.filters.Al``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(
        terms.USAXS.blackfly.filters.Al.get(),  # Bank A: Al
    )


@plan
def insertRadiographyFilters():
    """Bluesky plan: insert filters for radiography mode.

    Reads the Al filter position from ``terms.USAXS.img_filters.Al``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(
        terms.USAXS.img_filters.Al.get(),  # Bank A: Al
    )


@plan
def insertSaxsFilters():
    """Bluesky plan: insert filters for SAXS measurements.

    Reads the Al filter position from ``terms.SAXS.filters.Al``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(
        terms.SAXS.filters.Al.get(),  # Bank A: Al
    )


@plan
def insertScanFilters():
    """Bluesky plan: insert filters for USAXS scanning.

    Reads the Al filter position from ``terms.USAXS.scan_filters.Al``.

    USAGE:  ``RE(insertScanFilters())``

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(
        terms.USAXS.scan_filters.Al.get(),  # Bank A: Al
    )


@plan
def insertWaxsFilters():
    """Bluesky plan: insert filters for WAXS measurements.

    Reads the Al filter position from ``terms.WAXS.filters.Al``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(
        terms.WAXS.filters.Al.get(),  # Bank A: Al
    )


def insertTransmissionFilters():
    """Bluesky plan: insert energy-dependent filters for transmission measurements.

    Selects Al filter position based on monochromator energy to reduce diode
    damage when measuring transmission on guard slits:

    * energy < 12.1 keV  → position 0
    * 12.1 ≤ energy < 18.1 keV → position 3
    * energy ≥ 18.1 keV → position 7

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if monochromator.dcm.energy.position < 12.1:
        al_filters = 0
    elif monochromator.dcm.energy.position < 18.1:
        al_filters = 3
    else:
        al_filters = 7
    yield from _insertFilters_(al_filters)
