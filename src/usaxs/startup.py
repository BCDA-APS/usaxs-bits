"""
Start Bluesky Data Acquisition sessions of all kinds.

Includes:

* Python script
* IPython console
* Jupyter notebook
* Bluesky queueserver
"""

# Standard Library Imports
import logging
from pathlib import Path

# Core Functions
from tiled.client import from_profile

from apsbits.core.best_effort_init import init_bec_peaks
from apsbits.core.catalog_init import init_catalog
from apsbits.core.instrument_init import init_instrument
from apsbits.core.instrument_init import make_devices
from apsbits.core.run_engine_init import init_RE

# Utility functions
from apsbits.utils.aps_functions import host_on_aps_subnet
from apsbits.utils.baseline_setup import setup_baseline_stream

# Configuration functions
from apsbits.utils.config_loaders import load_config
from apsbits.utils.helper_functions import register_bluesky_magics
from apsbits.utils.helper_functions import running_in_queueserver
from apsbits.utils.logging_setup import configure_logging
from epics import caget

from usaxs.utils.scalers_setup import setup_scalers

# Configuration block
# Get the path to the instrument package
# Load configuration to be used by the instrument.
instrument_path = Path(__file__).parent
iconfig_path = instrument_path / "configs" / "iconfig.yml"
iconfig = load_config(iconfig_path)

# # Additional logging configuration
# # Only needed if using logging setup differs from apsbits package.
# # If so, copy 'extra_logging.yml' from apsbits and modify locally.
# extra_logging_configs_path = instrument_path / "configs" / "extra_logging.yml"
# configure_logging(extra_logging_configs_path=extra_logging_configs_path)


logger = logging.getLogger(__name__)
logger.info("Starting Instrument with iconfig: %s", iconfig_path)

# initialize instrument
instrument, oregistry = init_instrument("guarneri")

# Discard oregistry items loaded above.
oregistry.clear()

# Configure the session with callbacks, devices, and plans.
# aps_dm_setup(iconfig.get("DM_SETUP_FILE"))

# Command-line tools, such as %wa, %ct, ...
register_bluesky_magics()

# Bluesky initialization block

if iconfig.get("TILED_PROFILE_NAME", {}):
    profile_name = iconfig.get("TILED_PROFILE_NAME")
    tiled_client = from_profile(profile_name)

bec, peaks = init_bec_peaks(iconfig)
cat = init_catalog(iconfig)
RE, sd = init_RE(iconfig, subscribers=[bec, cat])

# Optional Nexus callback block
# delete this block if not using Nexus
if iconfig.get("NEXUS_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.demo_nexus_callback import nxwriter_init

    nxwriter = nxwriter_init(RE)

# Optional SPEC callback block
# delete this block if not using SPEC
if iconfig.get("SPEC_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.demo_spec_callback import init_specwriter_with_RE
    from .callbacks.demo_spec_callback import newSpecFile  # noqa: F401
    from .callbacks.demo_spec_callback import spec_comment  # noqa: F401
    from .callbacks.demo_spec_callback import specwriter  # noqa: F401

    init_specwriter_with_RE(RE)

# These imports must come after the above setup.
# Queue server block
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

# Experiment specific logic, device and plan loading. # Create the devices.
make_devices(clear=False, file="scalers_and_amplifiers.yml", device_manager=instrument)
setup_scalers(oregistry)

make_devices(file="devices.yml", clear=False, device_manager=instrument)
make_devices(file="devices_aps_only.yml", clear=False, device_manager=instrument)
make_devices(file="ad_devices.yml", clear=False, device_manager=instrument)
make_devices(file="autorange_devices.yml", clear=False, device_manager=instrument)

##operation variables
in_operation = caget("usxLAX:blCalc:userCalc2.VAL") == 1
# in_operation = True
logger.info("in operation = " + str(in_operation))

if in_operation:
    make_devices(file="shutters_op.yml", clear=False, device_manager=instrument)
    from usaxs.suspenders.suspender_functions import suspender_in_operations

    suspend_FE_shutter, suspend_BeamInHutch = suspender_in_operations()

else:   # if not in_operation:
    make_devices(file="shutters_sim.yml", clear=False, device_manager=instrument)
    from usaxs.suspenders.suspender_functions import suspender_in_sim

    suspend_FE_shutter, suspend_BeamInHutch = suspender_in_sim()

# Setup baseline stream with connect=False is default
# Devices with the label 'baseline' will be added to the baseline stream.
setup_baseline_stream(sd, oregistry, connect=False)

# from .plans.sim_plans import sim_count_plan  # noqa: E402, F401
# from .plans.sim_plans import sim_print_plan  # noqa: E402, F401
# from .plans.sim_plans import sim_rel_scan_plan  # noqa: E402, F401


# flake8: noqa: F401, E402
"""Bluesky .plans."""
from .plans.amplifiers_plan import autoscale_amplifiers
from .plans.area_detector_plans import areaDetectorAcquire
from .plans.autocollect_plan import remote_ops

# these are all tuning plans facing users and staff
from .plans.axis_tuning import tune_a2rp
from .plans.axis_tuning import find_a2rp
from .plans.axis_tuning import tune_ar
from .plans.axis_tuning import find_ar
from .plans.axis_tuning import tune_diode
from .plans.axis_tuning import tune_dx
from .plans.axis_tuning import tune_dy
from .plans.axis_tuning import tune_mr
from .plans.axis_tuning import tune_saxs_optics
from .plans.axis_tuning import tune_usaxs_optics
from .plans.command_list import run_command_file
from .plans.command_list import sync_order_numbers
from .plans.filter_plans import insertBlackflyFilters
from .plans.filter_plans import insertRadiographyFilters
from .plans.filter_plans import insertSaxsFilters
from .plans.filter_plans import insertScanFilters
from .plans.filter_plans import insertTransmissionFilters
from .plans.filter_plans import insertWaxsFilters
from .plans.mode_changes import mode_DirectBeam
from .plans.mode_changes import mode_OpenBeamPath
from .plans.mode_changes import mode_Radiography
from .plans.mode_changes import mode_SAXS
from .plans.mode_changes import mode_USAXS
from .plans.mode_changes import mode_WAXS
from .plans.mono_feedback import MONO_FEEDBACK_OFF
from .plans.mono_feedback import MONO_FEEDBACK_ON
from .plans.move_instrument import move_SAXSIn
from .plans.move_instrument import move_SAXSOut
from .plans.move_instrument import move_USAXSIn
from .plans.move_instrument import move_USAXSOut
from .plans.move_instrument import move_WAXSIn
from .plans.move_instrument import move_WAXSOut
from .plans.plans_tune import allUSAXStune
from .plans.plans_tune import preSWAXStune
from .plans.plans_tune import preUSAXStune
from .plans.plans_usaxs import Flyscan
from .plans.plans_usaxs import USAXSscan
from .plans.plans_usaxs import USAXSscanStep
from .plans.plans_user_facing import saxsExp
from .plans.plans_user_facing import waxsExp
from .plans.resets import reset_USAXS
from .plans.sample_transmission import measure_USAXS_Transmission
from .plans.sim_plans import sim_count_plan
from .plans.sim_plans import sim_print_plan
from .plans.sim_plans import sim_rel_scan_plan
from .utils.setup_new_user import newUser
from .utils.setup_new_user import newSample

# customize the instrument configuration
oregistry["usaxs_shutter"].delay_s = 0.01

newUser()
