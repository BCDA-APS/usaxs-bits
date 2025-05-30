"""
Plans for executing command lists in USAXS.

run batch of scans from command list
"""

import datetime
import logging
import os

import pyRestTable
from apsbits.core.instrument_init import oregistry
from apstools.utils import ExcelDatabaseFileGeneric
from apstools.utils import rss_mem
from bluesky import plan_stubs as bps
from bluesky.utils import plan
from ophyd import Signal

# from ..usaxs_flyscan_support import instrument_archive
# from ..utils.emails import email_notices
from ..usaxs_flyscan_support.nexus_flyscan import reset_manager
from ..utils.constants import constants
from ..utils.quoted_line import split_quoted_line
from .amplifiers_plan import measure_background
from .axis_tuning import instrument_default_tune_ranges
from .axis_tuning import update_EPICS_tuning_widths
from .axis_tuning import user_defined_settings
from .mode_changes import mode_BlackFly
from .mode_changes import mode_Radiography
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .mode_changes import mode_WAXS
from .plans_tune import allUSAXStune
from .plans_tune import preSWAXStune
from .plans_tune import preUSAXStune
from .requested_stop import RequestAbort
from .sample_rotator_plans import PI_Off
from .sample_rotator_plans import PI_onF
from .sample_rotator_plans import PI_onR

a_shutter_autoopen = oregistry["a_shutter_autoopen"]
s_stage = oregistry["s_stage"]
saxs_det = oregistry["saxs_det"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]
waxs_det = oregistry["waxs_det"]

I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
trd_controls = oregistry["trd_controls"]
upd_controls = oregistry["upd_controls"]

MAXIMUM_ATTEMPTS = 1  # (>=1): try command list item no more than this many attempts

logger = logging.getLogger(__name__)

##User facing functions


@plan
def run_command_file(filename, md=None):
    """
    Plan: execute a list of commands from a text or Excel file.

    * Parse the file into a command list
    * yield the command list to the RunEngine (or other)
    """
    if md is None:
        md = {}
    commands = get_command_list(filename)
    yield from execute_command_list(filename, commands, md=md)


def summarize_command_file(filename):
    """Print the command list from a text or Excel file."""
    commands = get_command_list(filename)
    logger.info("Command file: %s\n%s", command_list_as_table(commands), filename)


## Internal functions


@plan
def beforeScanComputeOtherStuff():
    """Actions before each data collection starts."""
    yield from bps.null()  # TODO: remove this once you add the "other stuff"


@plan
def postCommandsListfile2WWW(commands):
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


@plan
def before_command_list(md=None, commands=None):
    """Actions before a command list is run."""

    if commands is not None:
        verify_commands(commands)

    if md is None:
        md = {}

    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        user_data.collection_in_progress,
        1,
    )

    yield from user_data.set_state_plan("Starting data collection")

    yield from bps.mv(
        usaxs_shutter,
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


def verify_commands(commands):
    """Verifies command input parameters to check if they are valid"""
    errors: list[str] = []
    # separate commands into individual components, see execute_command_list for details
    scan_actions = "flyscan usaxsscan saxs saxsexp waxs waxsexp".split()
    for command in commands:
        action, args, i, raw_command = command
        if action.lower() in scan_actions:
            # if args[2].isnumeric() is False :
            #    list_of_errors.append(f"line {i}: thickness incorrect for : {raw_command.strip()}")
            try:
                sx = float(args[0])
                sy = float(args[1])
                sth = float(args[2])
                snm = args[3]
            except (IndexError, ValueError) as exinfo:
                errors.append(
                    f"line {i}: Improper command : {raw_command.strip()} : {exinfo}"
                )
                continue
            # check sx against travel limits
            if sx < s_stage.x.low_limit:
                errors.append(
                    f"line {i}: SX low limit: value {sx} < low limit {s_stage.x.low_limit}, "
                    f"command: {raw_command.strip()}"
                )
            if sx > s_stage.x.high_limit:
                errors.append(
                    f"line {i}: SX high limit: value {sx} > high limit {s_stage.x.high_limit}, "
                    f"command: {raw_command.strip()}"
                )
            # check sy against travel limits
            if sy < s_stage.y.low_limit:
                errors.append(
                    f"line {i}: SY low limit: value {sy} < low limit {s_stage.y.low_limit}, "
                    f"command: {raw_command.strip()}"
                )
            if sy > s_stage.y.high_limit:
                errors.append(
                    f"line {i}: SY high limit: value {sy} > high limit {s_stage.y.high_limit}, "
                    f"command: {raw_command.strip()}"
                )
            # check sth for reasonable sample thickness value
            if sth < 0:
                print(
                    f"{sth = } from args[2] = float('{args[2]}') -- thickness problem"
                )
            #    list_of_errors.append(f"line {i}: thickness incorrect for : {raw_command.strip()}")
            # check snm for reasonable sample title value
    if len(errors) > 0:
        err_msg = (
            "Errors were found in command file. Cannot continue. List of errors:\n"
            "\n".join(errors)
        )
        raise RuntimeError(err_msg)
    # this is the end of this routine
    # raise RuntimeError("Stop anyway")
    logger.info("Command file verified")


@plan
def after_command_list(md=None):
    """Actions after a command list is run."""
    # if md is None:
    #     md = {}
    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        user_data.collection_in_progress,
        0,
        usaxs_shutter,
        "close",
    )
    yield from user_data.set_state_plan("USAXS macro file done")


@plan
def before_plan(md=None):
    """Actions before every data collection plan."""
    if md is None:
        md = {}

    if terms.preUSAXStune.needed:
        # tune at previous sample position
        # don't overexpose the new sample position
        # select between positions
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        if mode_now == "USAXS in beam":
            yield from preUSAXStune(md=md)
        else:
            yield from preSWAXStune(md=md)


@plan
def after_plan(weight=1, md=None):
    """Actions after every data collection plan."""

    # if md is None:
    #     md = {}

    yield from bps.mv(  # increment it
        terms.preUSAXStune.num_scans_last_tune,
        terms.preUSAXStune.num_scans_last_tune.get() + weight,
    )


def parse_Excel_command_file(filename):
    """
    Parse an Excel spreadsheet with commands, return as command list.

    TEXT view of spreadsheet (Excel file line numbers shown)::

        [1] List of sample scans to be run
        [2]
        [3]
        [4] scan    sx  sy  thickness   sample name
        [5] FlyScan 0   0   0   blank
        [6] FlyScan 5   2   0   blank

    PARAMETERS

    filename : str
        Name of input Excel spreadsheet file.  Can be relative or absolute path,
        such as "actions.xslx", "../sample.xslx", or
        "/path/to/overnight.xslx".

    RETURNS

    list of commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    RAISES

    FileNotFoundError
        if file cannot be found

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


def parse_text_command_file(filename):
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


def command_list_as_table(commands):
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


def get_command_list(filename):
    """Return command list from either text or Excel file."""
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    try:
        commands = parse_Excel_command_file(filename)
    except Exception:  # TODO: XLRDError
        commands = parse_text_command_file(filename)
    return commands


@plan
def execute_command_list(filename, commands, md=None):
    """
    Plan: execute the command list.

    The command list is a tuple described below.

    * Only recognized commands will be executed.
    * Unrecognized commands will be reported as comments.

    PARAMETERS

    filename : str
        Name of input text file.  Can be relative or absolute path,
        such as "actions.txt", "../sample.txt", or
        "/path/to/overnight.txt".
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
    from .plans_usaxs import USAXSscan
    from .plans_user_facing import saxsExp
    from .plans_user_facing import waxsExp

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
    # yield from documentation_run(text)

    # TODO: figure out what this was doing, does not seem to have the code available in bits
    # instrument_archive(text)

    yield from before_command_list(md=md, commands=commands)
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

        def _handle_actions_(
            action=action,
            args=args,
            i=i,
            raw_command=raw_command,
            _md=_md,
            simple_actions=simple_actions,
        ):
            """Inner function to make try..except clause more clear."""
            if action in ("flyscan", "usaxsscan"):
                sx = float(args[0])
                sy = float(args[1])
                sth = float(args[2])
                _md.update(dict(sx=sx, sy=sy, thickness=sth, title=args[3]))
                yield from USAXSscan(sx, sy, sth, args[3], md=_md)

            elif action in ("saxs", "saxsexp"):
                sx = float(args[0])
                sy = float(args[1])
                sth = float(args[2])
                _md.update(dict(sx=sx, sy=sy, thickness=sth, title=args[3]))
                yield from saxsExp(sx, sy, sth, args[3], md=_md)

            elif action in ("waxs", "waxsexp"):
                sx = float(args[0])
                sy = float(args[1])
                sth = float(args[2])
                _md.update(dict(sx=sx, sy=sy, thickness=sth, title=args[3]))
                yield from waxsExp(sx, sy, sth, args[3], md=_md)

            # elif action in ("run_python", "run"):
            #     filename = args[0]
            #     yield from run_python_file(filename, md={})

            elif action in ("set",):
                yield from run_set_command(*args)

            elif action in simple_actions:
                yield from simple_actions[action](md=_md)

            else:
                logger.info("no handling for line %d: %s", i, raw_command)
                yield from bps.null()
            logger.info("memory report: %s", rss_mem())

        attempt = 0  # count the number of attempts
        maximum_attempts = MAXIMUM_ATTEMPTS  # set an upper limit
        exit_requested = False

        # see issue #502
        while attempt < maximum_attempts:
            try:
                # call the inner function (above)
                yield from _handle_actions_()
                logger.info("Command %s executed successfully.", command)
                break  # leave the while loop
            # TODO: need to handle some Exceptions, fail on others
            except Exception as exc:
                if exc.__class__ in (RequestAbort,):
                    exit_requested = True
                    break  # we requested abort from EPICS
                subject = (
                    f"{exc.__class__.__name__}"
                    f" during attempt {attempt + 1} of {maximum_attempts}"
                    f" of command '{command}''"
                )
                body = f"subject: {subject}\n"
                body += f"\ndate: {datetime.datetime.now().isoformat(' ')}\n"
                body += f"command file: {full_filename}\n"
                body += f"line number: {i}\n"
                body += f"command: {command}\n"
                body += f"raw command: {raw_command}\n"
                body += f"attempt: {attempt + 1} of {maximum_attempts}\n"
                body += f"exception: {exc}\n"
                body += "Stopping further processing of this command list.\n"
                logger.error("Exception %s\n%s", subject, body)
                # email_notices.send(subject, body)
                attempt += 1
                exit_requested = True  # issue #502: stop if an Exception was noted

        if exit_requested:
            break

    yield from after_command_list(md=md)
    logger.info("memory report: %s", rss_mem())


@plan
def sync_order_numbers():
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


@plan
def run_set_command(*args):
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
