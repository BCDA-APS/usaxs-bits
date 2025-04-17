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
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.bsdev(__file__)

DEFAULT_MD = {"title": "test run with simulator(s)"}

# Device instances
sim_det = oregistry["sim_det"]
sim_motor = oregistry["sim_motor"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


def sim_count_plan(num: int = 1, imax: float = 10_000, md: dict = DEFAULT_MD):
    """Demonstrate the ``count()`` plan."""
    logger.debug("sim_count_plan()")
    yield from bps.mv(sim_det.Imax, imax)
    yield from bp.count([sim_det], num=num, md=md)


def sim_print_plan():
    """Demonstrate a ``print()`` plan stub (no data streams)."""
    logger.debug("sim_print_plan()")
    yield from bps.null()
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
    """Demonstrate the ``rel_scan()`` plan."""
    logger.debug("sim_rel_scan_plan()")
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


def sim_detector(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Simulate detector response.

    This function simulates a detector response by setting up a scaler
    and triggering it with a specified count time.

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

    USAGE:  ``RE(sim_detector())``
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
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="sim_detector")
        yield from bps.wait(group="sim_detector")

    return (yield from _inner())


def sim_motor(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Simulate motor movement.

    This function simulates a motor movement by setting up a motor
    and moving it to a specified position.

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

    USAGE:  ``RE(sim_motor())``
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
        yield from user_data.set_state_plan("simulating motor movement")
        yield from bps.sleep(1)  # Simulate motor movement time

    return (yield from _inner())
