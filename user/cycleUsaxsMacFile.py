# this is a warmup instrument plan

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps

from instrument.devices import usaxs_flyscan
from instrument.plans.command_list import run_command_file


def cycle_command_file(filename, md=None):
    """
    simply runs usaxs.mac in a loop. 
    run as:
    RE(cycle_command_file("usaxs.mac"))
    to stop, use Stop checkbox on GUI
       
    reload by : 
    %run -m cycleUsaxsMacFile
    """
    if md is None:
        md = {}
    while True:
        try:
            logger.info(f"Running run_command_file repeatedly")
            yield from run_command_file(filename)
            logger.info(f"completed run_command_file")
        except Exception as exc:
            logger.error(f"caught {exc}")
