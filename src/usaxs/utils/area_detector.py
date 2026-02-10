"""Utilities supporting area detectors."""

import datetime
import pathlib
from typing import Iterator

from apsbits.core.instrument_init import oregistry
from ophyd.areadetector import DetectorBase
from ophyd.areadetector import FilePlugin


def all_area_detectors() -> Iterator[DetectorBase]:
    """Yield all area detectors from the 'oregistry'."""
    for dname in oregistry.device_names:
        detector = oregistry[dname]
        if not isinstance(detector, DetectorBase):
            continue
        # print(f"{dname=}")
        yield detector


def area_detector_file_plugins(detector: DetectorBase) -> Iterator[FilePlugin]:
    """Yield all file plugins of the area detector."""
    for cname in detector.component_names:
        component = getattr(detector, cname)
        if not isinstance(component, FilePlugin):
            continue
        # print(f"{detector.name}.{cname}")
        yield component


def path_template_fixer(plugin: FilePlugin) -> None:
    """Set write_path_template & read_path_templates from EPICS PV."""
    # Consider file_path PV might have calendar format codes.
    formatter = datetime.datetime.now().strftime
    ioc_write_path = formatter(plugin.file_path.get())

    # Replace the write_path_template and read_path_template.
    path = pathlib.Path(ioc_write_path)
    parts = list(path.parts)
    if "USAXS_data" in parts:
        plugin.write_path_template = ioc_write_path

        idx = parts.index("USAXS_data")
        new_parts = tuple(["/share1"] + parts[idx:])
        plugin.read_path_template = str(pathlib.Path(*new_parts))
