"""
USAXS fly-scan device for the 12-ID-E USAXS instrument.

``UsaxsFlyScanDevice``
    Ophyd device that holds fly-scan configuration and runtime state.
    The ``busy`` PV drives the Aerotech controller to execute the pre-loaded
    trajectory; ``scan_time`` and ``num_points`` mirror the EPICS parameters.
    The ``flying`` soft signal is set ``True`` while a fly scan is in progress
    and is used by plans to gate progress reporting.

    Fly-scan *plans* live in ``usaxs/plans/``.
    Fly-scan HDF5 saving is handled by ``usaxs_flyscan_support/saveFlyData.py``.

    # Testing SaveFlyScan() outside a plan:
    # sfs = SaveFlyScan("/tmp/sfs.h5", config_file=XML_CONFIGURATION_FILE)
    # sfs.preliminaryWriteFile()
    # sfs.saveFile()
"""

from apsbits.utils.config_loaders import get_config
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import Signal
from ophyd.status import Status

from ..usaxs_flyscan_support.saveFlyData import XML_CONFIGURATION_FILE

iconfig = get_config()
fly_scan_settings = iconfig.get("USAXS_FLY_SCAN_SETTINGS", {})

fallback_dir = fly_scan_settings.get("FALLBACK_DIR")
hdf5_file = fly_scan_settings.get("SAVE_FLY_DATA_HDF5_FILE")
hdf5_dir = fly_scan_settings.get("SAVE_FLY_DATA_HDF5_DIR")


class UsaxsFlyScanDevice(Device):
    """EPICS interface and runtime state for the USAXS fly scan.

    ``busy``       — EPICS busy record that triggers the Aerotech trajectory.
    ``scan_time``  — expected fly-scan duration (s).
    ``num_points`` — number of trajectory points.
    ``flying``     — soft signal; ``True`` while a fly scan is executing.
    ``timeout_s``  — extra padding beyond ``scan_time`` before declaring a timeout.
    """

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
        self.ax0 = None
        self.dx0 = None
        self.saveFlyData = None
        self.saveFlyData_config = XML_CONFIGURATION_FILE
        self.saveFlyData_HDF5_dir = hdf5_dir
        self.fallback_dir = fallback_dir
        self.saveFlyData_HDF5_file = hdf5_file
        self._output_HDF5_file_ = None
        self.flying._status = Status()  # issue #501
        self.flying._status.set_finished()
