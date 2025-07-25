# this is a warmup instrument plan

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


from usaxs.plans.command_list import run_command_file


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
            logger.info("Running run_command_file repeatedly")
            yield from run_command_file(filename)
            logger.info("completed run_command_file")
        except Exception as exc:
            logger.error(f"caught {exc}")
