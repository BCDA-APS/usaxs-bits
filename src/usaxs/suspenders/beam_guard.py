"""
Late-binding beam suspender guard for USAXS data-collection plans.

Why this exists
---------------
The beam suspenders cannot be referenced by a plan module at import time:
they do not exist until ``startup.py`` has read ``usxLAX:blCalc:userCalc2``
and chosen between ``suspender_in_operations()`` and ``suspender_in_sim()``.
Writing ``@bpp.suspend_decorator(suspend_BeamInHutch)`` above a plan is
therefore impossible without a back-edge into ``usaxs.startup``, which is
forbidden (see CLAUDE.md, "No back-edges into ``usaxs.startup``").

The previous workaround applied the decorators in ``startup.py`` by rebinding
names::

    USAXSscan = bpp.suspend_decorator(suspend_BeamInHutch)(USAXSscan)

That rebinds the name only inside the ``usaxs.startup`` namespace.  User
scripts and ``command_list.py`` do ``from usaxs.plans.plans_usaxs import
USAXSscan``, which binds the *undecorated* original — so scans launched from
a script or a command file ran with no suspenders at all.

``beam_guarded`` solves this by resolving the suspenders **at call time**
instead of at decoration time.  Plans can then be decorated at their
definition sites, so the guard travels with the function object through any
import path.

Usage
-----
In a plan module (no dependency on ``usaxs.startup``)::

    from usaxs.suspenders.beam_guard import beam_guarded

    @plan
    @beam_guarded
    def Flyscan(...):
        ...

Keep ``@plan`` outermost so ``bluesky.utils.Plan`` behaviour is unchanged.

In ``startup.py``, once the suspenders exist::

    set_beam_suspenders(suspend_FE_shutter, suspend_BeamInHutch)

Only data-collection plans should carry ``@beam_guarded``.  The suspenders are
deliberately *not* installed on the RunEngine globally: that blocks all staff
operations whenever there is no beam.

Do not nest guarded plans.  Installing the same suspender twice and then
removing it once leaves the outer scope unguarded, because the inner
``remove_suspender`` discards it from ``RE._suspenders``.
"""

import functools
import logging

from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)

# Populated once by startup.py.  Empty means "not armed" — guarded plans then
# run unguarded (bare imports, unit tests, any session that never ran startup).
_beam_suspenders = []


def set_beam_suspenders(*suspenders) -> None:
    """Register the suspenders that :func:`beam_guarded` installs.

    Called once from ``startup.py`` after the operations/sim decision has been
    made.  Replaces any previously registered suspenders.

    Parameters
    ----------
    *suspenders
        ``bluesky.suspenders`` instances, e.g. ``suspend_FE_shutter`` and
        ``suspend_BeamInHutch``.  Call with no arguments to disarm.
    """
    _beam_suspenders.clear()
    _beam_suspenders.extend(suspenders)
    logger.info(
        "Beam guard armed with %d suspender(s) for data-collection plans.",
        len(_beam_suspenders),
    )


def beam_guarded(plan_func):
    """Decorator: install the registered beam suspenders for the plan's duration.

    The suspenders are looked up when the plan is *called*, not when it is
    decorated, so this works at module-import time before the suspenders
    exist.  If none are registered the plan runs unguarded.

    Parameters
    ----------
    plan_func : callable
        A Bluesky plan (generator function).

    Returns
    -------
    callable
        Generator function yielding the plan's messages bracketed by
        ``install_suspender`` / ``remove_suspender`` messages.  The plan's
        return value is preserved.
    """

    @functools.wraps(plan_func)
    def wrapper(*args, **kwargs):
        inner = plan_func(*args, **kwargs)
        if not _beam_suspenders:
            logger.debug(
                "Beam guard not armed; %s runs unguarded.", plan_func.__name__
            )
            return (yield from inner)
        return (yield from bpp.suspend_wrapper(inner, list(_beam_suspenders)))

    return wrapper
