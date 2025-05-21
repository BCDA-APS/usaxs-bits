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
    from .callbacks.spec_data_file_writer import init_specwriter_with_RE  # noqa: F401
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

RE(make_devices(file="scaler.yml", clear=False))
scaler0 = oregistry["scaler0"]
scaler0.stage_sigs["count_mode"] = "OneShot"

scaler0.channels.chan03.name = "I00_SIGNAL"
scaler0.channels.chan03.s.name = "I00"
oregistry.register(scaler0.channels.chan03)  # I00 singal

scaler0.channels.chan02.name = "I0_SIGNAL"
scaler0.channels.chan02.s.name = "I0"
oregistry.register(scaler0.channels.chan02)  # I0 signal

scaler0.channels.chan04.name = "UPD_SIGNAL"
scaler0.channels.chan04.s.name = "UPD"
oregistry.register(scaler0.channels.chan04)  # UPD signal

scaler0.channels.chan05.name = "TRD_SIGNAL"
scaler0.channels.chan05.s.name = "TRD"
oregistry.register(scaler0.channels.chan05)  # TRD signal


##operation variables
in_operation = False  # should be a caget?

##load devices
RE(make_devices(file="devices.yml", clear=False))
RE(make_devices(file="ad_devices.yml", clear=False))

if in_operation:
    RE(make_devices(file="shutters_op.yml", clear=False))
if not in_operation:
    RE(make_devices(file="shutters_sim.yml", clear=False))
