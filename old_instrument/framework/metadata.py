""" """

__all__ = [
    "RE",
]

import logging

logger = logging.getLogger(__name__)

import getpass
import os
import socket

import apstools
import area_detector_handlers
import bluesky
import databroker
import epics
import h5py
import matplotlib
import numpy
import ophyd
import pymongo
import pyRestTable
import spec2nexus

logger.info(__file__)

from .initialize import RE

# Set up default metadata

RE.md["beamline_id"] = "APS 12-ID-E USAXS"
RE.md["proposal_id"] = "testing"
RE.md["pid"] = os.getpid()

HOSTNAME = socket.gethostname() or "localhost"
USERNAME = getpass.getuser() or "APS 12-ID-E USAXS user"
RE.md["login_id"] = USERNAME + "@" + HOSTNAME

# useful diagnostic to record with all data
RE.md["versions"] = dict(
    apstools=apstools.__version__,
    area_detector_handlers=area_detector_handlers.__version__,
    bluesky=bluesky.__version__,
    databroker=databroker.__version__,
    epics_ca=epics.__version__,
    epics=epics.__version__,
    h5py=h5py.__version__,
    matplotlib=matplotlib.__version__,
    numpy=numpy.__version__,
    ophyd=ophyd.__version__,
    pymongo=pymongo.__version__,
    pyRestTable=pyRestTable.__version__,
    spec2nexus=spec2nexus.__version__,
)

# per https://github.com/APS-USAXS/ipython-usaxs/issues/553
RE.md["epics_libca"] = epics.ca.find_libca()
