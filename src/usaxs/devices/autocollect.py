"""
Automated data collection device and plan for the 12-ID-E USAXS instrument.

``AutoCollectDataDevice`` wraps three EPICS PVs that allow an external client
(e.g. SPEC, a GUI, or another IOC) to trigger Bluesky data-collection plans
remotely via Channel Access.

Typical usage::

    RE(auto_collect.remote_ops())

The ``remote_ops`` plan loops until ``permit`` is cleared, executing whichever
named command or command-file appears in ``commands`` each time ``trigger_signal``
is asserted.
"""

import datetime
import logging
import os

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal

logger = logging.getLogger(__name__)


class AutoCollectDataDevice(Device):
    """EPICS-triggered automated data collection device.

    Wraps three PVs that allow an external client to start Bluesky plans
    via Channel Access:

    ``trigger_signal`` (``Start``)
        Set to ``"start"`` / 1 by the external client to request a collection.
        The plan resets it to 0 immediately after reading ``commands``.
    ``commands`` (``StrInput``)
        String PV holding the name of the plan to run or the path to a
        command file.  Recognised built-in commands: ``"preUSAXStune"``,
        ``"useModeRadiography"``.  Any other value is treated as a path to a
        command file (see ``run_command_file``).
    ``permit`` (``Permit``)
        Set to ``"yes"`` / 1 to allow collection.  Clearing it causes
        ``remote_ops`` to exit cleanly.
    """

    trigger_signal = Component(EpicsSignal, "Start", string=True)
    commands = Component(EpicsSignal, "StrInput", string=True)
    permit = Component(EpicsSignal, "Permit", string=True)
    idle_interval = 2  # seconds between idle-status prints

    def idle_reporter(self):
        """Print a one-line status message (overwriting the previous line)."""
        ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        print(
            f"{ts}: auto_collect is waiting for next command from EPICS ...",
            end="\r",
        )

    def remote_ops(self, *args, **kwargs):
        """Bluesky plan: loop waiting for PV-directed data collection commands.

        Sets ``permit`` to ``"yes"`` on entry, then polls ``trigger_signal``
        every ``idle_interval`` seconds.  When a trigger is received the
        command in ``commands`` is executed.

        The plan exits when:

        * ``permit`` is cleared (set to anything other than 1 / ``"yes"``).
        * The user types ``^C`` twice (``RE.abort()``).
        * An unhandled exception propagates out of the command dispatcher.

        Yields
        ------
        Bluesky messages.
        """
        from usaxs.plans.plans_tune import preUSAXStune
        from usaxs.plans.command_list import run_command_file

        user_data = oregistry["user_data"]

        yield from bps.mv(self.permit, "yes")
        yield from bps.sleep(1)

        while self.permit.get() in (1, "yes"):
            if self.trigger_signal.get() in (1, "start"):
                print()  # next line if emerging from idle_reporter()
                yield from bps.mv(self.trigger_signal, 0)

                command = self.commands.get()
                try:
                    if command == "preUSAXStune":
                        yield from bps.mv(user_data.collection_in_progress, 1)
                        yield from preUSAXStune()
                        yield from bps.mv(user_data.collection_in_progress, 0)
                    elif command == "useModeRadiography":
                        yield from bps.mv(user_data.collection_in_progress, 1)
                        # mode_Radiography() not yet implemented here
                        yield from bps.mv(user_data.collection_in_progress, 0)
                    elif os.path.exists(command):
                        yield from run_command_file(command)
                    else:
                        logger.warning("unrecognized command: %s", command)
                except Exception as exc:
                    logger.warning(
                        "Exception during execution of command %s:\n%s", command, exc
                    )
                logger.info("waiting for next user command")
            else:
                yield from bps.sleep(self.idle_interval)
                self.idle_reporter()

        print()  # next line if emerging from idle_reporter()

