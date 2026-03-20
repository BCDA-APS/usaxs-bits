#!/usr/bin/env python


"""
Save EPICS PV data from a USAXS fly scan to a NeXus/HDF5 file.

The HDF5 file structure is defined by an external XML configuration file
(``saveFlyData.xml``) validated against ``saveFlyData.xsd``.  The
``NeXus_Structure`` manager from ``nexus_flyscan`` parses that XML once and
caches the result for the session.

Writing happens in two passes:

1. ``preliminaryWriteFile()`` — called while the fly scan is still running.
   Writes PVs where ``acquire_after_scan=false`` in the XML.
2. ``saveFile()`` — called after the scan trigger signals completion.
   Writes PVs where ``acquire_after_scan=true``, then creates all NeXus links
   and closes the file.

This module can also be run as a CLI script (``python saveFlyData.py``),
which is how SPEC invokes it.  See ``main()`` for the entry point.
"""

import argparse
import datetime
import logging
import os
import sys
import time
from typing import Any
from typing import Optional

import h5py
import numpy

logger = logging.getLogger(__name__)

# do not warn if the HDF5 library version has changed
# headers are 1.8.15, library is 1.8.16
# THIS SETTING MIGHT BITE US IN THE FUTURE!
os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"

# matches IOC for big arrays
os.environ["EPICS_CA_MAX_ARRAY_BYTES"] = "1280000"  # was 200000000
try:
    import usaxs.usaxs_flyscan_support.nexus_flyscan as nexus_flyscan
    # when run standalone
except ImportError:
    from . import nexus_flyscan  # when imported in a package


COMMON_AD_CONFIG_DIR = "/share1/AreaDetectorConfig/FlyScan_config/"
path = os.path.dirname(__file__)
XML_CONFIGURATION_FILE = os.path.join(
    COMMON_AD_CONFIG_DIR,
    "saveFlyData.xml",
)
XSD_SCHEMA_FILE = os.path.join(path, "saveFlyData.xsd")


class TimeoutException(Exception):
    """Exception raised when a timeout occurs during data acquisition."""

    pass


class EpicsNotConnected(Exception):
    """Exception raised when an EPICS PV connection cannot be established."""

    pass


NOT_CONNECTED_TEXT = "not connected"
NO_DATA_TEXT = "no data"


class SaveFlyScan(object):
    """Class for saving fly scan data.

    This class handles saving data from fly scans to HDF5 files, including
    metadata and scan parameters.
    """

    trigger_pv = "usxLAX:USAXSfly:Start"
    trigger_accepted_values = (0, "Done")
    trigger_poll_interval_s = 0.1
    scantime_pv = "usxLAX:USAXS:FS_ScanTime"
    creator_version = "unknown"
    flyScanNotSaved_pv = "usxLAX:USAXS:FlyScanNotSaved"

    def __init__(self, hdf5_file: str, config_file: Optional[str] = None) -> None:
        """Initialize the SaveFlyScan instance.

        Args:
            hdf5_file (str): Path to the HDF5 file where data will be saved.
            config_file (str, optional): Path to the XML configuration file.
                If not provided, uses the default configuration file.
        """
        self.hdf5_file_name = hdf5_file
        # XML_CONFIGURATION_FILE is already an absolute path
        self.config_file = config_file or XML_CONFIGURATION_FILE

        self.mgr = nexus_flyscan.get_manager(self.config_file)
        self._prepare_to_acquire()

    def waitForData(self) -> None:
        """Wait until the data is ready, then save it.

        Note:
            Not for production use in bluesky.
            This routine is used by SPEC and for development code.

            No timeout is implemented intentionally — fly scan duration varies
            enormously (seconds to hours) and no fixed limit is sensible.
            The caller is expected to kill the process externally if needed.
        """
        import epics

        def keep_waiting():
            triggered = self.trigger.get() in self.trigger_accepted_values
            return not triggered

        self.trigger = epics.PV(self.trigger_pv)
        epics.caput(self.flyScanNotSaved_pv, 1)
        # file is open now, write preliminary data
        self.preliminaryWriteFile()

        while keep_waiting():
            time.sleep(self.trigger_poll_interval_s)

        # write the remaining data and close the file
        self.saveFile()
        epics.caput(self.flyScanNotSaved_pv, 0)

    def preliminaryWriteFile(self) -> None:
        """Write all preliminary data to the file while fly scan is running.

        This method writes data that can be acquired before the scan completes,
        such as metadata and configuration parameters.
        """
        not_connected_PVs = self.mgr.unconnected_signals
        for pv_spec in self.mgr.pv_registry.values():
            if pv_spec.acquire_after_scan:
                continue
            elif pv_spec in not_connected_PVs:
                logger.warning(
                    "preliminaryWriteFile(): PV %s is not connected now", pv_spec.pvname
                )
                value = NOT_CONNECTED_TEXT
            elif pv_spec.as_string:
                value = pv_spec.ophyd_signal.get(
                    as_string=True, timeout=10, use_monitor=False
                )
            else:
                value = pv_spec.ophyd_signal.get(timeout=10, use_monitor=False)
            if value is None:
                value = NO_DATA_TEXT
            logger.debug(f"preliminaryWriteFile(): writing {pv_spec}")
            if not isinstance(value, numpy.ndarray):
                value = [value]
            else:
                lim = pv_spec.length_limit
                pv_reg = self.mgr.pv_registry
                if lim and lim in pv_reg:
                    length_limit = pv_reg[lim].ophyd_signal.get()
                    if len(value) > length_limit:
                        value = value[:length_limit]

            hdf5_parent = pv_spec.group_parent.hdf5_group
            try:
                logger.debug(
                    'preliminaryWriteFile(name="%s", data=%s)', pv_spec.label, value
                )
                ds = makeDataset(hdf5_parent, pv_spec.label, value)
                if ds is None:
                    logger.debug(f"Could not create {pv_spec.label}")
                    continue
                self._attachEpicsAttributes(ds, pv_spec)
                addAttributes(ds, **pv_spec.attrib)
            except IOError as e:
                logger.debug("preliminaryWriteFile():")
                logger.debug(
                    "ERROR: pv_spec.label=%s, value=%s", pv_spec.label, str(value)
                )
                logger.debug("MESSAGE: %s", e)
                logger.debug("RESOLUTION: writing as error message string")
                makeDataset(hdf5_parent, pv_spec.label, [str(e).encode("utf8")])

    def saveFile(self) -> None:
        """Write all desired data to the file and close it.

        This method writes data that must be acquired after the scan completes,
        such as final measurements and scan results.
        """
        t = datetime.datetime.now()
        timestamp = datetime.datetime.isoformat(t, sep=" ")
        f = self.mgr.group_registry["/"].hdf5_group
        f.attrs["timestamp"] = timestamp

        # note: len(caget(array)) returns NORD (number of useful data)
        not_connected_PVs = self.mgr.unconnected_signals
        for pv_spec in self.mgr.pv_registry.values():
            if pv_spec in not_connected_PVs:
                logger.warning("saveFile(): PV %s is not connected now", pv_spec.pvname)
                continue
            if not pv_spec.acquire_after_scan:
                continue
            if pv_spec.as_string:
                value = pv_spec.ophyd_signal.get(as_string=True)
            else:
                value = pv_spec.ophyd_signal.get()
            if value is None:
                value = NO_DATA_TEXT
            if not isinstance(value, numpy.ndarray):
                value = [value]
            else:
                if (
                    pv_spec.length_limit
                    and pv_spec.length_limit in self.mgr.pv_registry
                ):
                    length_limit = self.mgr.pv_registry[
                        pv_spec.length_limit
                    ].ophyd_signal.get()
                    if len(value) > length_limit:
                        value = value[:length_limit]

            hdf5_parent = pv_spec.group_parent.hdf5_group
            try:
                logger.debug(f'saveFile(name="{pv_spec.label}", data={value})')
                ds = makeDataset(hdf5_parent, pv_spec.label, value)
                self._attachEpicsAttributes(ds, pv_spec)
                addAttributes(ds, **pv_spec.attrib)
            except Exception as e:
                logger.debug("saveFile():")
                logger.debug(
                    "ERROR: pv_spec.label=%s, value=%s", pv_spec.label, str(value)
                )
                logger.debug("MESSAGE: %s", e)
                logger.debug("RESOLUTION: writing as error message string")
                makeDataset(hdf5_parent, pv_spec.label, [str(e).encode("utf8")])

        # as the final step, make all the links as directed
        for _k, v in self.mgr.link_registry.items():
            v.make_link(f)

        f.close()  # be CERTAIN to close the file
        logger.debug("saveFile(): file closed")

    def _get_support_code_dir(self):
        """Return the absolute directory containing this source file."""
        return os.path.split(os.path.abspath(__file__))[0]

    def _prepare_to_acquire(self):
        """connect with EPICS and create HDF5 file and structure"""
        t0 = time.time()
        if not self.mgr.configured:
            self.mgr._read_configuration()
            self.mgr._connect_ophyd()
            for _i in range(50):  # limited wait to connect
                verdict = self.mgr.connected
                logger.debug(f"connected: {verdict}  time:{time.time()-t0}")
                if verdict:
                    break  # seems to take about 60-70 ms with current XML file
                time.sleep(0.01)

        connect_timeout = 15.0
        while not self.mgr.connected:
            if time.time() - t0 > connect_timeout:
                for item in self.mgr.unconnected_signals:
                    logger.warning(
                        "Not connected PV=%s  ophyd=%s",
                        item.pvname,
                        item.ophyd_signal.name,
                    )
                # Intentional: some PVs are routinely unavailable (unimportant
            # metadata sources).  Raising here caused too many spurious
            # failures.  Unconnected PVs are logged as warnings above and
            # written as NOT_CONNECTED_TEXT placeholders in the data file.
                break
            time.sleep(0.1)

        # create the file
        for key, xture in sorted(self.mgr.group_registry.items()):
            if key == "/":
                # create the file and internal structure
                f = h5py.File(self.hdf5_file_name, "w")
                # the following are attributes to the root element of the HDF5 file
                root_attrs = {}
                root_attrs["file_name"] = self.hdf5_file_name
                root_attrs["creator"] = __file__
                root_attrs["creator_version"] = self.creator_version
                root_attrs["creator_config_file"] = self.config_file
                root_attrs["HDF5_Version"] = h5py.version.hdf5_version
                root_attrs["h5py_version"] = h5py.version.version
                addAttributes(f, **root_attrs)
                xture.hdf5_group = f
            else:
                hdf5_parent = xture.group_parent.hdf5_group
                xture.hdf5_group = hdf5_parent.create_group(xture.name)
                xture.hdf5_group.attrs["NX_class"] = xture.nx_class
            addAttributes(xture.hdf5_group, **xture.attrib)

        for field in self.mgr.field_registry.values():
            field.text = field.text.encode("utf8")  # lxml always gives str; encode for h5py
            try:
                ds = makeDataset(
                    field.group_parent.hdf5_group, field.name, [field.text]
                )
                addAttributes(ds, **field.attrib)
            except Exception as err:
                msg = "problem with field={}, text={}, exception={}".format(
                    field.name, field.text, err
                )
                raise Exception(msg) from err

    def _attachEpicsAttributes(self, node, pv):
        """attach common attributes from EPICS to the HDF5 tree node"""
        if hasattr(pv.ophyd_signal, "desc"):
            desc = pv.ophyd_signal.desc.value
        else:
            desc = ""

        attr = {}
        attr["epics_pv"] = pv.pvname.encode("utf8")
        if hasattr(pv, "units"):
            t = pv.units
        else:
            t = ""
        attr["units"] = t.encode("utf8")
        if hasattr(pv, "type"):
            t = pv.type
        else:
            t = ""
        attr["epics_type"] = t
        attr["epics_description"] = desc.encode("utf8")
        addAttributes(node, **attr)


def makeDataset(parent: h5py.Group, name: str, data: Any) -> Optional[h5py.Dataset]:
    """Create a dataset in the HDF5 file.

    Args:
        parent (h5py.Group): Parent group in the HDF5 file.
        name (str): Name of the dataset.
        data (Any): Data to be stored in the dataset.

    Returns:
        Optional[h5py.Dataset]: The created dataset, or None if creation failed.
    """
    if name in parent:
        del parent[name]
    try:
        dset = parent.create_dataset(name, data=data)
        return dset
    except Exception as _exc:
        logger.error(
            "Could not create dataset: %s:%s, %s",
            parent.name,
            name,
            str(_exc),
        )
        return None


def addAttributes(dataset: h5py.Dataset, **kwargs) -> None:
    """Add attributes to a dataset.

    Args:
        dataset (h5py.Dataset): The dataset to add attributes to.
        **kwargs: Keyword arguments representing attribute names and values.
    """
    for k, v in kwargs.items():
        dataset.attrs[k] = v


def get_CLI_options() -> argparse.Namespace:
    """Get command line interface options.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("data_file", action="store", help="/path/to/new/hdf5/data/file")

    parser.add_argument(
        "xml_config_file", action="store", help="XML configuration file"
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the command line interface.

    This function handles command line arguments, validates file paths,
    and executes the fly scan data saving process.

    Raises:
        RuntimeError: If the data file already exists or if the config file is not found
    """
    cli_options = get_CLI_options()
    dataFile = cli_options.data_file
    path = os.path.dirname(dataFile)
    if len(path) > 0 and not os.path.exists(path):
        msg = "directory for that file does not exist: " + dataFile
        raise RuntimeError(msg)

    if os.path.exists(dataFile):
        msg = "file exists: " + dataFile
        raise RuntimeError(msg)

    configFile = cli_options.xml_config_file
    if not os.path.exists(configFile):
        msg = "config file not found: " + configFile
        raise RuntimeError(msg)

    sfs = SaveFlyScan(dataFile, configFile)
    try:
        sfs.waitForData()
    except TimeoutException as _exception_message:
        logger.warning("exiting because of timeout!!!!!!!")
        sys.exit(1)  # exit silently with error, 1=TIMEOUT
    logger.debug("wrote file: " + dataFile)


def developer_bluesky() -> None:
    """Development function for testing with Bluesky.

    This function creates a test HDF5 file using the default XML configuration
    and waits for data to be available.
    """
    sfs = SaveFlyScan("test.h5", XML_CONFIGURATION_FILE)
    sfs.waitForData()


def developer_spec():
    """Bluesky USAXS FlyScan uses this algorithm"""
    sfs = SaveFlyScan("/tmp/sfs.h5", XML_CONFIGURATION_FILE)
    sfs.preliminaryWriteFile()
    sfs.saveFile()


if __name__ == "__main__":
    main()  # production system - SPEC uses this
    # developer_bluesky()
    # developer_spec()

# Developer test commands (run from the tools directory):
#   /bin/rm test.h5
#   caput usxLAX:USAXSfly:Start 0
#   python ./saveFlyData.py ./test.h5 ./saveFlyData.xml
#   python ~/bin/h5toText.py ./test.h5
