"""
Start Bluesky Data Acquisition sessions of all kinds.

Includes:

* Python script
* IPython console
* Jupyter notebook
* Bluesky queueserver
"""

import logging
from pathlib import Path

from apsbits.core.best_effort_init import init_bec_peaks
from apsbits.core.catalog_init import init_catalog
from apsbits.core.instrument_init import make_devices
from apsbits.core.instrument_init import oregistry
from apsbits.core.run_engine_init import init_RE
from apsbits.utils.aps_functions import aps_dm_setup
from apsbits.utils.config_loaders import get_config
from apsbits.utils.config_loaders import load_config
from apsbits.utils.helper_functions import register_bluesky_magics
from apsbits.utils.helper_functions import running_in_queueserver

from usaxs.utils.scalers_setup import setup_scalers

logger = logging.getLogger(__name__)

# Get the path to the instrument package
instrument_path = Path(__file__).parent

# Load configuration to be used by the instrument.
iconfig_path = instrument_path / "configs" / "iconfig.yml"
load_config(iconfig_path)

# Get the configuration
iconfig = get_config()

logger.info("Starting Instrument with iconfig: %s", iconfig_path)

# Discard oregistry items loaded above.
oregistry.clear()

# Configure the session with callbacks, devices, and plans.
aps_dm_setup(iconfig.get("DM_SETUP_FILE"))

# Command-line tools, such as %wa, %ct, ...
register_bluesky_magics()

# Initialize core bluesky components
bec, peaks = init_bec_peaks(iconfig)
cat = init_catalog(iconfig)
RE, sd = init_RE(iconfig, bec_instance=bec, cat_instance=cat)

# Import optional components based on configuration
if iconfig.get("NEXUS_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.nexus_data_file_writer import nxwriter_init

    nxwriter = nxwriter_init(RE)

if iconfig.get("SPEC_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.spec_data_file_writer import init_specwriter_with_RE
    from .callbacks.spec_data_file_writer import newSpecFile  # noqa: F401
    from .callbacks.spec_data_file_writer import spec_comment  # noqa: F401
    from .callbacks.spec_data_file_writer import specwriter  # noqa: F401

    init_specwriter_with_RE(RE)

# These imports must come after the above setup.
if running_in_queueserver():
    ### To make all the standard plans available in QS, import by '*', otherwise import
    ### plan by plan.
    from apstools.plans import lineup2  # noqa: F401
    from bluesky.plans import *  # noqa: F403

else:
    # Import bluesky plans and stubs with prefixes set by common conventions.
    # The apstools plans and utils are imported by '*'.
    from apstools.plans import *  # noqa: F403
    from apstools.utils import *  # noqa: F403
    from bluesky import plan_stubs as bps  # noqa: F401
    from bluesky import plans as bp  # noqa: F401

### Load devices

RE(make_devices(file="scalers_and_amplifiers.yml", clear=False))
setup_scalers()


##operation variables
# in_operation = caget("usxLAX:blCalc:userCalc2.VAL") == 1  # should be a caget?
in_operation = True

RE(make_devices(file="devices.yml", clear=False))
RE(make_devices(file="devices_aps_only.yml", clear=False))
RE(make_devices(file="ad_devices.yml", clear=False))
RE(make_devices(file="autorange_devices.yml", clear=False))

if in_operation:
    RE(make_devices(file="shutters_op.yml", clear=False))
    from usaxs.suspenders.suspender_functions import suspender_in_operations

    suspend_FE_shutter, suspend_BeamInHutch = suspender_in_operations()

if not in_operation:
    RE(make_devices(file="shutters_sim.yml", clear=False))
    from usaxs.suspenders.suspender_functions import suspender_in_sim

    suspend_FE_shutter, suspend_BeamInHutch = suspender_in_sim()

### Baseline stream
# Beamline configuration stored before/after experiment
# uses baseline label to add to baseline data
if iconfig.get("BASELINE_LABEL", {}).get("ENABLE", False):
    _label = iconfig.get("BASELINE_LABEL", {}).get("LABEL", "baseline")
    logger.info(
        "Adding objects with %r label to 'baseline' stream.",
        _label,
    )
    try:
        sd.baseline.extend(oregistry.findall(_label, allow_none=True) or [])
    except Exception:
        logger.warning(
            "Could not add objects with %r label to 'baseline' stream",
            _label,
        )
    del _label


# flake8: noqa: F401, E402
"""Bluesky plans."""
from plans.amplifiers_plan import autoscale_amplifiers
from plans.area_detector_plans import areaDetectorAcquire
from plans.autocollect_plan import remote_ops

# these are all tuning plans facing users and staff
from plans.axis_tuning import tune_a2rp
from plans.axis_tuning import tune_ar
from plans.axis_tuning import tune_diode
from plans.axis_tuning import tune_dx
from plans.axis_tuning import tune_dy
from plans.axis_tuning import tune_mr
from plans.axis_tuning import tune_saxs_optics
from plans.axis_tuning import tune_usaxs_optics
from plans.command_list import run_command_file
from plans.command_list import sync_order_numbers
from plans.filter_plans import insertBlackflyFilters
from plans.filter_plans import insertRadiographyFilters
from plans.filter_plans import insertSaxsFilters
from plans.filter_plans import insertScanFilters
from plans.filter_plans import insertTransmissionFilters
from plans.filter_plans import insertWaxsFilters
from plans.mode_changes import mode_DirectBeam
from plans.mode_changes import mode_OpenBeamPath
from plans.mode_changes import mode_Radiography
from plans.mode_changes import mode_SAXS
from plans.mode_changes import mode_USAXS
from plans.mode_changes import mode_WAXS
from plans.mono_feedback import MONO_FEEDBACK_OFF
from plans.mono_feedback import MONO_FEEDBACK_ON
from plans.move_instrument import move_SAXSIn
from plans.move_instrument import move_SAXSOut
from plans.move_instrument import move_USAXSIn
from plans.move_instrument import move_USAXSOut
from plans.move_instrument import move_WAXSIn
from plans.move_instrument import move_WAXSOut
from plans.plans_tune import allUSAXStune
from plans.plans_tune import preSWAXStune
from plans.plans_tune import preUSAXStune
from plans.plans_usaxs import Flyscan
from plans.plans_usaxs import USAXSscan
from plans.plans_usaxs import USAXSscanStep
from plans.plans_user_facing import saxsExp
from plans.plans_user_facing import waxsExp
from plans.resets import reset_USAXS
from plans.sample_transmission import measure_USAXS_Transmission
from plans.sim_plans import sim_count_plan
from plans.sim_plans import sim_print_plan
from plans.sim_plans import sim_rel_scan_plan
from utils.setup_new_user import newUser

# customize the instrument configuration
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_shutter.delay_s = 0.01

print("You must now run newUser() first")
# newUser()
