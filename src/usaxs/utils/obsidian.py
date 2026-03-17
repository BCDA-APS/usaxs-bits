"""
Instrument-automated notes in Obsidian Markdown for the 12-ID-E USAXS beamline.

==============================================================================
OVERVIEW
==============================================================================

Obsidian is a file-based Markdown note-taking application.  This module
writes machine-generated log entries into the shared Obsidian vault at
/share1/Obsidian/Experiments so that instrument events are interleaved with
notes taken by beamline staff.

Notes are standard Markdown and are designed to be:
    - Human-readable in Obsidian (headings, bold labels, bullet lists)
    - AI-parseable (consistent structure, clear labels, ISO timestamps)
    - Concise — each entry records the event and essential parameters only

Staff may append their own notes at any time.  Instrument entries are always
written at the end of the file so that hand-written notes are preserved.

==============================================================================
FILE ORGANISATION
==============================================================================

Vault root   : /share1/Obsidian/Experiments
Period folder: YYYY-P  where P = 01 (Jan–Apr), 02 (May–Aug), 03 (Sep–Dec)
Notes folder : YYYY-P/Instrument_Records/
Note file    : <user_data_dir_basename>.md
               e.g. session folder "1_14_setup" → "1_14_setup.md"

Each note file is created once and then only appended to.

==============================================================================
TIMESTAMP FORMAT
==============================================================================

All entries are stamped with an ISO-8601 timestamp (YYYY-MM-DD HH:MM:SS).

    - Simple one-line entries: timestamp and text on the same line.
          2026-02-26 10:30:00 Starting plan: sample=MySample ...

    - Structured entries that open with a Markdown heading (##/###): timestamp
      on its own line immediately before the heading so the heading renders
      correctly in Obsidian.
          2026-02-26 10:30:00
          ## Beam Dumped

==============================================================================
FUNCTIONS
==============================================================================

    createPeriodFolder()             → Path : ensure YYYY-P period folder exists
    createMdFile()                   → Path : ensure note file exists
    appendToMdFile(text)                    : append one timestamped entry
    recordUserStart()                       : log new-user session start
    recordNewSample()                       : log instrument state for new sample
    recordRunCommandFile(command_list)      : log a command-file execution
    recordBeamDump()                        : log APS ring beam dump
    recordBeamRecovery()                    : log APS ring beam recovery
    recordFunctionRun()                     : log the calling function and its args
    recordQserverRun(command_line)          : log a QueueServer command
    recordUserAbort()                       : log a user-initiated abort
    recordProperEnd()                       : log a clean experiment end

==============================================================================
SUGGESTED IMPROVEMENTS
==============================================================================

    - recordUserStart() reads user_name and sample_dir from user_data but does
      not yet include them in the note text.  Adding them would make the
      "User Experiment Start" entry much more useful.

    - EpicsSignalRO instances created inline inside recordNewSample() may not
      have completed Channel Access connection before .get() is called,
      potentially returning stale or zero values.  Consider creating them at
      module level (like monochromator) and calling .wait_for_connection().

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-02-26 : Reformatted and documented.  Fixed double-timestamp
                        bug in all record*() functions; fixed broken Markdown
                        heading formatting in appendToMdFile(); removed unused
                        imports (json, Component, Device, cleanupText,
                        filename_exists); removed dead variable start_time in
                        recordUserStart(); removed unused shlex import inside
                        recordFunctionRun(); corrected "QueServer" → "QueueServer".
"""

import datetime
import logging
import os
from pathlib import Path

from apsbits.core.instrument_init import oregistry
from ophyd import EpicsSignalRO

from .check_file_exists import filename_exists  # available for callers; not used here


user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]

logger = logging.getLogger(__name__)

APSBSS_SECTOR = "12"
APSBSS_BEAMLINE = "12-ID-E"


def createPeriodFolder():
    """
    Ensure the current 4-month period folder exists and return its path.

    The vault organises notes into three periods per calendar year, each
    spanning four months.  The period number P is derived from the month:

        P = 01 → January – April
        P = 02 → May – August
        P = 03 → September – December

    The folder path created (or reused) is:
        /share1/Obsidian/Experiments/YYYY-P/Instrument_Records/

    Returns
    -------
    Path
        Absolute path to the Instrument_Records folder for the current period.
    """
    base_path = Path("/share1/Obsidian/Experiments")
    now = datetime.datetime.now()
    # (month-1)//4 + 1 maps months 1-4 → 1, 5-8 → 2, 9-12 → 3
    period = (now.month - 1) // 4 + 1
    folder_name = f"{now.year}-{period:02d}"
    working_folder = base_path / folder_name / "Instrument_Records"

    if not working_folder.exists():
        working_folder.mkdir(parents=True)

    return working_folder


# Keep the original name as an alias so existing call sites are not broken.
createMonthFolder = createPeriodFolder


def createMdFile():
    """
    Ensure the note file for the current session exists and return its path.

    The file name is derived from the last component of user_data.user_dir
    (the session data directory), so each beamtime session gets its own note
    file.  For example, if user_dir is ``/share1/USAXS_data/2026-01/1_14_setup``
    the note file is ``1_14_setup.md``.

    The file is created with a single ``# Experiment Notes`` heading on first
    use.  Subsequent calls return the existing path without modification.

    Returns
    -------
    Path
        Absolute path to the session Markdown note file.
    """
    working_folder = createPeriodFolder()
    data_path = user_data.user_dir.get()
    last_folder_name = os.path.basename(os.path.normpath(data_path))
    md_filename = f"{last_folder_name}.md"
    md_file_path = working_folder / md_filename

    if not md_file_path.exists():
        with open(md_file_path, "w") as f:
            f.write("# Experiment Notes by USAXS instrument\n")

    return md_file_path


def appendToMdFile(text: str):
    """
    Append one timestamped entry to the current session note file.

    The entry is stamped with the current wall-clock time
    (``YYYY-MM-DD HH:MM:SS``).  Formatting depends on whether the text opens
    with a Markdown heading:

        - Plain text: ``{timestamp} {text}``  (single line)
        - Heading (``#…``): timestamp on its own line, then the heading,
          so that Obsidian renders the heading correctly.

    Empty or whitespace-only text is silently ignored.

    Parameters
    ----------
    text : str
        The text to append.  May be a single line or a multi-line block
        (e.g. heading + bullet list).  Leading/trailing whitespace is stripped
        before writing.
    """
    md_file_path = createMdFile()
    stripped = text.strip()
    if not stripped:
        return
    with open(md_file_path, "a") as f:
        time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if stripped.startswith("#"):
            # Markdown headings must start at the beginning of a line.
            # Write the timestamp on its own preceding line.
            f.write(f"\n{time_now}\n{stripped}\n")
        else:
            f.write(f"{time_now} {stripped}\n")


def recordUserStart():
    """
    Record the start of a new user session in the note file.

    Called by newUser().  Writes a ``## User Experiment Start`` heading and
    then delegates to recordNewSample() to capture the current instrument
    state.

    Note: user_name and sample_dir are available from user_data but are not
    yet included in the note text.  Adding them here would make this entry
    more informative (see SUGGESTED IMPROVEMENTS in the module docstring).
    """
    user_name = user_data.user_name.get()    # read but not yet used in note
    sample_dir = user_data.sample_dir.get()  # read but not yet used in note
    appendToMdFile("## User Experiment Start\n")
    recordNewSample()


def recordNewSample():
    """
    Record the current instrument state when a new sample directory is created.

    Called by newSample().  Captures APS ring current, undulator energy, and
    monochromator energy at the moment of the call and writes them as a
    Markdown sub-section.

    Warning: ``aps_current`` and ``und_energy`` are created as inline
    EpicsSignalRO objects.  Channel Access connection is not explicitly awaited,
    so the first ``.get()`` call may return a stale or default value if the
    IOC is slow to respond (see SUGGESTED IMPROVEMENTS in the module docstring).
    """
    mono_energy = monochromator.dcm.energy.readback
    aps_current = EpicsSignalRO("XFD:srCurrent", name="aps_current")
    und_energy = EpicsSignalRO("S12ID:USID:EnergyM.VAL", name="undulator_energy")
    sample_dir = user_data.sample_dir.get()
    text = (
        f"### New Sample directory \"{sample_dir}\" created\n"
        f"- **APS Current (mA):** {aps_current.get():.2f}\n"
        f"- **Undulator Energy (keV):** {und_energy.get():.2f}\n"
        f"- **Mono X-ray Energy (keV):** {mono_energy.get():.2f}\n"
    )
    appendToMdFile(text)


def recordRunCommandFile(command_list: str):
    """
    Record the execution of a command file (called by run_command_file()).

    Parameters
    ----------
    command_list : str
        Text representation of the queued sample/command list.
    """
    text = f"## Run Command File executed\n{command_list}\n"
    appendToMdFile(text)


def recordBeamDump():
    """
    Record an APS ring beam dump event (called by suspenders).
    """
    appendToMdFile("## Beam Dumped\n")


def recordBeamRecovery():
    """
    Record APS ring beam recovery after a dump (called by suspenders).
    """
    appendToMdFile("## Beam Recovered\n")


def recordFunctionRun():
    """
    Record the name and arguments of the function that called this one.

    Uses ``inspect`` to walk one frame up the call stack and reconstruct a
    Python-style call representation of the caller:
        ``functionName(arg1=value1, arg2=value2, ...)``

    Values are formatted with ``repr()`` so strings appear quoted, booleans
    appear as ``True``/``False``, and the result can be read back as valid
    Python syntax.

    Call this as a plain function (NOT ``yield from``) at the very start of a
    plan body, before the first ``yield``, so it fires when the RunEngine
    begins executing the plan:

        linkam = linkam_tc1
        isDebugMode = linkam_debug.get()
        recordFunctionRun()          # ← call here
        if not isDebugMode:
            yield from before_command_list()

    The Obsidian note entry produced looks like::

        2026-02-26 10:30:00
        ## Function Run: myLinkamPlan_AI_template
        - **Call:** myLinkamPlan_AI_template(pos_X=0, pos_Y=0, thickness=1.0, scan_title='MySample', temp_target=200, ...)

    Returns
    -------
    str
        The reconstructed call string (also written to the note file).
    """
    import inspect
    previous_frame = inspect.currentframe().f_back
    function_name = previous_frame.f_code.co_name
    args, _, _, values = inspect.getargvalues(previous_frame)
    arg_list = [f"{arg}={repr(values[arg])}" for arg in args]
    command_line = f"{function_name}({', '.join(arg_list)})"
    text = (
        f"## Function Run: {function_name}\n"
        f"- **Call:** {command_line}\n"
    )
    appendToMdFile(text)
    return command_line


def recordQserverRun(command_line: str):
    """
    Record a command dispatched by the QueueServer (called by QueueServer).

    Parameters
    ----------
    command_line : str
        The command string exactly as submitted to the QueueServer.
    """
    text = f"## QueueServer Command Run\n- **Command Line:** {command_line}\n"
    appendToMdFile(text)


def recordUserAbort():
    """
    Record a user-initiated abort (Ctrl-C or RunEngine abort).
    """
    appendToMdFile("## User Abort Event\n")


def recordProperEnd():
    """
    Record a clean, successful end of the experiment.
    """
    appendToMdFile("## Proper End of Experiment\n")
