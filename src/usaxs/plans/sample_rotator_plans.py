"""
rotate the sample with PI C867 motor
"""

__all__ = """
    PI_Off
    PI_onF
    PI_onR
""".split()

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
pi_c867 = oregistry["pi_c867"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


def PI_Off(
    timeout: float = 1,
) -> Generator[Any, None, None]:
    """
    Plan: stop rotating sample in either direction.

    NOTE:
        Do NOT stop either jog by sending 1 to the
        motor `.STOP` field.  That will result in a
        `FailedStatus` exception if the motor is
        in motion.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds, by default 1

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(
        pi_c867.jog_forward,
        0,
        pi_c867.jog_reverse,
        0,
        timeout=1,
    )


def PI_onF(
    timeout: float = 20,
) -> Generator[Any, None, None]:
    """
    Plan: start rotating sample in forward direction.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds, by default 20

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(pi_c867.home, "forward", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_forward, 1)


def PI_onR(
    timeout: float = 20,
) -> Generator[Any, None, None]:
    """
    Plan: start rotating sample in reverse direction.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds, by default 20

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(pi_c867.home, "reverse", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_reverse, 1)


def rotate_sample(
    angle: float,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Rotate sample to a specific angle.

    This function rotates the sample to a specified angle and optionally
    measures the intensity at that position.

    Parameters
    ----------
    angle : float
        Target angle in degrees
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

    USAGE:  ``RE(rotate_sample(angle=45.0))``
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
        yield from user_data.set_state_plan(f"rotating sample to {angle} degrees")
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="rotation")
        yield from bps.wait(group="rotation")

    return (yield from _inner())
