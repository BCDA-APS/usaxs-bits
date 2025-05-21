"""
Install a NeXus file writer for uascan raw data files

See ``instrument.utils.setup_new_user.newFile()``
to replace ``instrument.framework.callbacks.newSpecFile()``
"""

from ..startup import RE
from ..startup import callback_db
from .nxwriter_usaxs import NXWriterUascan


# TODO move this into nxwriter_usaxs which subscribes
nxwriter = NXWriterUascan()
#
callback_db["nxwriter"] = RE.subscribe(nxwriter.receiver)
