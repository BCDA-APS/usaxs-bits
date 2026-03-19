"""
Demo SPEC file writer callback for the 12-ID-E USAXS instrument.

This module is a template/demo for subscribing a SPEC file writer to the
Bluesky RunEngine.  The production SPEC writer path goes through
``setup_new_user.newUser()`` / ``setup_new_user.newSample()``, which call
``_setSpecFileName()`` directly.

Module-level objects
--------------------
specwriter : SpecWriterCallback2 (or SpecWriterCallback for apstools <1.6.21)
    The SPEC file writer instance.  Imported by ``setup_new_user`` and other
    modules that need to interact with the active SPEC file.

Public functions
----------------
spec_comment(comment, doc)
    Insert a free-text comment into the current SPEC file.
newSpecFile(title, scan_id, RE)
    Create (or append to) a date-prefixed SPEC file in the current directory.
init_specwriter_with_RE(RE)
    Subscribe ``specwriter`` to the RunEngine and add a motor-position
    preprocessor (requires apstools ≥1.6.14).

Config keys used (under ``SPEC_DATA_FILES``):
    ENABLE          : bool — subscribe to RE (default False)
    FILE_EXTENSION  : str  — output file extension (default "dat")
"""

import datetime
import logging
import pathlib
from typing import Any
from typing import Optional

import apstools.callbacks
import apstools.utils

from apsbits.utils.config_loaders import get_config

logger = logging.getLogger(__name__)
logger.bsdev(__file__)  # custom level added by apsbits at import time

iconfig = get_config()
file_extension = iconfig.get("SPEC_DATA_FILES", {}).get("FILE_EXTENSION", "dat")


def spec_comment(comment: str, doc: Optional[Any] = None) -> None:
    """Insert a free-text comment into the current SPEC data file.

    Delegates to ``apstools.callbacks.spec_comment``, passing the module-level
    ``specwriter`` instance.

    Parameters
    ----------
    comment : str
        Text to write as a SPEC comment line.
    doc : dict, optional
        Bluesky document to associate the comment with, if any.
    """
    apstools.callbacks.spec_comment(comment, doc, specwriter)


def newSpecFile(
    title: str, scan_id: Optional[int] = None, RE: Optional[Any] = None
) -> None:
    """Create or append to a date-prefixed SPEC file in the current directory.

    The filename is constructed as ``MM_DD_<title>.<ext>``, where the title is
    sanitised with ``apstools.utils.cleanupText`` and the extension comes from
    ``iconfig["SPEC_DATA_FILES"]["FILE_EXTENSION"]`` (default ``"dat"``).

    Parameters
    ----------
    title : str
        Base name for the SPEC file (will be sanitised).
    scan_id : int, optional
        Starting scan number.  Ignored if the file already exists (the last
        scan number in the existing file is used instead).
    RE : bluesky.RunEngine, optional
        If provided, ``RE.md["scan_id"]`` is updated to match.

    Notes
    -----
    If the file already exists a warning is logged and scans are appended.
    """
    kwargs = {}
    if RE is not None:
        kwargs["RE"] = RE

    mmdd = str(datetime.datetime.now()).split()[0][5:].replace("-", "_")
    clean = apstools.utils.cleanupText(title)
    fname = pathlib.Path(f"{mmdd}_{clean}.{file_extension}")
    if fname.exists():
        logger.warning(">>> file already exists: %s <<<", fname)
        handled = "appended"
    else:
        kwargs["scan_id"] = scan_id or 1
        handled = "created"

    specwriter.newfile(fname, **kwargs)

    logger.info("SPEC file name : %s", specwriter.spec_filename)
    logger.info("File will be %s at end of next bluesky scan.", handled)


def init_specwriter_with_RE(RE: Any) -> None:
    """Subscribe the SPEC writer to the RunEngine and add motor preprocessor.

    Opens the current ``specwriter.spec_filename`` for writing, subscribes
    ``specwriter.receiver`` to *RE* if ``SPEC_DATA_FILES.ENABLE`` is true in
    ``iconfig``, and appends a ``motor_start_preprocessor`` that records all
    motor positions at the start of each run (requires apstools ≥1.6.14).

    Parameters
    ----------
    RE : bluesky.RunEngine
        The active RunEngine instance.
    """
    # make the SPEC file in current working directory (assumes is writable)
    specwriter.newfile(specwriter.spec_filename)

    if iconfig.get("SPEC_DATA_FILES", {}).get("ENABLE", False):
        RE.subscribe(specwriter.receiver)  # write data to SPEC files
        logger.info("SPEC data file: %s", specwriter.spec_filename.resolve())

    try:
        # feature new in apstools 1.6.14
        from apstools.plans import label_stream_wrapper

        def motor_start_preprocessor(plan):
            """Record motor positions at start of each run."""
            return label_stream_wrapper(plan, "motor", when="start")

        RE.preprocessors.append(motor_start_preprocessor)
    except Exception:
        logger.warning("Could not load support to log motors positions.")


# write scans to SPEC data file
try:
    # apstools >=1.6.21
    _specwriter = apstools.callbacks.SpecWriterCallback2()
except AttributeError:
    # apstools <1.6.21
    _specwriter = apstools.callbacks.SpecWriterCallback()

# The SPEC file writer object, imported by other modules (e.g. setup_new_user).
specwriter = _specwriter
