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
    """Bluesky plan: clear the filters for a transmission measurement.

    Historically this inserted energy-dependent Al attenuation (position 0,
    3 or 7 below 12.1 keV / below 18.1 keV / above) to protect the diode.
    That is no longer wanted, for two reasons:

    * the diodes carry their own metallic protective foils, so the Al was
      guarding against a hazard that no longer exists;
    * the filter box is a slow mechanical device.  Each change costs a move
      plus a 1.2 s settle, and attenuating the beam drives I0 down into a
      range change -- which is exactly what made I0 prone to bad ranges
      during transmission measurements at 12-ID-E.

    Removing the attenuation keeps I0 on one range across the measurement
    and lets the transmission count time come down (``TR_MeasurementTime``).

    The energy-dependent selection is kept in the history rather than the
    code; restoring it means reinstating the three-way branch on
    ``monochromator.dcm.energy.position``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from _insertFilters_(0)
