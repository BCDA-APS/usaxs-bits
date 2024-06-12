
"""
support USAXS area detectors

replace Bluesky file name scheme when used with area detector

file systems on some area detectors need more work

* saxs:  /mnt/share1/USAXS_data/yyyy-mm/user_working_folder_saxs/
* waxs:  /mnt/usaxscontrol/USAXS_data/yyyy-mm/user_working_folder_waxs/
* PointGrey BlackFly does not write out to file typically.  No use of HDF5 plugin.
* PointGrey BlackFly Optical: /mnt/share1/USAXS_data/...
* Alta: /mnt/share1/USAXS_data/...
"""

__all__ = """
    _validate_AD_FileWriter_path_
    area_detector_EPICS_PV_prefix
    DATABROKER_ROOT_PATH
    EpicsDefinesHDF5FileNames
    EpicsDefinesJpegFileNames
    myHdf5EpicsIterativeWriter
    myHDF5FileNames
    myJpegEpicsIterativeWriter
    myJpegFileNames
    """.split()



import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import AD_EpicsHdf5FileName
from apstools.devices import AD_EpicsJPEGFileName
from apstools.devices import AD_EpicsTIFFFileName
from apstools.devices import AD_plugin_primed
from collections import OrderedDict
#from .ad_tiff_upstream import AD_EpicsTiffFileName - obsolete on 6/1/2024, https://bcda-aps.github.io/apstools/latest/api/_devices.html#apstools.devices.area_detector_support.AD_EpicsFileNameTIFFPlugin
from ophyd import HDF5Plugin
from ophyd import JPEGPlugin
from ophyd import TIFFPlugin
from ophyd.areadetector.filestore_mixins import FileStoreBase
from ophyd.areadetector.filestore_mixins import FileStoreIterativeWrite
#from ophyd.utils import set_and_wait
import itertools
import numpy as np
import time


DATABROKER_ROOT_PATH = "/"

area_detector_EPICS_PV_prefix = {
    'Pilatus 100k' : 'usaxs_pilatus3:',
    'Pilatus 200kw' : 'usaxs_pilatus2:',
    'PointGrey BlackFly' : 'usxFLY1:',      # radiography
    'PointGrey BlackFly Optical' : 'usxFLY2:',
    'Alta' : 'usxalta:',
    'SimDetector' : 'usxSIM1:',
    'Dexela 2315' : 'usxDEX:',
}


def _validate_AD_FileWriter_path_(path, root_path):
    if not str(path).startswith(root_path):
        raise ValueError((
            f"error in file {__file__}:\n"
            f"  path '{path}' must start with '{root_path}"
        ))


class Override_AD_EpicsHdf5FileName(AD_EpicsHdf5FileName):
    # TODO: for apstools, but not yet as of 6-12-2024

    def stage(self):
        """
        overrides default behavior
        Set EPICS items before device is staged, then copy EPICS
        naming template (and other items) to ophyd after staging.
        """
        # Make a filename.
        filename, read_path, write_path = self.make_filename()

        # Ensure we do not have an old file open.
        #set_and_wait(self.capture, 0)
        self.capture.set(0).wait()
        # These must be set before parent is staged (specifically
        # before capture mode is turned on. They will not be reset
        # on 'unstage' anyway.

        if not (write_path.endswith("/") or write_path.endswith("\\")):
            if write_path.find("\\") >= 0:
                write_path += "\\"
            else:
                write_path += "/"

        #set_and_wait(self.file_path, write_path)
        self.file_path.set(write_path).wait()
        #set_and_wait(self.file_name, filename)
        self.file_name.set(filename).wait()
        ### set_and_wait(self.file_number, 0)

        # get file number now since it is incremented during stage()
        file_number = self.file_number.get()
        # Must avoid parent's stage() since it sets file_number to 0
        # Want to call grandparent's stage()
        #super().stage()     # avoid this - sets `file_number` to zero
        # call grandparent.stage()
        FileStoreBase.stage(self)

        # AD does the file name templating in C
        # We can't access that result until after acquisition
        # so we apply the same template here in Python.
        template = self.file_template.get()
        self._fn = template % (read_path, filename, file_number)
        self._fp = read_path
        if not self.file_path_exists.get():
            raise IOError("Path {} does not exist on IOC.".format(
                          self.file_path.get()))

        self._point_counter = itertools.count()

        # from FileStoreHDF5.stage()
        res_kwargs = {'frame_per_point': self.get_frames_per_point()}
        self._generate_resource(res_kwargs)


class myHdf5EpicsIterativeWriter(Override_AD_EpicsHdf5FileName,
                                 FileStoreIterativeWrite): ...
class myHDF5FileNames(HDF5Plugin, myHdf5EpicsIterativeWriter): ...
class EpicsDefinesHDF5FileNames(HDF5Plugin,
                                myHdf5EpicsIterativeWriter): ...

class myJpegEpicsIterativeWriter(AD_EpicsJPEGFileName,
                                 FileStoreIterativeWrite): ...
class myJpegFileNames(JPEGPlugin, myJpegEpicsIterativeWriter): ...
class EpicsDefinesJpegFileNames(JPEGPlugin,
                                myJpegEpicsIterativeWriter): ...

class myTiffEpicsIterativeWriter(AD_EpicsTIFFFileName,
                                 FileStoreIterativeWrite): ...
class myTiffFileNames(TIFFPlugin, myTiffEpicsIterativeWriter): ...
class EpicsDefinesTiffFileNames(TIFFPlugin,
                                myTiffEpicsIterativeWriter): ...


def Override_AD_plugin_primed(plugin):
    """
    Has area detector pushed an NDarray to the file writer plugin?
    """
    cam = plugin.parent.cam
    tests = []

    for obj in (cam, plugin):
        test = np.array(obj.array_size.get()).sum() != 0
        tests.append(test)
        if not test:
            logger.debug("'%s' image size is zero", obj.name)

    checks = dict(array_size=False, color_mode=True,)
    for key, as_string in checks.items():
        c = getattr(cam, key).get(as_string=as_string)
        p = getattr(plugin, key).get(as_string=as_string)
        test = c == p
        tests.append(test)
        if not test:
            logger.debug("%s does not match", key)

    return False not in tests


def Override_AD_prime_plugin2(plugin):
    """Override faulty apstools implementation"""
    if Override_AD_plugin_primed(plugin):
        logger.debug("'%s' plugin is already primed", plugin.name)
        return

    sigs = OrderedDict(
        [
            (plugin.enable, 1),
            (plugin.parent.cam.array_callbacks, 1),  # set by number
            (plugin.parent.cam.image_mode, 0),  # Single, set by number
            (plugin.parent.cam.trigger_mode, 0),  # set by number
            # just in case the acquisition time is set very long...
            (plugin.parent.cam.acquire_time, 1),
            (plugin.parent.cam.acquire_period, 1),
            (plugin.parent.cam.acquire, 1),  # set by number
        ]
    )

    original_vals = {sig: sig.get() for sig in sigs}

    for sig, val in sigs.items():
        time.sleep(0.1)  # abundance of caution
        #set_and_wait(sig, val)
        sig.set(val).wait()


    while plugin.parent.cam.acquire.get() not in (0, "Done"):
        time.sleep(.05)  # wait for acquisition to finish

    for sig, val in reversed(list(original_vals.items())):
        time.sleep(0.1)
        #set_and_wait(sig, val)
        sig.set(val).wait()
