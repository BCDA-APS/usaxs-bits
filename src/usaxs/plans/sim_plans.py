"""
Simulators from ophyd
=====================

For development and testing only, provides plans.

.. autosummary::
    ~sim_count_plan
    ~sim_print_plan
    ~sim_rel_scan_plan
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import plans as bp

logger = logging.getLogger(__name__)
logger.bsdev(__file__)

DEFAULT_MD = {"title": "test run with simulator(s)"}


def sim_count_plan(num: int = 1, imax: float = 10_000, md: dict = DEFAULT_MD):
    """Bluesky plan: demonstrate ``count()`` with the simulator detector.

    Parameters
    ----------
    num : int, optional
        Number of readings to take, by default 1.
    imax : float, optional
        Peak intensity for the simulated detector, by default 10 000.
    md : dict, optional
        Metadata for the run, by default ``DEFAULT_MD``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    logger.debug("sim_count_plan()")
    sim_det = oregistry["sim_det"]
    yield from bps.mv(sim_det.Imax, imax)
    yield from bp.count([sim_det], num=num, md=md)


def sim_print_plan():
    """Bluesky plan: print simulator motor and detector values (no data stream).

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    logger.debug("sim_print_plan()")
    yield from bps.null()
    sim_det = oregistry["sim_det"]
    sim_motor = oregistry["sim_motor"]
    print("sim_print_plan(): This is a test.")
    print(f"sim_print_plan():  {sim_motor.position=}  {sim_det.read()=}.")


def sim_rel_scan_plan(
    span: float = 5,
    num: int = 11,
    imax: float = 10_000,
    center: float = 0,
    sigma: float = 1,
    noise: str = "uniform",  # none poisson uniform
    md: dict = DEFAULT_MD,
):
    """Bluesky plan: demonstrate ``rel_scan()`` with the simulator devices.

    Parameters
    ----------
    span : float, optional
        Total scan range in motor units, by default 5.
    num : int, optional
        Number of scan points, by default 11.
    imax : float, optional
        Peak intensity for the simulated detector, by default 10 000.
    center : float, optional
        Peak centre position in motor units, by default 0.
    sigma : float, optional
        Peak width (Gaussian sigma) in motor units, by default 1.
    noise : str, optional
        Noise model: ``"none"``, ``"poisson"``, or ``"uniform"``,
        by default ``"uniform"``.
    md : dict, optional
        Metadata for the run, by default ``DEFAULT_MD``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    logger.debug("sim_rel_scan_plan()")
    sim_det = oregistry["sim_det"]
    sim_motor = oregistry["sim_motor"]
    # fmt: off
    yield from bps.mv(
        sim_det.Imax, imax,
        sim_det.center, center,
        sim_det.sigma, sigma,
        sim_det.noise, noise,
    )
    # fmt: on
    print(f"sim_rel_scan_plan(): {sim_motor.position=}.")
    print(f"sim_rel_scan_plan(): {sim_det.read()=}.")
    print(f"sim_rel_scan_plan(): {sim_det.read_configuration()=}.")
    print(f"sim_rel_scan_plan(): {sim_det.noise._enum_strs=}.")
    yield from bp.rel_scan([sim_det], sim_motor, -span / 2, span / 2, num=num, md=md)
