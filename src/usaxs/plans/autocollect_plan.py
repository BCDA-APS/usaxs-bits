"""Automatic data collection plans for the USAXS instrument.

This module provides plans for automatic data collection in the USAXS instrument,
including remote operation control and command execution.
"""

import datetime
import logging
import os
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from .command_list import run_command_file
from .mode_changes import mode_Radiography
from .scans import preUSAXStune

logger = logging.getLogger(__name__)


# Device instances
user_data = oregistry["user_data"]


def idle_reporter() -> None:
    """Update the console while waiting for next remote command."""
    ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    print(f"{ts}: auto_collect is waiting for next command from EPICS ...", end="\r")


def remote_ops(
    self: Any,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Enable PV-directed data collection.

    This function enables automatic data collection based on EPICS PV commands.
    It supports various modes including pre-USAXS tuning, radiography mode,
    and command file execution.

    Parameters
    ----------
    self : Any
        The autocollect device instance
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(auto_collect.remote_ops())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from bps.mv(self.permit, "yes")
        yield from bps.sleep(1)

        logger.info("auto_collect is waiting for user commands")
        while self.permit.get() in (1, "yes"):
            if self.trigger_signal.get() in (1, "start"):
                print()  # next line if emerging from idle_reporter()
                logger.debug("starting user commands")
                yield from bps.mv(self.trigger_signal, 0)

                command = self.commands.get()
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
                    logger.warn(
                        "Exception during execution of command %s:\n%s",
                        command,
                        str(exc),
                    )
                logger.info("waiting for next user command")
            else:
                yield from bps.sleep(self.idle_interval)
                idle_reporter()

        print()  # next line if emerging from idle_reporter()
        logger.info("auto_collect is ending")

    return (yield from _inner())
