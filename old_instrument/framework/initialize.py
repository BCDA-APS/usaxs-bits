"""
initialize the bluesky framework
"""

__all__ = """
    RE  db  sd  bec  peaks
    bp  bps  bpp
    summarize_plan
    np
    callback_db
    """.split()

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)

import os
import sys

# fmt: off
sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
        )
    )
)
# fmt: on


# convenience imports
import databroker
from bluesky import RunEngine
from bluesky import SupplementalData
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.magics import BlueskyMagics
from bluesky.utils import PersistentDict
from bluesky.utils import ProgressBarManager
from IPython import get_ipython
from ophyd.signal import EpicsSignalBase

# DATABROKER_CATALOG = "9idc_usaxs_retired_2022_01_14"  # was mongodb_config in different format
# DATABROKER_CATALOG = "9idc_usaxs"  # last used 2022-11-07 before 8 am
DATABROKER_CATALOG = "usaxs"


def get_md_path():
    md_dir_name = "Bluesky_RunEngine_md"
    if os.environ == "win32":
        home = os.environ["LOCALAPPDATA"]
        path = os.path.join(home, md_dir_name)
    else:  # at least on "linux"
        home = os.environ["HOME"]
        path = os.path.join(home, ".config", md_dir_name)
    return path


# check if we need to transition from SQLite-backed historydict
old_md = None
md_path = get_md_path()
if not os.path.exists(md_path):
    logger.info("New directory to store RE.md between sessions: %s", md_path)
    os.makedirs(md_path)
    from bluesky.utils import get_history

    old_md = get_history()

# Set up a RunEngine and use metadata backed PersistentDict
RE = RunEngine({})
RE.md = PersistentDict(md_path)
if old_md is not None:
    logger.info("migrating RE.md storage to PersistentDict")
    RE.md.update(old_md)

# keep track of callback subscriptions
callback_db = {}

# Connect with our mongodb database
db = databroker.catalog[DATABROKER_CATALOG].v1

# Subscribe metadatastore to documents.
# If this is removed, data is not saved to metadatastore.
callback_db["db"] = RE.subscribe(db.insert)

# Set up SupplementalData.
sd = SupplementalData()
RE.preprocessors.append(sd)

# Add a progress bar.
pbar_manager = ProgressBarManager()
RE.waiting_hook = pbar_manager

# Register bluesky IPython magics.
get_ipython().register_magics(BlueskyMagics)

# Set up the BestEffortCallback.
bec = BestEffortCallback()
callback_db["bec"] = RE.subscribe(bec)
peaks = bec.peaks  # just as alias for less typing
bec.disable_baseline()

# At the end of every run, verify that files were saved and
# print a confirmation message.
# from bluesky.callbacks.broker import verify_files_saved
# callback_db['post_run_verify'] = RE.subscribe(post_run(verify_files_saved), 'stop')

# Uncomment the following lines to turn on
# verbose messages for debugging.
# ophyd.logger.setLevel(logging.DEBUG)

# diagnostics
# RE.msg_hook = ts_msg_hook

# set default timeout for all EpicsSignal connections & communications
TIMEOUT = 15
EpicsSignalBase.set_defaults(
    auto_monitor=True,
    timeout=TIMEOUT,
    write_timeout=TIMEOUT,
    connection_timeout=TIMEOUT,
)
