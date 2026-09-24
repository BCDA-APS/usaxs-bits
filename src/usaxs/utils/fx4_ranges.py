"""
Parse FX4 range labels into a full-scale current.

The autoscale sanity check works in *fractions of full scale* rather than
absolute currents, so a change to the FX4's range table cannot silently
invalidate the thresholds.  That needs the full-scale value of whatever range
is active, and the only place it is available is the ``Range`` record's enum
label -- strings like ``"100 nA"`` or ``"10 mA"``.

.. warning::
   The exact label spelling has not been checked against the live IOC.  Get it
   with ``caget -d 31 usxFX4:FX4:Range``.  :func:`full_scale_pA` returns
   ``None`` rather than guessing when a label does not parse, and the caller
   then falls back to the absolute backstops.
"""

import logging
import re

logger = logging.getLogger(__name__)

_UNIT_TO_PICOAMPS = {
    "pa": 1.0,
    "na": 1.0e3,
    "ua": 1.0e6,
    "µa": 1.0e6,  # micro sign
    "μa": 1.0e6,  # Greek mu
    "ma": 1.0e9,
    "a": 1.0e12,
}

_LABEL = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Zµμ]+)\s*$")


def full_scale_pA(label):
    """Return the full-scale current of an FX4 range label, in pA.

    Parameters
    ----------
    label : str or None
        The ``Range`` enum string, e.g. ``"100 nA"``.

    Returns
    -------
    float or None
        Full scale in pA, or ``None`` if *label* could not be parsed.

    Examples
    --------
    >>> full_scale_pA("100 nA")
    100000.0
    >>> full_scale_pA("10 mA")
    10000000000.0
    >>> full_scale_pA("0.02 nA")
    20.0
    >>> full_scale_pA("fast 100 nA") is None
    True
    """
    if not label or not isinstance(label, str):
        return None
    match = _LABEL.match(label)
    if match is None:
        logger.debug("cannot parse FX4 range label %r", label)
        return None
    value, unit = match.groups()
    scale = _UNIT_TO_PICOAMPS.get(unit.lower())
    if scale is None:
        logger.debug("unknown current unit %r in FX4 range label %r", unit, label)
        return None
    return float(value) * scale
