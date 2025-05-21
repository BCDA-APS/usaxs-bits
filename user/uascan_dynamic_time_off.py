"""
Turn off dynamic time in uascan.

Command line::
    %run -im user.uascan_dynamic_time_off

In a command file::
    run_python user/uascan_dynamic_time_off.py
"""

import logging

logger = logging.getLogger(__name__)


from instrument.devices import terms

terms.USAXS.useDynamicTime.put(False)
logger.info("terms.USAXS.useDynamicTime = %s", terms.USAXS.useDynamicTime.get())
