"""Helper functions for the USAXS instrument.

This module provides various utility functions for controlling and managing
the USAXS instrument, including shutter control, temperature control, and
stage movement.
"""

import logging
import warnings

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry

logger = logging.getLogger(__name__)

# Device instances
aps = oregistry["aps"]
linkam_tc1 = oregistry["linkam_tc1"]
scaler0 = oregistry["scaler0"]
UPD_SIGNAL = oregistry["UPD_SIGNAL"]


def linkam_setup():
    """Set up the Linkam temperature controller.

    This function initializes the Linkam temperature controller, sets up
    tolerances, and configures engineering units.
    """
    linkam_tc1 = oregistry["linkam_tc1"]
    try:
        linkam_tc1.wait_for_connection()
    except Exception:
        warnings.warn(f"Linkam controller {linkam_tc1.name} not connected.")

    if linkam_tc1.connected:
        # set tolerance for "in position" (Python term, not an EPICS PV)
        # note: done = |readback - setpoint| <= tolerance
        linkam_tc1.temperature.tolerance.put(1.0)

        # sync the "inposition" computation
        linkam_tc1.temperature.cb_readback()

        # easy access to the engineering units
        linkam_tc1.units.put(linkam_tc1.temperature.readback.metadata["units"])
        linkam_tc1.ramp = linkam_tc1.ramprate
