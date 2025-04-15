"""
Install a NeXus file writer for uascan raw data files

See ``instrument.utils.setup_new_user.newFile()``
to replace ``instrument.framework.callbacks.newSpecFile()``
"""

import logging

from ..framework import RE
from ..framework import callback_db
from .nxwriter_usaxs import NXWriterUascan

__all__ = [
    "nxwriter",
]

logger = logging.getLogger(__name__)
logger.info(__file__)

# TODO move this into nxwriter_usaxs which subscribes
nxwriter = NXWriterUascan()
#
callback_db["nxwriter"] = RE.subscribe(nxwriter.receiver)
