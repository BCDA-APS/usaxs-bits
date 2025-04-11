"""
APS only: connect with facility information
"""

import logging

from apstools.devices import ApsMachineParametersDevice

logger = logging.getLogger(__name__)

logger.info(__file__)


aps = ApsMachineParametersDevice(name="aps")
