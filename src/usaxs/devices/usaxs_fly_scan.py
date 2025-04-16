"""
USAXS Fly Scan setup
"""

from apsbits.utils.config_loaders import get_config
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import Signal
from ophyd.status import Status

from ..usaxs_support.saveFlyData import XML_CONFIGURATION_FILE

# NOTES for testing SaveFlyScan() command
"""
sfs = SaveFlyScan("/tmp/sfs.h5", config_file=XML_CONFIGURATION_FILE)
sfs.preliminaryWriteFile()
sfs.saveFile()
"""

iconfig = get_config()
fly_scan_settings = iconfig.get("USAXS_FLY_SCAN_SETTINGS", {})

fallback_dir = fly_scan_settings.get("FALLBACK_DIR")
hdf5_file = fly_scan_settings.get("FALLBACK_DIR")
hdf5_dir = fly_scan_settings.get("FALLBACK_DIR")


class UsaxsFlyScanDevice(Device):
    busy = Component(
        EpicsSignal, "usxLAX:USAXSfly:Start", string=True, put_complete=True
    )
    scan_time = Component(EpicsSignal, "usxLAX:USAXS:FS_ScanTime")
    num_points = Component(EpicsSignal, "usxLAX:USAXS:FS_NumberOfPoints")
    flying = Component(Signal, value=False)
    timeout_s = 120

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t0 = None
        self.update_time = None
        self.update_interval_s = 5
        self.ar0 = None
        self.ay0 = None
        self.dy0 = None
        self.saveFlyData = None
        self.saveFlyData_config = XML_CONFIGURATION_FILE
        self.saveFlyData_HDF5_dir = hdf5_dir
        self.fallback_dir = fallback_dir
        self.saveFlyData_HDF5_file = hdf5_file
        self._output_HDF5_file_ = None
        self.flying._status = Status()  # issue #501
        self.flying._status.set_finished()

