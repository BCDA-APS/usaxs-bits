"""
lup: lineup
"""

__all__ = [
    "lup",
]

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional

from bluesky import plan_stubs as bps
from bluesky import plans as bp
from ophyd import Device

logger = logging.getLogger(__name__)

logger.info(__file__)


def lup(
    detectors: List[Device],
    motor: Device,
    start: float,
    finish: float,
    npts: int = 5,
    key: str = "cen",
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Lineup a positioner.

    Step-scan the motor from start to finish and collect data from the detectors.
    The **first** detector in the list will be used to assess alignment.
    The statistical measure is selected by ``key`` with a default of
    center: ``key="cen"``.

    The bluesky ``BestEffortCallback``is required, with plots enabled, to
    collect the data for the statistical measure.

    If the chosen key is reported, the `lup()` plan will move the positioner to
    the new value at the end of the plan and print the new position.

    Parameters
    ----------
    detectors : List[Device]
        List of detectors to collect data from
    motor : Device
        The motor to scan
    start : float
        The starting position for the scan
    finish : float
        The ending position for the scan
    npts : int, optional
        Number of points to scan, by default 5
    key : str, optional
        The statistical measure to use, by default "cen"
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    det0 = detectors[0].name
    print(f"{det0=}")
    yield from bp.rel_scan(detectors, motor, start, finish, npts)

    yield from bps.sleep(1)

    bec = oregistry["bec"]
    if det0 in bec.peaks[key]:
        target = bec.peaks[key][det0]
        if isinstance(target, tuple):
            target = target[0]
        print(f"want to move {motor.name} to {target}")
        yield from bps.mv(motor, target)
        print(f"{motor.name}={motor.position}")
    else:
        print(f"'{det0}' not found in {bec.peaks[key]}")
