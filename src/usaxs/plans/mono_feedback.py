"""Monochromator feedback plans for the USAXS instrument.

This module provides plans for controlling the monochromator feedback
system, including enabling and disabling feedback loops.
"""

__all__ = [
    "DCMfeedbackOFF",
    "DCMfeedbackON",
]

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

# Constants
MONO_FEEDBACK_OFF = oregistry["MONO_FEEDBACK_OFF"]
MONO_FEEDBACK_ON = oregistry["MONO_FEEDBACK_ON"]

# Device instances
monochromator = oregistry["monochromator"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


def DCMfeedbackOFF() -> Generator[Any, None, None]:
    """
    Plan: turn off monochromator feedback.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_OFF)


def DCMfeedbackON(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Enable the monochromator feedback loop.

    This function enables the feedback loop for the double crystal
    monochromator to maintain optimal performance.

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

    USAGE:  ``RE(DCMfeedbackON())``
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
        yield from user_data.set_state_plan("enabling monochromator feedback")
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="feedback")
        yield from bps.wait(group="feedback")

    return (yield from _inner())
