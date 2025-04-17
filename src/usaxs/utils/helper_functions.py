"""Helper functions for the USAXS instrument.

This module provides various utility functions for controlling and managing
the USAXS instrument, including shutter control, temperature control, and
stage movement.
"""

import logging
import time
import warnings
from collections import OrderedDict
from typing import Any
from typing import Generator
from typing import List
from typing import Optional

import numpy as np

# Get devices from oregistry
from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from ophyd import EpicsSignal
from ophyd import Signal
from ophyd.device import Kind
from ophyd.scaler import EpicsScaler
from ophyd.signal import EpicsSignalRO

from ..devices import AMPLIFIER_MINIMUM_SETTLING_TIME
from ..devices import NUM_AUTORANGE_GAINS
from ..devices import AutorangeSettings
from ..devices import AutoscaleError
from ..devices import DetectorAmplifierAutorangeDevice
from ..devices.general_terms import terms
from ..devices.shutters import ApsPssShutter
from ..devices.shutters import ApsPssShutterWithStatus
from ..devices.shutters import My12IdPssShutter
from ..devices.shutters import SimulatedApsPssShutterWithStatus
from ..devices.stages import a_stage
from ..devices import ScalerCH
from ..devices import ScalerChannel
from ..devices import upd_controls
from ..suspenders import usaxs_q_calc

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
