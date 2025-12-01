"""
automated data collection

To start the automatic data collection plan:

    RE(auto_collect.remote_ops())
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal

from bluesky import plan_stubs as bps
from bluesky import plans as bp
from apsbits.core.instrument_init import oregistry
import datetime
import os



class AutoCollectDataDevice(Device):
    """Device for automated data collection control.

    This device manages the signals for automated data collection, including
    trigger signals, command inputs, and permission controls.

    Attributes:
        trigger_signal: EpicsSignal for starting the collection
        commands: EpicsSignal for string input commands
        permit: EpicsSignal for permission control
        idle_interval: Time interval in seconds between idle checks
    """

    trigger_signal: Component[EpicsSignal] = Component(
        EpicsSignal, "Start", string=True
    )
    commands: Component[EpicsSignal] = Component(EpicsSignal, "StrInput", string=True)
    permit: Component[EpicsSignal] = Component(EpicsSignal, "Permit", string=True)
    idle_interval: int = 2  # seconds
    
    def idle_reporter(self):
        """Update the console while waiting for next remote command."""
        ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        print(
            f"{ts}: auto_collect is waiting for next command from EPICS ...",
            end="\r"
        )


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
            
            from usaxs.plans.plans_tune import preUSAXStune
            #from .plans import mode_Radiography
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
                            yield from bps.mv(user_data.collection_in_progress, 1,)
                            yield from preUSAXStune()
                            yield from bps.mv(user_data.collection_in_progress, 0,)
                        elif command == "useModeRadiography":
                            yield from bps.mv(user_data.collection_in_progress, 1,)
                            #yield from mode_Radiography()
                            yield from bps.mv(user_data.collection_in_progress, 0,)
                        elif os.path.exists(command):
                            yield from run_command_file(command)
                        else:
                            #logger.warning("unrecognized command: %s", command)
                            pass
                    except Exception as exc:
                        #logger.warn("Exception during execution of command %s:\n%s", command, str(exc))
                        pass
                    #logger.info("waiting for next user command")
                else:
                    yield from bps.sleep(self.idle_interval)
                    self.idle_reporter()

            print()  # next line if emerging from idle_reporter()

