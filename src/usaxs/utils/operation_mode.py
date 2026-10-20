"""
Decide whether the instrument runs against hardware or against simulations.

``startup.py`` picks between ``shutters_op.yml`` and ``shutters_sim.yml`` -- and
between the real and the inert beam suspenders -- from one PV,
``usxLAX:blCalc:userCalc2.VAL`` (``BlueSkyEnable``).  That decision used to be::

    in_operation = caget("usxLAX:blCalc:userCalc2.VAL") == 1

``caget()`` returns ``None`` when the PV does not connect in time, and
``None == 1`` is ``False``, so a slow or absent ``iocusxlax`` silently selected
*simulation*.  The failure is invisible afterwards: ``usaxs_shutter`` becomes a
``SimulatedApsPssShutterWithStatus`` whose ``set("open")`` completes normally
without touching a PV, and the suspenders become ``SuspendBoolHigh`` objects
watching a soft ``Signal`` that is never set.  A tune then runs to completion
against a closed shutter and a dead beam, reports a failed fit, and nothing in
the output says why.  That cost a shift on 2026-10-19.

So: *unknown* must never mean *simulated*.  This module reads the PV with a
real connection timeout and retries, raises :class:`OperationModeUnknown` if it
still cannot be read, and provides the banner that states which mode was
chosen.  Deliberate simulation is available, but only by asking for it --
see :data:`OVERRIDE_ENV`.
"""

import logging
import os

from epics import PV

logger = logging.getLogger(__name__)

BL_ENABLE_PV = "usxLAX:blCalc:userCalc2.VAL"
"""PV that enables Bluesky operations.  ``DESC`` is ``BlueSkyEnable``."""

OVERRIDE_ENV = "USAXS_SIMULATE"
"""Environment variable that overrides the PV.

``1``/``true``/``yes``/``on``/``sim`` select simulation;
``0``/``false``/``no``/``off``/``ops`` force operations.  Unset means "ask the
PV", which is the normal case.
"""

CONNECTION_TIMEOUT = 10.0
"""Seconds to wait for the PV to connect, per attempt.

Generous on purpose.  This runs during startup, when the CA context has just
been created and the repeater may still be coming up; a 1--2 s timeout is the
kind of margin that turns a slow network into a silently simulated beamline.
"""

READ_TIMEOUT = 5.0
"""Seconds to wait for the value once the PV has connected."""

ATTEMPTS = 3
"""How many times to try connecting before giving up."""

_TRUE_WORDS = frozenset({"1", "true", "yes", "on", "sim", "simulate", "simulation"})
_FALSE_WORDS = frozenset({"0", "false", "no", "off", "ops", "operation", "operations"})


class OperationModeUnknown(RuntimeError):
    """Raised when operations-vs-simulation cannot be determined.

    Deliberately fatal.  The alternative -- guessing -- is what this module
    exists to prevent.
    """


def _override():
    """Return the forced mode as ``in_operation``, or ``None`` if unset.

    Returns
    -------
    bool or None
        ``True`` to force operations, ``False`` to force simulation, ``None``
        when :data:`OVERRIDE_ENV` is not set.

    Raises
    ------
    OperationModeUnknown
        If the variable is set to something unrecognised.  An unparseable
        override is an unknown mode, not a reason to fall back.
    """
    raw = os.environ.get(OVERRIDE_ENV)
    if raw is None:
        return None

    word = raw.strip().lower()
    if word in _TRUE_WORDS:
        return False  # simulate -> not in operation
    if word in _FALSE_WORDS:
        return True
    raise OperationModeUnknown(
        f"{OVERRIDE_ENV}={raw!r} is not recognised."
        f"  Use one of {sorted(_TRUE_WORDS)} to simulate,"
        f" or one of {sorted(_FALSE_WORDS)} to force operations,"
        f" or unset it to read {BL_ENABLE_PV}."
    )


def _read_enable_pv(pvname, attempts, connection_timeout, read_timeout):
    """Read *pvname*, retrying the connection.

    Parameters
    ----------
    pvname : str
        PV to read.
    attempts : int
        How many connection attempts to make.
    connection_timeout : float
        Seconds to wait for connection, per attempt.
    read_timeout : float
        Seconds to wait for the value once connected.

    Returns
    -------
    float or None
        The value, or ``None`` if it could not be read.
    """
    pv = PV(pvname, connection_timeout=connection_timeout)
    for attempt in range(1, attempts + 1):
        if pv.wait_for_connection(timeout=connection_timeout):
            # use_monitor=False: this is the first read of the session and the
            # answer decides whether the shutters are real.  Do not accept a
            # cached value.
            value = pv.get(timeout=read_timeout, use_monitor=False)
            if value is not None:
                return value
            logger.warning(
                "%s connected but returned no value (attempt %d of %d)",
                pvname,
                attempt,
                attempts,
            )
        else:
            logger.warning(
                "%s did not connect within %g s (attempt %d of %d)",
                pvname,
                connection_timeout,
                attempt,
                attempts,
            )
    return None


def determine_in_operation(
    pvname=BL_ENABLE_PV,
    attempts=ATTEMPTS,
    connection_timeout=CONNECTION_TIMEOUT,
    read_timeout=READ_TIMEOUT,
):
    """Decide whether to load real hardware or simulations.

    Parameters
    ----------
    pvname : str, optional
        PV to consult.  Defaults to :data:`BL_ENABLE_PV`.
    attempts : int, optional
        Connection attempts before giving up.  Defaults to :data:`ATTEMPTS`.
    connection_timeout : float, optional
        Seconds per connection attempt.  Defaults to
        :data:`CONNECTION_TIMEOUT`.
    read_timeout : float, optional
        Seconds to wait for the value.  Defaults to :data:`READ_TIMEOUT`.

    Returns
    -------
    tuple[bool, str]
        ``(in_operation, reason)``.  *reason* is a short human-readable phrase
        naming what the decision was based on, for the banner and the log.

    Raises
    ------
    OperationModeUnknown
        If the PV cannot be read and no override is set.
    """
    forced = _override()
    if forced is not None:
        reason = f"{OVERRIDE_ENV}={os.environ[OVERRIDE_ENV]!r} (PV not consulted)"
        logger.warning("operation mode forced by environment: %s", reason)
        return forced, reason

    value = _read_enable_pv(pvname, attempts, connection_timeout, read_timeout)
    if value is None:
        raise OperationModeUnknown(
            f"Could not read the BlueSkyEnable flag {pvname}"
            f" in {attempts} attempts.\n"
            "\n"
            "Refusing to start.  An unreadable PV must not select simulation:\n"
            "that silently replaces usaxs_shutter, mono_shutter and FE_shutter\n"
            "with stand-ins that move nothing, and the beam suspenders with\n"
            "inert ones, so scans run to completion with no beam and no error.\n"
            "\n"
            "Check that iocusxlax is running and reachable, then start again.\n"
            "To start without it, say so explicitly:\n"
            f"    {OVERRIDE_ENV}=1 ./scripts/start-usaxs-bits.sh   # simulate\n"
            f"    {OVERRIDE_ENV}=0 ./scripts/start-usaxs-bits.sh   # force ops"
        )

    return value == 1, f"{pvname} = {value}"


def operation_mode_banner(in_operation, reason):
    """Return the startup banner announcing the selected mode.

    Printed at the *end* of startup, after the device-creation chatter, so it
    is the last thing on screen rather than a ``logger.info`` line a thousand
    lines up.

    Parameters
    ----------
    in_operation : bool
        The decision from :func:`determine_in_operation`.
    reason : str
        What that decision was based on.

    Returns
    -------
    str
        The banner, ready to ``print()``.
    """
    rule = "=" * 72
    if in_operation:
        body = [
            "  USAXS instrument mode:  OPERATIONS",
            f"  based on: {reason}",
            "",
            "  Real shutters and real beam suspenders are loaded.",
        ]
    else:
        body = [
            "  ***  USAXS instrument mode:  SIMULATION  ***",
            f"  based on: {reason}",
            "",
            "  usaxs_shutter, mono_shutter and FE_shutter are SIMULATED.",
            "  No shutter will move; no beam will reach the diode.",
            "  The beam suspenders are inert: scans will NOT pause on",
            "  beam loss, they will run to the end and fit noise.",
            "",
            f"  To run against hardware: set {BL_ENABLE_PV}",
            f"  (BlueSkyEnable) to 1, clear {OVERRIDE_ENV}, and restart.",
        ]
    return "\n".join([rule, *body, rule])
