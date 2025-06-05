"""
Start Bluesky Data Acquisition sessions of all kinds.

Includes:

* Python script
* IPython console
* Jupyter notebook
* Bluesky queueserver
"""

import logging
import os
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
from epics import caget 

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
in_operation = caget("usxLAX:blCalc:userCalc2.VAL") == 1  # should be a caget?
#in_operation = True
logger.info("in operation = " + str(in_operation))

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



from usaxs.utils.setup_new_user import newUser

# customize the instrument configuration
bec.disable_table()
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_shutter.delay_s=0.01

logger.info("Your Path Is : %s", os.getcwd())

filename = ".user_info.txt" #Store if a new user was created
if Path(filename).is_file():
    logger.info(f"{filename} exists, no need to run new user")
    user_name = Path(filename).read_text()
    logger.info("You are running as: %s", user_name.strip())
else:
    logger.info(f"{filename} does not exist, run new user")
    while True:
        new_user_name = input("Please provide the name of the new user: ").strip()
        if new_user_name:  # Check if not empty
            break
        print("Argument cannot be empty. Please try again.")
    newUser(new_user_name)
    Path(filename).write_text(new_user_name)
