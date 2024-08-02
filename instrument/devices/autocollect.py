
"""
automated data collection

To start the automatic data collection plan:

    RE(auto_collect.remote_ops())
"""

__all__ = [
    'AutoCollectDataDevice',
    'auto_collect',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO
import datetime
import os

from ..plans import preUSAXStune
from ..plans import mode_Radiography
from ..plans import run_command_file
from .user_data import user_data


def idle_reporter():
    """Update the console while waiting for next remote command."""
    ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    print(
        f"{ts}: auto_collect is waiting for next command from EPICS ...",
        end="\r"
    )


class AutoCollectDataDevice(Device):
    trigger_signal = Component(EpicsSignal, "Start", string=True)
    commands = Component(EpicsSignal, "StrInput", string=True)
    permit = Component(EpicsSignal, "Permit", string=True)
    idle_interval = 2       # seconds

    def remote_ops(self, *args, **kwargs):
        """
        Bluesky plan to enable PV-directed data collection

        To start the automatic data collection plan:

            RE(auto_collect.remote_ops())

        The plan will exit when:

        * `permit` is not "yes" or 1
        * user types `^C` twice (user types `RE.abort()` then)
        * unhandled exception

        The plan will collect data when `trigger_signal` goes to "start" or 1.
        `trigger_signal` immediately goes back to "stop" or 0.

        The command to be run is in `commands` which is:

        * a named command defined here
        * a command file in the present working directory
        """
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
                        yield from bps.mv(user_data.collection_in_progress, 1,)
                        yield from preUSAXStune()
                        yield from bps.mv(user_data.collection_in_progress, 0,)
                    elif command == "useModeRadiography":
                        yield from bps.mv(user_data.collection_in_progress, 1,)
                        yield from mode_Radiography()
                        yield from bps.mv(user_data.collection_in_progress, 0,)
                    elif os.path.exists(command):
                        yield from run_command_file(command)
                    else:
                        logger.warning("unrecognized command: %s", command)
                except Exception as exc:
                    logger.warn("Exception during execution of command %s:\n%s", command, str(exc))
                logger.info("waiting for next user command")
            else:
                yield from bps.sleep(self.idle_interval)
                idle_reporter()

        print()  # next line if emerging from idle_reporter()
        logger.info("auto_collect is ending")


auto_collect = AutoCollectDataDevice(
    "9idcLAX:AutoCollection",   # NOTE: no trailing colon here!
    name="auto_collect")
