"""
Sample rotation plans for the PI C867 rotator stage.

Public entry points
-------------------
* ``PI_Off``         — stop rotation in either direction.
* ``PI_onF``         — start continuous rotation in the forward direction.
* ``PI_onR``         — start continuous rotation in the reverse direction.
* ``rotate_sample``  — move the rotator to a specific angle.
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)


# Device instances
pi_c867 = oregistry["pi_c867"]
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


def PI_Off(
    timeout: float = 1,
):
    """Bluesky plan: stop rotating the sample in either direction.

    .. note::
        Do NOT stop either jog by sending 1 to the motor ``.STOP`` field.
        That will result in a ``FailedStatus`` exception if the motor is
        in motion.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds for the move, by default 1.  Note: currently
        the timeout is hardcoded to 1 s internally regardless of this value.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
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
):
    """Bluesky plan: start rotating the sample in the forward direction.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds for the home move, by default 20.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from bps.mv(pi_c867.home, "forward", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_forward, 1)


def PI_onR(
    timeout: float = 20,
):
    """Bluesky plan: start rotating the sample in the reverse direction.

    Parameters
    ----------
    timeout : float, optional
        Timeout in seconds for the home move, by default 20.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from bps.mv(pi_c867.home, "reverse", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_reverse, 1)


def rotate_sample(
    angle: float,
    md=None,
):
    """Bluesky plan: rotate the sample to a specific angle and count.

    Moves the PI C867 rotator to *angle* and triggers a one-shot scaler
    count.  Intended as a utility for specialised sample-rotation setups.

    Parameters
    ----------
    angle : float
        Target rotation angle in degrees.
    md : dict, optional
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(rotate_sample(angle=45.0))``
    """
    _md = dict(md or {})

    @bpp.run_decorator(md=_md)
    def _inner():
        yield from user_data.set_state_plan(f"rotating sample to {angle} degrees")
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="rotation")
        yield from bps.wait(group="rotation")

    return (yield from _inner())
