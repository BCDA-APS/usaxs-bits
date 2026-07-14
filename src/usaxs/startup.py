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
from apsbits.core.best_effort_init import init_bec_peaks
from apsbits.core.catalog_init import init_catalog
from apsbits.core.instrument_init import init_instrument
from apsbits.core.instrument_init import make_devices
from apsbits.core.run_engine_init import init_RE

# Utility functions
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

bec, peaks = init_bec_peaks(iconfig)
cat = init_catalog(iconfig)
RE, sd = init_RE(iconfig, subscribers=[bec, cat])

# Publish the RunEngine document stream over 0MQ so the queue-monitor GUI can
# draw live tune/alignment plots. Harmless when no proxy is listening. Run the
# proxy next to the RE Manager:  bluesky-0MQ-proxy 5567 5568
_doc_stream_cfg = iconfig.get("DOC_STREAM", {})
if _doc_stream_cfg.get("ENABLE", False):
    from bluesky.callbacks.zmq import Publisher

    _publish_addr = _doc_stream_cfg.get("PUBLISH_ADDR", "localhost:5567")
    RE.subscribe(Publisher(_publish_addr))
    logger.info("Publishing RunEngine documents to 0MQ proxy at %s", _publish_addr)

# These imports must come after the above setup.
# Queue server block
if running_in_queueserver():
    ### To make all the standard plans available in QS, import by '*', otherwise import
    ### plan by plan.
    from apstools.plans import lineup2  # noqa: F401
    #from bluesky.plans import *  # noqa: F403
else:
    # Import bluesky plans and stubs with prefixes set by common conventions.
    # The apstools plans and utils are imported by '*'.
    from apstools.plans import *  # noqa: F403
    from apstools.utils import *  # noqa: F403
    from bluesky import plan_stubs as bps  # noqa: F401
    from bluesky import plans as bp  # noqa: F401

# Experiment specific logic, device and plan loading. # Create the devices.
make_devices(clear=False, file="scalers_and_amplifiers.yml", device_manager=instrument)
setup_scalers()

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

else:  # if not in_operation:
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
from bluesky import preprocessors as bpp

# Queue server block
if running_in_queueserver():
    from .plans.axis_tuning import find_a2rp
    from .plans.axis_tuning import find_ar

    # these are all tuning plans facing users and staff
    from .plans.axis_tuning import tune_a2rp
    from .plans.axis_tuning import tune_ar
    from .plans.axis_tuning import tune_diode
    from .plans.axis_tuning import tune_dx
    from .plans.axis_tuning import tune_dy
    from .plans.axis_tuning import tune_mr
    from .plans.axis_tuning import tune_usaxs_optics
    from .plans.command_list import run_command_file
    from .plans.mode_changes import mode_DirectBeam
    from .plans.mode_changes import mode_OpenBeamPath
    from .plans.mode_changes import mode_Radiography
    from .plans.mode_changes import mode_SAXS
    from .plans.mode_changes import mode_USAXS
    from .plans.mode_changes import mode_WAXS
    from .plans.plans_usaxs import Flyscan
    from .plans.plans_usaxs import USAXSscan
    from .plans.plans_usaxs import USAXSscanStep
    from .plans.plans_user_facing import saxsExp
    from .plans.plans_user_facing import waxsExp
    from .plans.resets import reset_USAXS
    from .plans.user_actions_plans import new_sample_plan
    from .plans.user_actions_plans import new_user_plan
    from .utils.setup_new_user import newSample
    from .utils.setup_new_user import newUser

else:
    from usaxs.utils.obsidian import appendToMdFile
    from usaxs.utils.obsidian import recordBeamDump
    from usaxs.utils.obsidian import recordBeamRecovery
    from usaxs.utils.obsidian import recordFunctionRun
    from usaxs.utils.obsidian import recordNewSample
    from usaxs.utils.obsidian import recordProperEnd
    from usaxs.utils.obsidian import recordQserverRun
    from usaxs.utils.obsidian import recordRunCommandFile
    from usaxs.utils.obsidian import recordUserAbort
    from usaxs.utils.obsidian import recordUserStart

    from .plans.amplifiers_plan import autoscale_amplifiers
    from .plans.area_detector_plans import areaDetectorAcquire
    from .plans.autocollect_plan import remote_ops
    from .plans.axis_tuning import find_a2rp
    from .plans.axis_tuning import find_ar

    # these are all tuning plans facing users and staff
    from .plans.axis_tuning import tune_a2rp
    from .plans.axis_tuning import tune_ar
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
    from .plans.user_actions_plans import new_sample_plan
    from .plans.user_actions_plans import new_user_plan
    from .utils.setup_new_user import newSample
    from .utils.setup_new_user import newUser

# ── Apply beam suspenders to user-entry scan plans ────────────────
# These are the only plans that pause when the FE shutter closes or
# the beam leaves the hutch. Other plans run unguarded.
# Each line below is the literal equivalent of writing
# `@bpp.suspend_decorator(...)` above the plan definition — kept here
# (instead of in the plan files) so this whole story lives in one place
# and each beamline can fork it without touching the shared plan modules.
USAXSscan = bpp.suspend_decorator(suspend_FE_shutter)(USAXSscan)
USAXSscan = bpp.suspend_decorator(suspend_BeamInHutch)(USAXSscan)

saxsExp = bpp.suspend_decorator(suspend_FE_shutter)(saxsExp)
saxsExp = bpp.suspend_decorator(suspend_BeamInHutch)(saxsExp)

waxsExp = bpp.suspend_decorator(suspend_FE_shutter)(waxsExp)
waxsExp = bpp.suspend_decorator(suspend_BeamInHutch)(waxsExp)

# customize the instrument configuration
oregistry["usaxs_shutter"].delay_s = 0.01

if iconfig.get("NEXUS_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.nxwriter_usaxs import nxwriter_init

    nxwriter = nxwriter_init(RE, iconfig)

newUser(RE=RE, nxwriter=nxwriter)
