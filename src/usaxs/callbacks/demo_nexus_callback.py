"""
Demo NeXus file writer callback for the 12-ID-E USAXS instrument.

This module is a template/demo showing how to subscribe a NeXus file writer
to the Bluesky RunEngine.  It is not the primary data-writing path for USAXS
scans (that is handled by ``nxwriter_usaxs.py``).

``MyNXWriter`` subclasses ``apstools.callbacks.NXWriter`` (or ``NXWriterAPS``
when running on the APS subnet) to override only ``get_sample_title()``,
reading the title from scan metadata when available.

``nxwriter_init(RE)`` is the setup function: it instantiates ``MyNXWriter``,
subscribes it to the RunEngine if enabled in ``iconfig``, and applies
file-extension and missing-content-warning settings from the config.

Config keys used (under ``NEXUS_DATA_FILES``):
    ENABLE          : bool  — subscribe to RE (default False)
    FILE_EXTENSION  : str   — output file extension (default "hdf")
    WARN_MISSING    : bool  — warn on missing NeXus fields (default False)
"""

import logging
from typing import Any

from apstools.utils import host_on_aps_subnet

from apsbits.utils.config_loaders import get_config

logger = logging.getLogger(__name__)
logger.bsdev(__file__)  # custom level added by apsbits at import time

# Get the configuration
iconfig = get_config()


if host_on_aps_subnet():
    from apstools.callbacks import NXWriterAPS as NXWriter
else:
    from apstools.callbacks import NXWriter


class MyNXWriter(NXWriter):
    """NeXus writer with sample title read from scan metadata.

    Overrides ``get_sample_title()`` so that plans which store a ``"title"``
    key in ``RE.md`` (or pass it via ``md=`` to a scan) will have that title
    used in the NeXus file rather than the auto-generated default.
    """

    def get_sample_title(self) -> str:
        """Return the sample title for the NeXus file.

        Tries ``self.metadata["title"]`` first.  Falls back to a constructed
        string ``S{scan_id:05d}-{plan_name}-{uid[:7]}`` if the key is absent,
        matching the format of the apstools default but with zero-padded scan ID.

        Returns
        -------
        str
            Sample title string written into the NeXus ``/entry/title`` field.
        """
        try:
            title = self.metadata["title"]
        except KeyError:
            title = f"S{self.scan_id:05d}-{self.plan_name}-{self.uid[:7]}"
        return title


def nxwriter_init(RE: Any) -> Any:
    """Instantiate and configure the NeXus file writer callback.

    Creates a ``MyNXWriter`` instance, subscribes it to *RE* if
    ``NEXUS_DATA_FILES.ENABLE`` is true in ``iconfig``, and applies
    file-extension and warning settings from config.

    Parameters
    ----------
    RE : bluesky.RunEngine
        The active RunEngine instance.

    Returns
    -------
    MyNXWriter
        The configured writer instance (also subscribed to RE if enabled).
    """
    nxwriter = MyNXWriter()  # create the callback instance

    if iconfig.get("NEXUS_DATA_FILES", {}).get("ENABLE", False):
        RE.subscribe(nxwriter.receiver)  # write data to NeXus files

    nxwriter.file_extension = iconfig.get("NEXUS_DATA_FILES", {}).get(
        "FILE_EXTENSION", "hdf"
    )

    logger.debug("nxwriter file_extension: %s", nxwriter.file_extension)
    warn_missing = iconfig.get("NEXUS_DATA_FILES", {}).get("WARN_MISSING", False)
    nxwriter.warn_on_missing_content = warn_missing

    return nxwriter
