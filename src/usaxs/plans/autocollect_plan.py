"""Automatic data collection plans for the USAXS instrument.

This module provides plans for automatic data collection in the USAXS instrument,
including remote operation control and command execution.
"""

import datetime
import logging
import os

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps

from .command_list import run_command_file
from .mode_changes import mode_Radiography
from .plans_tune import preUSAXStune

logger = logging.getLogger(__name__)


# Device instances
user_data = oregistry["user_device"]
auto_collect = oregistry["auto_collect"]


def idle_reporter() -> None:
    """Update the console while waiting for next remote command."""
    ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    print(f"{ts}: auto_collect is waiting for next command from EPICS ...", end="\r")


def remote_ops():
    """Enable PV-directed data collection.

    This function enables automatic data collection based on EPICS PV commands.
    It supports various modes including pre-USAXS tuning, radiography mode,
    and command file execution.

    Parameters
    ----------
    None

    Returns
    -------
    None

    USAGE:  ``RE(remote_ops())``
    """

    yield from bps.mv(auto_collect.permit, "yes")
    yield from bps.sleep(1)

    logger.info("auto_collect is waiting for user commands")
    while auto_collect.permit.get() in (1, "yes"):
        if auto_collect.trigger_signal.get() in (1, "start"):
            print()  # next line if emerging from idle_reporter()
            logger.debug("starting user commands")
            yield from bps.mv(auto_collect.trigger_signal, 0)

            command = auto_collect.commands.get()
            try:
                if command == "preUSAXStune":
                    yield from bps.mv(
                        user_data.collection_in_progress,
                        1,
                    )
                    yield from preUSAXStune()
                    yield from bps.mv(
                        user_data.collection_in_progress,
                        0,
                    )
                elif command == "useModeRadiography":
                    yield from bps.mv(
                        user_data.collection_in_progress,
                        1,
                    )
                    yield from mode_Radiography()
                    yield from bps.mv(
                        user_data.collection_in_progress,
                        0,
                    )
                elif os.path.exists(command):
                    yield from run_command_file(command)
                else:
                    logger.warning("unrecognized command: %s", command)
            except Exception as exc:
                logger.warning(
                    "Exception during execution of command %s:\n%s",
                    command,
                    str(exc),
                )
            logger.info("waiting for next user command")
        else:
            yield from bps.sleep(auto_collect.idle_interval)
            idle_reporter()

    print()  # next line if emerging from idle_reporter()
    logger.info("auto_collect is ending")
