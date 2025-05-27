#!/usr/bin/env python

"""
save data from USAXS Fly scans in NeXus HDF5 files

PUBLIC FUNCTIONS

    ~get_manager
    ~reset_manager

INTERNAL

    ~NeXus_Structure
    ~getGroupObjectByXmlNode
    ~Field_Specification
    ~Group_Specification
    ~Link_Specification
    ~PV_Specification
    ~_developer

"""

import logging
import os

# ensure we have a location for the libca (& libCom) library
# os.environ["PYEPICS_LIBCA"] = "/APSshare/epics/base-7.0.3/lib/linux-x86_64/libca.so"
import socket
import time

from lxml import etree as lxml_etree
from ophyd import Component
from ophyd import EpicsSignal

os.environ["PYEPICS_LIBCA"] = "/local/epics/base-7.0.6.1/lib/linux-x86_64/libca.so"

logger = logging.getLogger(os.path.split(__file__)[-1])
logger.setLevel(logging.INFO)
# logger.addHandler(logging.NullHandler())

COMMON_AD_CONFIG_DIR = "/share1/AreaDetectorConfig/FlyScan_config/"
path = os.path.dirname(__file__)
XML_CONFIGURATION_FILE = os.path.join(COMMON_AD_CONFIG_DIR, "saveFlyData.xml")
XSD_SCHEMA_FILE = os.path.join(path, "saveFlyData.xsd")
TRIGGER_POLL_INTERVAL_s = 0.1

manager = None  # singleton instance of NeXus_Structure


class EpicsSignalDesc(EpicsSignal):
    """A specialized EpicsSignal that includes a description component.

    This class extends EpicsSignal to add a description field that can be used
    to store metadata about the signal.
    """

    desc = Component(EpicsSignal, ".DESC")


def reset_manager():
    """
    clear the NeXus structure manager

    The configuration file must be parsed the next time the
    structure manager object is requested using ``get_manager()``.
    """
    global manager
    logger.debug("reset NeXus structure manager")
    manager = None


def get_manager(config_file):
    """
    return a reference to the NeXus structure manager

    If the manager is not defined (``None``), then create a
    new instance of ``NeXus_Structure()``.
    """
    global manager
    if manager is None:
        logger.debug("create new NeXus structure manager instance")
        manager = NeXus_Structure(config_file)
    return manager


class NeXus_Structure:
    """
    Parse XML configuration, layout structure of HDF5 file, define PVs in ophyd.

    This class manages the NeXus structure for HDF5 files, including parsing XML
    configuration files and managing PV connections.
    """

    def __init__(self, config_file):
        """Initialize the NeXus structure from an XML configuration file.

        Args:
            config_file: Path to the XML configuration file
        """
        self.config_filename = config_file
        self.configured = False

        # key: node/@label, value: Field_Specification object
        self.field_registry = {}
        # key: HDF5 absolute path, value: Group_Specification object
        self.group_registry = {}
        # key: node/@label, value: Link_Specification object
        self.link_registry = {}
        self.pv_registry = {}  # key: node/@label,        value: PV_Specification object

    def _read_configuration(self):
        # first, validate configuration file against an XML Schema
        path = os.path.split(os.path.abspath(__file__))[0]
        xml_schema_file = os.path.join(path, XSD_SCHEMA_FILE)
        logger.debug(f"XML Schema file: {xml_schema_file}")
        xmlschema_doc = lxml_etree.parse(xml_schema_file)
        xmlschema = lxml_etree.XMLSchema(xmlschema_doc)

        logger.debug(f"XML configuration file: {self.config_filename}")
        config = lxml_etree.parse(self.config_filename)
        if not xmlschema.validate(config):
            # XML file is not valid, let lxml report what is wrong as an exception
            log = xmlschema.error_log  # access more details
            logger.debug(f"XML file invalid: {log}")
            try:
                xmlschema.assertValid(config)  # basic exception report
            except Exception as err:
                raise RuntimeError(f"XML validation failed: file='{self.config_filename}' {err=}") from err

        # safe to proceed parsing the file
        root = config.getroot()
        if root.tag != "saveFlyData":
            logger.debug(f"XML root tag incorrect: '{root.tag}' != 'saveFlyData'")
            raise RuntimeError("XML file not valid for configuring saveFlyData")

        self.creator_version = root.attrib["version"]
        logger.debug(f"XML file creator version: {self.creator_version}")

        node = root.xpath("/saveFlyData/triggerPV")[0]
        self.trigger_pv = node.attrib["pvname"]
        acceptable_values = (
            int(node.attrib["done_value"]),
            node.attrib["done_text"],
        )
        self.trigger_accepted_values = acceptable_values

        node = root.xpath("/saveFlyData/timeoutPV")[0]
        self.timeout_pv = node.attrib["pvname"]
        logger.debug(f"XML file timeout PV: {self.timeout_pv}")

        # initial default value set in this code
        # pull default poll_interval_s from XML Schema (XSD) file
        xsd_root = xmlschema_doc.getroot()
        xsd_node = xsd_root.xpath(
            "//xs:attribute[@name='poll_time_s']",  # name="poll_time_s"
            namespaces={"xs": "http://www.w3.org/2001/XMLSchema"},
        )

        # allow XML configuration to override default trigger_poll_interval_s
        default_value = float(xsd_node[0].get("default", TRIGGER_POLL_INTERVAL_s))
        self.trigger_poll_interval_s = node.get("poll_time_s", default_value)
        logger.debug(f"trigger_poll_interval_s: {self.trigger_poll_interval_s}")

        nx_structure = root.xpath("/saveFlyData/NX_structure")[0]
        for node in nx_structure.xpath("//group"):
            Group_Specification(node, self)

        for node in nx_structure.xpath("//field"):
            Field_Specification(node, self)

        for node in nx_structure.xpath("//PV"):
            PV_Specification(node, self)

        for node in nx_structure.xpath("//link"):
            Link_Specification(node, self)

        self.configured = True

    def _connect_ophyd(self):
        """Connect all PVs using ophyd signals.

        Creates EpicsSignal or EpicsSignalDesc instances for each PV in the registry.
        """
        for i, pv in enumerate(self.pv_registry.values()):
            oname = f"metadata_{i+1:04d}"
            if pv.pvname.find(".") < 0:
                creator = EpicsSignalDesc
            else:
                # includes a field as part of pvname
                # cannot attach .DESC as suffix to this
                creator = EpicsSignal
            pv.ophyd_signal = creator(pv.pvname, name=oname)

    @property
    def connected(self):
        """Check if all PVs are connected.

        Returns:
            bool: True if all PVs are connected, False otherwise
        """
        arr = [pv.ophyd_signal.connected for pv in self.pv_registry.values()]
        return False not in arr

    @property
    def unconnected_signals(self):
        """Get list of ophyd EpicsSignal objects that are not connected.

        Returns:
            list: List of PV_Specification objects for unconnected signals
        """
        disconnects = [
            pv
            # .
            for pv in self.pv_registry.values()
            if not pv.ophyd_signal.connected
        ]
        return disconnects

    def get_hdf5_path(self, xml_node):
        """Get the HDF5 path for a given XML node.

        Args:
            xml_node: XML node to get the HDF5 path for

        Returns:
            str: The HDF5 path for the given node
        """
        for group_spec_obj in self.group_registry.values():
            if group_spec_obj.xml_node == xml_node:
                return group_spec_obj.hdf5_path
        return None

    def __getitem__(self, key):
        """Get a NeXus structure item by key.

        Args:
            key: Key to look up in the structure

        Returns:
            The requested item from the NeXus structure

        Raises:
            KeyError: If the key is not found
        """
        return self.get_hdf5_path(key)

    def __len__(self):
        """Get the number of items in the NeXus structure.

        Returns:
            int: Number of items in the structure
        """
        return len(self.group_registry)

    def __iter__(self):
        """Get an iterator over the NeXus structure items.

        Returns:
            iterator: Iterator over the structure items
        """
        return iter(self.group_registry.values())

    def __str__(self):
        """Get a string representation of the NeXus structure.

        Returns:
            str: String representation of the structure
        """
        return f"NeXus_Structure(config='{self.config_filename}')"


def getGroupObjectByXmlNode(xml_node, manager):
    """locate a Group_Specification object by matching its xml_node"""
    for group_spec_obj in manager.group_registry.values():
        if group_spec_obj.xml_node == xml_node:
            return group_spec_obj
    return None


class Field_Specification:
    """
    Specification of the "field" element in the XML configuration.

    This class represents a "field" element in the XML configuration and
    generates appropriate structures in the HDF5 file.
    """

    def __init__(self, xml_element_node, manager):
        """Initialize a field specification from an XML node.

        Args:
            xml_element_node: XML node containing field configuration
            manager: NeXus_Structure instance managing this field
        """
        self.xml_node = xml_element_node
        xml_parent_node = xml_element_node.getparent()
        self.group_parent = getGroupObjectByXmlNode(xml_parent_node, manager)
        self.name = xml_element_node.attrib["name"]
        self.hdf5_path = self.group_parent.hdf5_path + "/" + self.name

        nodes = xml_element_node.xpath("text")
        self.text = "" if len(nodes) == 0 else nodes[0].text.strip()
        self.attrib = {
            node.attrib["name"]: node.attrib["value"]
            # .
            for node in xml_element_node.xpath("attribute")
        }

        manager.field_registry[self.hdf5_path] = self

    def __str__(self):
        """Get a string representation of the field specification.

        Returns:
            str: String representation of the field
        """
        try:
            address = self.hdf5_path
            text = f"{address=!r}"
        except Exception:
            text = ""
        return f"{self.__class__.__name__}({text})"


class Group_Specification:
    """
    Specification of the "group" element in the XML configuration.

    This class represents a "group" element in the XML configuration and
    generates appropriate structures in the HDF5 file.
    """

    def __init__(self, xml_element_node, manager):
        """Initialize a group specification from an XML node.

        Args:
            xml_element_node: XML node containing group configuration
            manager: NeXus_Structure instance managing this group
        """
        self.xml_node = xml_element_node
        self.hdf5_path = None
        self.hdf5_group = None
        self.name = xml_element_node.attrib["name"]
        self.nx_class = xml_element_node.attrib["class"]

        self.attrib = {
            node.attrib["name"]: node.attrib["value"]
            # .
            for node in xml_element_node.xpath("attribute")
        }

        xml_parent_node = xml_element_node.getparent()
        self.group_children = {}
        if xml_parent_node.tag == "group":
            # identify our parent
            self.group_parent = getGroupObjectByXmlNode(xml_parent_node, manager)
            # next, find our HDF5 path from our parent
            path = self.group_parent.hdf5_path
            if not path.endswith("/"):
                path += "/"
            self.hdf5_path = path + self.name
            # finally, declare ourself to be a child of that parent
            self.group_parent.group_children[self.hdf5_path] = self
        elif xml_parent_node.tag == "NX_structure":
            self.group_parent = None
            self.hdf5_path = "/"

        if self.hdf5_path in manager.group_registry:
            msg = "Cannot create duplicate HDF5 path names: path=%s name=%s nx_class=%s" % (
                self.hdf5_path,
                self.name,
                self.nx_class,
            )
            raise RuntimeError(msg)

        manager.group_registry[self.hdf5_path] = self

    def __str__(self):
        """Get a string representation of the group specification.

        Returns:
            str: String representation of the group
        """
        try:
            address = self.hdf5_path
            text = f"{address=!r}"
        except Exception:
            text = ""
        return f"{self.__class__.__name__}({text})"


class Link_Specification:
    """
    Specification of the "link" element in the XML configuration.

    This class represents a "link" element in the XML configuration and
    generates appropriate structures in the HDF5 file.
    """

    def __init__(self, xml_element_node, manager):
        """Initialize a link specification from an XML node.

        Args:
            xml_element_node: XML node containing link configuration
            manager: NeXus_Structure instance managing this link
        """
        self.xml_node = xml_element_node

        self.name = xml_element_node.attrib["name"]
        self.source_hdf5_path = xml_element_node.attrib["source"]  # path to existing object
        self.linktype = xml_element_node.get("linktype", "NeXus")
        if self.linktype not in ("NeXus",):
            msg = "Cannot create HDF5 " + self.linktype + " link: " + self.hdf5_path
            raise RuntimeError(msg)

        xml_parent_node = xml_element_node.getparent()
        self.group_parent = getGroupObjectByXmlNode(xml_parent_node, manager)
        self.name = xml_element_node.attrib["name"]
        self.hdf5_path = self.group_parent.hdf5_path + "/" + self.name

        manager.link_registry[self.hdf5_path] = self

    def make_link(self, hdf_file_object):
        """
        Create a NeXus-style HDF5 link within the file.

        Args:
            hdf_file_object: HDF5 file object to create the link in
        """
        source = self.source_hdf5_path  # source: existing HDF5 object
        parent = "/".join(source.split("/")[0:-1])  # parent: parent HDF5 path of source
        target = self.hdf5_path  # target: HDF5 node path to be created
        parent_obj = hdf_file_object[parent]
        source_obj = hdf_file_object[source]

        str_source = str(source_obj.name).encode("utf-8")
        str_target = target.encode("utf-8")
        if "target" not in source_obj.attrs:
            # NeXus link, NOT an HDF5 link!
            source_obj.attrs["target"] = str_source
        parent_obj[str_target] = parent_obj[str_source]

    def __str__(self):
        """Get a string representation of the link specification.

        Returns:
            str: String representation of the link
        """
        try:
            source = self.source_hdf5_path
            target = self.hdf5_path
            text = f"{source=!r}, {target=!r}"
        except Exception:
            text = ""
        return f"{self.__class__.__name__}({text})"


class PV_Specification:
    """
    Specification of the "PV" element in the XML configuration.

    This class represents a "PV" (EPICS Process Variable) element in the XML
    configuration and generates appropriate ophyd and other structures so its
    data may be recorded properly in the HDF5 file.
    """

    def __init__(self, xml_element_node, manager):
        """Initialize a PV specification from an XML node.

        Args:
            xml_element_node: XML node containing PV configuration
            manager: NeXus_Structure instance managing this PV
        """
        self.xml_node = xml_element_node

        self.label = xml_element_node.attrib["label"]
        if self.label in manager.pv_registry:
            msg = "Cannot use PV label more than once: " + self.label
            raise RuntimeError(msg)
        self.pvname = xml_element_node.attrib["pvname"]
        self.as_string = xml_element_node.attrib.get("string", "false").lower() in ("t", "true")
        # _s = xml_element_node.attrib.get('string', "false")
        # print(f"PV: {self.pvname}  string:{self.as_string}  node:{_s}")
        self.pv = None
        self.ophyd_signal = None
        aas = xml_element_node.attrib.get("acquire_after_scan", "false")
        self.acquire_after_scan = aas.lower() in ("t", "true")

        self.attrib = {node.attrib["name"]: node.attrib["value"] for node in xml_element_node.xpath("attribute")}

        # identify our parent
        xml_parent_node = xml_element_node.getparent()
        self.group_parent = getGroupObjectByXmlNode(xml_parent_node, manager)

        self.length_limit = xml_element_node.get("length_limit", None)
        if self.length_limit is not None:
            if not self.length_limit.startswith("/"):
                # convert local to absolute reference
                self.length_limit = self.group_parent.hdf5_path + "/" + self.length_limit

        # finally, declare ourself to be a child of that parent
        self.hdf5_path = self.group_parent.hdf5_path + "/" + self.label
        self.group_parent.group_children[self.hdf5_path] = self

        manager.pv_registry[self.hdf5_path] = self

    def __str__(self):
        """Get a string representation of the PV specification.

        Returns:
            str: String representation of the PV
        """
        try:
            text = f"label={self.label!r}, PV={self.pvname!r}"
        except Exception:
            text = ""
        return f"{self.__class__.__name__}({text})"


def _developer():
    """
    developer's scratch space
    """
    print("basic tests while developing this module")
    assert manager is None, "starting condition should be None"

    config_file = XML_CONFIGURATION_FILE

    boss = get_manager(config_file)
    assert isinstance(boss, NeXus_Structure), "new structure created"

    mgr = get_manager(config_file)
    assert isinstance(mgr, NeXus_Structure), "existing structure"
    assert boss == mgr, "identical to first structure"

    reset_manager()
    assert manager is None, "structure reset"

    mgr = get_manager(config_file)
    assert isinstance(mgr, NeXus_Structure), "new structure created"
    assert boss != mgr, "new structure different from first structure"
    del boss

    mgr._read_configuration()
    assert mgr.trigger_poll_interval_s == TRIGGER_POLL_INTERVAL_s
    assert len(mgr.pv_registry) > 0

    t0 = time.time()
    timeout = 2.0
    mgr._connect_ophyd()
    for _i in range(500):  # limited wait to connect
        verdict = mgr.connected
        t = time.time() - t0
        logger.debug(f"connected: {verdict}  time:{t}")
        if verdict or t > timeout:
            break  # seems to take about 60-70 ms with current XML file
        time.sleep(0.005)

    workstation = socket.gethostname()
    if workstation.find("usaxscontrol") >= 0:
        assert mgr.connected

    conn = [pv for pv in mgr.pv_registry.values() if pv.ophyd_signal.connected]
    msg = f"connected {len(conn)} of {len(mgr.pv_registry)} PVs " f"in {time.time()-t0:.04f} s"
    logger.debug(msg)


# if __name__ == "__main__":
#    logging.basicConfig(level=logging.DEBUG)
#    _developer()
