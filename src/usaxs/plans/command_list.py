"""Command list execution and management module.

This module provides functionality to run batches of scans from command lists,
including parsing Excel and text command files, executing commands, and managing
the scanning process.
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from typing import Any
from typing import Generator

import pyRestTable
from apsbits.utils.controls_setup import oregistry
from apstools.utils import ExcelDatabaseFileGeneric
from apstools.utils import rss_mem
from bluesky import plan_stubs as bps
from IPython import get_ipython
from ophyd import Signal

from ..misc.amplifiers import measure_background
from ..usaxs_support.nexus import reset_manager
from ..usaxs_support.surveillance import instrument_archive
from ..utils.quoted_line import split_quoted_line
from .axis_tuning import instrument_default_tune_ranges
from .axis_tuning import update_EPICS_tuning_widths
from .axis_tuning import user_defined_settings
from .doc_run import documentation_run
from .mode_changes import mode_BlackFly
from .mode_changes import mode_Radiography
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .mode_changes import mode_WAXS
from .requested_stop import RequestAbort

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
a_shutter_autoopen = oregistry["a_shutter_autoopen"]
constants = oregistry["constants"]
email_notices = oregistry["email_notices"]
saxs_det = oregistry["saxs_det"]
terms = oregistry["terms"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
user_data = oregistry["user_data"]
waxs_det = oregistry["waxs_det"]
s_stage = oregistry["s_stage"]
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
trd_controls = oregistry["trd_controls"]
upd_controls = oregistry["upd_controls"]

__all__ = """
    after_command_list
    after_plan
    before_command_list
    before_plan
    beforeScanComputeOtherStuff
    command_list_as_table
    execute_command_list
    get_command_list
    parse_Excel_command_file
    parse_text_command_file
    postCommandsListfile2WWW
    run_command_file
    run_python_file
    run_set_command
    summarize_command_file
    sync_order_numbers
""".split()

MAXIMUM_ATTEMPTS = 1  # (>=1): try command list item no more than this many attempts


def beforeScanComputeOtherStuff() -> Generator:
    """Actions before each data collection starts."""
    yield from bps.null()  # TODO: remove this once you add the "other stuff"


def postCommandsListfile2WWW(commands: list[tuple]) -> Generator:
    """Post list of commands to WWW and archive the list for posterity."""
    tbl_file = "commands.txt"
    tbl = command_list_as_table(commands)
    timestamp = datetime.datetime.now().isoformat().replace("T", " ")
    file_contents = "bluesky command sequence\n"
    file_contents += f"written: {timestamp}\n"
    file_contents += str(tbl.reST())

    # post for livedata page
    # path = "/tmp"
    path = "/share1/local_livedata"
    with open(os.path.join(path, tbl_file), "w") as fp:
        fp.write(file_contents)

    # post to EPICS
    yield from bps.mv(
        user_data.macro_file,
        os.path.split(tbl_file)[-1],
        user_data.macro_file_time,
        timestamp,
    )

    # keep this list for posterity
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = "/share1/log/macros"
    posterity_file = f"{timestamp}-{tbl_file}"
    with open(os.path.join(path, posterity_file), "w") as fp:
        fp.write(file_contents)


def before_command_list(
    md: dict | None = None, commands: list[tuple] | None = None
) -> Generator:
    """Execute preparatory actions before running a command list.

    This function performs several initialization steps before executing a command list:
    1. Verifies commands if provided
    2. Updates timestamps and collection status
    3. Configures shutters and controls
    4. Measures dark currents if enabled
    5. Sets up tuning ranges and updates EPICS settings
    6. Performs pre-USAXS tuning if requested
    7. Synchronizes order numbers if enabled

    Parameters
    ----------
    md : dict | None, optional
        Metadata dictionary to be used during the scan, by default None
    commands : list[tuple] | None, optional
        List of command tuples to be verified, by default None

    Yields
    ------
    Generator
        Bluesky plan for executing the preparatory actions
    """
    from .scans import preUSAXStune

    if commands is not None:
        verify_commands(commands)

    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        user_data.collection_in_progress,
        1,
    )

    yield from user_data.set_state_plan("Starting data collection")

    yield from bps.mv(
        ti_filter_shutter,
        "close",
        terms.SAXS.collecting,
        0,
        terms.WAXS.collecting,
        0,
        a_shutter_autoopen,
        1,
    )

    if constants["MEASURE_DARK_CURRENTS"]:
        yield from measure_background(
            [upd_controls, I0_controls, I00_controls, trd_controls],
        )

    # reset the ranges to be used when tuning optical axes (issue #129)
    # These routines are defined in file: 29-axis-tuning.py
    yield from instrument_default_tune_ranges()
    yield from user_defined_settings()
    yield from update_EPICS_tuning_widths()

    yield from beforeScanComputeOtherStuff()  # 41-commands.py

    if terms.preUSAXStune.run_tune_on_qdo.get():
        logger.info("Running preUSAXStune as requested at start of measurements")
        yield from preUSAXStune(md=md)

    if constants["SYNC_ORDER_NUMBERS"]:
        yield from sync_order_numbers()

    if commands is not None:
        yield from postCommandsListfile2WWW(commands)

    # force the next FlyScan to reload the metadata configuration
    # which forces a (re)connection to the EPICS PVs
    reset_manager()


def verify_commands(commands: list[tuple]) -> None:
    """Verify the validity of command input parameters.

    This function checks each command in the list for:
    1. Valid scan action types
    2. Proper numeric values for coordinates and thickness
    3. Stage travel limits for X and Y coordinates
    4. Sample thickness validity
    5. Sample name presence

    Parameters
    ----------
    commands : list[tuple]
        List of command tuples, where each tuple contains:
        (action, args, line_number, raw_command)

    Raises
    ------
    RuntimeError
        If any command validation fails, with detailed error messages
    """
    # create string for error logging
    list_of_errors = []
    # separate commands into individual components, see execute_command_list for details
    scan_actions = "flyscan usaxsscan saxs saxsexp waxs waxsexp".split()
    for command in commands:
        action, args, i, raw_command = command
        if action.lower() in scan_actions:
            try:
                sx = float(args[0])
                sy = float(args[1])
                sth = float(args[2])
                # Verify sample name exists but don't use it
                _ = args[3]
            except (IndexError, ValueError) as exc:
                list_of_errors.append(
                    f"line {i}: Improper command : {raw_command.strip()} : {exc}"
                )
                continue
            # check sx against travel limits
            if sx < s_stage.x.low_limit:
                list_of_errors.append(
                    f"line {i}: SX low limit: value {sx} < low limit "
                    f"{s_stage.x.low_limit},  command: {raw_command.strip()}"
                )
            if sx > s_stage.x.high_limit:
                list_of_errors.append(
                    f"line {i}: SX high limit: value {sx} > high limit "
                    f"{s_stage.x.high_limit},  command: {raw_command.strip()}"
                )
            # check sy against travel limits
            if sy < s_stage.y.low_limit:
                list_of_errors.append(
                    f"line {i}: SY low limit: value {sy} < low limit "
                    f"{s_stage.y.low_limit},  command: {raw_command.strip()}"
                )
            if sy > s_stage.y.high_limit:
                list_of_errors.append(
                    f"line {i}: SY high limit: value {sy} > high limit "
                    f"{s_stage.y.high_limit},  command: {raw_command.strip()}"
                )
            # check sth for reasonable sample thickness value
            if sth < 0:
                print(
                    f"{sth = } from args[2] = float('{args[2]}') -- thickness problem"
                )
    if len(list_of_errors) > 0:
        err_msg = (
            "Errors were found in command file. Cannot continue. List of errors:\n"
            + "\n".join(list_of_errors)
        )
        raise RuntimeError(err_msg)
    logger.info("Command file verified")


def after_command_list(md: dict | None = None) -> Generator:
    """Execute cleanup actions after running a command list.

    This function performs several cleanup steps:
    1. Updates timestamps
    2. Marks collection as complete
    3. Closes shutters
    4. Updates system state

    Parameters
    ----------
    md : dict | None, optional
        Metadata dictionary used during the scan, by default None

    Yields
    ------
    Generator
        Bluesky plan for executing the cleanup actions
    """
    # if md is None:
    #     md = {}
    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        user_data.collection_in_progress,
        0,
        ti_filter_shutter,
        "close",
    )
    yield from user_data.set_state_plan("USAXS macro file done")


def before_plan(md: dict | None = None) -> Generator:
    """Execute preparatory actions before each data collection plan.

    This function:
    1. Determines the current mode (USAXS or SWAXS)
    2. Performs appropriate tuning based on the mode

    Parameters
    ----------
    md : dict | None, optional
        Metadata dictionary to be used during the scan, by default None

    Yields
    ------
    Generator
        Bluesky plan for executing the preparatory actions
    """
    from .scans import preSWAXStune
    from .scans import preUSAXStune

    if terms.preUSAXStune.needed:
        # tune at previous sample position
        # don't overexpose the new sample position
        # select between positions
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        if mode_now == "USAXS in beam":
            yield from preUSAXStune(md=md)
        else:
            yield from preSWAXStune(md=md)


def after_plan(weight: int = 1, md: dict | None = None) -> Generator:
    """Execute cleanup actions after each data collection plan.

    This function:
    1. Increments the number of scans since last tune

    Parameters
    ----------
    weight : int, optional
        Weight to increment the scan counter by, by default 1
    md : dict | None, optional
        Metadata dictionary used during the scan, by default None

    Yields
    ------
    Generator
        Bluesky plan for executing the cleanup actions
    """

    yield from bps.mv(  # increment it
        terms.preUSAXStune.num_scans_last_tune,
        terms.preUSAXStune.num_scans_last_tune.get() + weight,
    )


def parse_Excel_command_file(filename: str) -> list[tuple]:
    """Parse an Excel spreadsheet containing scan commands.

    The spreadsheet should be formatted with the following columns:
    - scan: The type of scan to perform
    - sx: Sample X position
    - sy: Sample Y position
    - thickness: Sample thickness
    - sample name: Name or description of the sample

    Example spreadsheet format:
    ```
    List of sample scans to be run

    scan    sx  sy  thickness   sample name
    FlyScan 0   0   0          blank
    FlyScan 5   2   0          blank
    ```

    Parameters
    ----------
    filename : str
        Path to the Excel spreadsheet file. Can be relative or absolute path.

    Returns
    -------
    list[tuple]
        List of command tuples, where each tuple contains:
        (action, args, line_number, raw_command)
    """
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    xl = ExcelDatabaseFileGeneric(full_filename)

    commands = []

    if len(xl.db) > 0:
        for i, row in enumerate(xl.db.values()):
            action, *values = list(row.values())

            # trim off any None values from end
            while len(values) > 0:
                if values[-1] is not None:
                    break
                values = values[:-1]

            commands.append((action, values, i + 1, list(row.values())))

    return commands


def parse_text_command_file(filename: str) -> list[tuple]:
    """
    Parse a text file with commands, return as command list.

    * The text file is interpreted line-by-line.
    * Blank lines are ignored.
    * A pound sign (#) marks the rest of that line as a comment.
    * All remaining lines are interpreted as commands with arguments.

    Example of text file (no line numbers shown)::

        #List of sample scans to be run
        # pound sign starts a comment (through end of line)

        # action  value
        mono_shutter open

        # action  x y width height
        uslits 0 0 0.4 1.2

        # action  sx  sy  thickness   sample name
        FlyScan 0   0   0   blank
        FlyScan 5   2   0   "empty container"

        # action  sx  sy  thickness   sample name
        SAXS 0 0 0 blank

        # action  value
        mono_shutter close

    PARAMETERS

    filename : str
        Name of input text file.  Can be relative or absolute path,
        such as "actions.txt", "../sample.txt", or
        "/path/to/overnight.txt".

    RETURNS

    list of commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    RAISES

    FileNotFoundError
        if file cannot be found
    """
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    with open(full_filename, "r") as fp:
        buf = fp.readlines()

    commands = []
    for i, raw_command in enumerate(buf):
        row = raw_command.strip()
        if row == "" or row.startswith("#"):
            continue  # comment or blank

        else:  # command line
            action, *values = split_quoted_line(row)
            commands.append((action, values, i + 1, raw_command.rstrip()))

    return commands


def command_list_as_table(commands: list[tuple]) -> pyRestTable.Table:
    """Format a command list as a :class:`pyRestTable.Table()` object."""
    tbl = pyRestTable.Table()
    tbl.addLabel("line #")
    tbl.addLabel("action")
    tbl.addLabel("parameters")
    for command in commands:
        action, args, line_number = command[:3]
        row = [line_number, action, ", ".join(map(str, args))]
        tbl.addRow(row)
    return tbl


def get_command_list(filename: str) -> list[tuple]:
    """Return command list from either text or Excel file."""
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    try:
        commands = parse_Excel_command_file(filename)
    except Exception:  # TODO: XLRDError
        commands = parse_text_command_file(filename)
    return commands


def summarize_command_file(filename: str) -> None:
    """Print the command list from a text or Excel file."""
    commands = get_command_list(filename)
    logger.info("Command file: %s\n%s", command_list_as_table(commands), filename)


def run_command_file(filename: str, md: dict | None = None) -> Generator:
    """Plan: execute a list of commands from a text or Excel file.

    * Parse the file into a command list
    * yield the command list to the RunEngine (or other)
    """
    if md is None:
        md = {}
    commands = get_command_list(filename)
    yield from execute_command_list(filename, commands, md=md)


def execute_command_list(
    filename: str, commands: list[tuple], md: dict | None = None
) -> Generator:
    """Plan: execute the command list.

    The command list is a tuple described below.

    * Only recognized commands will be executed.
    * Unrecognized commands will be reported as comments.

    Parameters
    ----------
    filename : str
        Name of input text file. Can be relative or absolute path,
        such as "actions.txt", "../sample.txt", or "/path/to/overnight.txt".
    commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    where

    command : tuple
        (action, parameters, line_number, raw_command)
    action: str
        names a known action to be handled
    parameters: list
        List of parameters for the action.
        The list is empty of there are no values
    line_number: int
        line number (1-based) from the input text file
    raw_command: obj (str or list(str)
        contents from input file, such as:
        ``SAXS 0 0 0 blank``
    """
    from .scans import SAXS
    from .scans import WAXS
    from .scans import USAXSscan
    from .scans import allUSAXStune
    from .scans import preUSAXStune

    if md is None:
        md = {}

    full_filename = os.path.abspath(filename)

    if len(commands) == 0:
        yield from bps.null()
        return

    text = f"Command file: {filename}\n"
    text += str(command_list_as_table(commands))
    logger.info(text)
    logger.info("memory report: %s", rss_mem())

    # save the command list as a separate Bluesky run for documentation purposes
    yield from documentation_run(text)

    instrument_archive(text)

    yield from before_command_list(md=md, commands=commands)

    def _handle_actions_(
        action: str,
        args: list,
        _md: dict,
        i: int,
        raw_command: str,
        simple_actions: dict,
    ) -> Generator:
        """Inner function to make try..except clause more clear."""
        if action in ("flyscan", "usaxsscan"):
            # handles either step or fly scan
            sx = float(args[0])
            sy = float(args[1])
            sth = float(args[2])
            snm = args[3]
            _md.update(dict(sx=sx, sy=sy, thickness=sth, title=snm))
            yield from USAXSscan(sx, sy, sth, snm, md=_md)

        elif action in ("saxs", "saxsexp"):
            sx = float(args[0])
            sy = float(args[1])
            sth = float(args[2])
            snm = args[3]
            _md.update(dict(sx=sx, sy=sy, thickness=sth, title=snm))
            yield from SAXS(sx, sy, sth, snm, md=_md)

        elif action in ("waxs", "waxsexp"):
            sx = float(args[0])
            sy = float(args[1])
            sth = float(args[2])
            snm = args[3]
            _md.update(dict(sx=sx, sy=sy, thickness=sth, title=snm))
            yield from WAXS(sx, sy, sth, snm, md=_md)

        elif action in ("run_python", "run"):
            filename = args[0]
            yield from run_python_file(filename, md={})

        elif action in ("set",):
            yield from run_set_command(*args)

        elif action in simple_actions:
            yield from simple_actions[action](md=_md)

        else:
            logger.info("no handling for line %d: %s", i, raw_command)
            yield from bps.null()
        logger.info("memory report: %s", rss_mem())

    for command in commands:
        action, args, i, raw_command = command
        logger.info("file line %d: %s", i, raw_command)
        yield from bps.checkpoint()

        _md = {}
        _md["full_filename"] = full_filename
        _md["filename"] = filename
        _md["line_number"] = i
        _md["action"] = action
        _md["parameters"] = (
            args  # args is shorter than parameters, means the same thing here
        )
        _md["iso8601"] = datetime.datetime.now().isoformat(" ")

        _md.update(md or {})  # overlay with user-supplied metadata

        action = action.lower()
        simple_actions = dict(
            # command names MUST be lower case!
            # TODO: all these should accept a `md` kwarg
            mode_blackfly=mode_BlackFly,
            mode_radiography=mode_Radiography,
            mode_saxs=mode_SAXS,
            mode_usaxs=mode_USAXS,
            mode_waxs=mode_WAXS,
            pi_off=PI_Off,
            pi_onf=PI_onF,
            pi_onr=PI_onR,
            preusaxstune=preUSAXStune,
            allusaxstune=allUSAXStune,
        )

        attempt = 0  # count the number of attempts
        maximum_attempts = MAXIMUM_ATTEMPTS  # set an upper limit
        exit_requested = False

        # see issue #502
        while attempt < maximum_attempts:
            try:
                # call the inner function (above)
                yield from _handle_actions_(
                    action, args, _md, i, raw_command, simple_actions
                )
                break  # leave the while loop
            # TODO: need to handle some Exceptions, fail on others
            except Exception as exc:
                if exc.__class__ in (RequestAbort,):
                    exit_requested = True
                    break  # we requested abort from EPICS
                subject = (
                    f"{exc.__class__.__name__}"
                    f" during attempt {attempt+1} of {maximum_attempts}"
                    f" of command '{command}''"
                )
                body = (
                    f"subject: {subject}"
                    f"\n"
                    f"\ndate: {datetime.datetime.now().isoformat(' ')}"
                    f"\ncommand file: {full_filename}"
                    f"\nline number: {i}"
                    f"\ncommand: {command}"
                    f"\nraw command: {raw_command}"
                    f"\nattempt: {attempt+1} of {maximum_attempts}"
                    f"\nexception: {exc}"
                    f"\n"
                    f"Stopping further processing of this command list.\n"
                )
                logger.error("Exception %s\n%s", subject, body)
                email_notices.send(subject, body)
                attempt += 1
                exit_requested = True  # issue #502: stop if an Exception was noted

        if exit_requested:
            break

    yield from after_command_list(md=md)
    logger.info("memory report: %s", rss_mem())


def sync_order_numbers() -> Generator:
    """
    Synchronize the order numbers between the various detectors.

    Pick the maximum order number from each detector (or
    supported scan technique) and set them all to that number.
    """
    order_number = max(
        terms.FlyScan.order_number.get(),
        saxs_det.hdf1.file_number.get(),
        waxs_det.hdf1.file_number.get(),
    )
    logger.info("Synchronizing detector order numbers to %d", order_number)
    yield from bps.mv(
        terms.FlyScan.order_number,
        order_number,
        saxs_det.hdf1.file_number,
        order_number,
        waxs_det.hdf1.file_number,
        order_number,
    )


def run_python_file(filename: str, md: dict | None = None) -> Generator:
    """
    Plan: load and run a Python file using the IPython `%mov` magic.

    * look for the file relative to pwd or in sys.path
    * %run -i the file (in the ipython shell namespace)
    """
    yield from bps.null()

    # locate `filename` in one of the paths
    candidates = [os.path.abspath(os.path.join(p, filename)) for p in sys.path]
    # first candidate is always relative to pwd
    candidates.insert(0, os.path.abspath(filename))

    for f in candidates:
        if os.path.exists(f):
            logger.info("Running Python file: %s", f)
            get_ipython().run_line_magic("run", f"-i {f}")
            return
    logger.error("Could not find file '%s'", filename)
    if not filename.endswith(".py"):
        logger.warning("Did you forget the '.py' suffix on '%s'?", filename)


def run_set_command(*args: Any) -> Generator:
    """
    Change a general parameter from a command file.

    The general parameter to be set MUST be an attribute of ``terms``.
    The ``instrument.devices.general_terms.terms`` are (mostly)
    EPICS PVs which contain configuration values to be used when they
    are called.  None of these are expected to cause any motion,
    so they should need to be waited upon for completion.
    Uses::

        yield from bps.abs_set(term, value, timeout=0.1, wait=False)

    syntax:  ``SET terms.component value``

    Does not raise an exception.  Instead, logs as _error_ and
    skips further handling of this command.

    NOTE: If you intend to use this signal immediately (as with a
    ``.get()`` operation), you may need to sleep for a short
    interval (perhaps ~ 0.1s) to allow EPICS to process this PV
    and post a CA update.

    This command (from ``apstools.utils``) will list all the terms,
    PVs (if related), and current values::

      listdevice(terms, cname=True, dname=False, show_pv=True, use_datetime=False)

    New with issue #543.
    """
    yield from bps.null()

    # print(f"{args = }")
    if len(args) != 2:
        logger.error(
            "syntax:  SET terms.component value"
            f", received {args}.  Skipping this command ..."
        )
        return

    term = args[0]
    value = args[1]
    # print(f"{term = }")
    # print(f"{value = }")

    if not term.startswith("terms."):
        logger.error(
            (
                "First argument must start with 'terms.'"
                ", received '%s'.  Skipping this command ..."
            )
            % term
        )
        return
    # logger.info("type(value) = %s", type(value))

    # get the python object
    pyobj = terms  # dig down to the term
    full_dotted_name = terms.name  # re-construct full dotted name
    for cn in term.split(".")[1:]:
        # print(f"{cn = }")
        if hasattr(pyobj, cn):
            pyobj = getattr(pyobj, cn)
            full_dotted_name += f".{cn}"
            # print(f"{pyobj = }")
        else:
            logger.error(
                ("'%s.%s' does not exist.  Skipping this command ...")
                % (full_dotted_name, cn)
            )
            return
    if isinstance(pyobj, Signal):
        old_value = pyobj.get()
    # elif hasattr(pyobj, "position"):
    #     old_value = pyobj.position
    else:
        logger.error(
            (
                "Cannot set '%s', it is not a Signal"
                # " or positioner"
                ".  Skipping this command ..."
            )
            % full_dotted_name
        )
        return
    # print(f"{type(pyobj.get()) = }")

    try:
        if isinstance(old_value, int):
            # print("int")
            value = int(value)
        elif isinstance(old_value, float):
            # print("float")
            value = float(value)
        elif isinstance(old_value, str):
            # print("str")
            value = str(value)
        else:
            logger.error(
                (
                    "Cannot set '%s', support for data type '%s'"
                    " is not implemented yet.  Skipping this command ..."
                )
                % (full_dotted_name, type(old_value).__name__)
            )
            return
    except Exception as exc:
        logger.error(
            (
                "Cannot set '%s' to '%s'"
                " due to exception (%s)."
                "  Skipping this command ..."
            )
            % (term, args[1], exc)
        )
        return

    # print(f"{[full_dotted_name, value] = }")
    yield from bps.abs_set(pyobj, value, timeout=0.1, wait=False)
