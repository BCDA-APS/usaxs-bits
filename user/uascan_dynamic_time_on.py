
"""
Turn on dynamic time in uascan.

Command line::
    %run -im user.uascan_dynamic_time_on

In a command file::
    run_python user/uascan_dynamic_time_on.py    
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from instrument.devices import terms


terms.USAXS.useDynamicTime.put(True)
logger.info(
    "terms.USAXS.useDynamicTime = %s",
    terms.USAXS.useDynamicTime.get()
)
