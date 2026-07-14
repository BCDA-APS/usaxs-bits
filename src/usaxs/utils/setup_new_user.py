"""
User and sample session management for the 12-ID-E USAXS instrument.

The two main entry points are:

``newUser(user, sample, ...)``
    Called once per beamtime to create the top-level user data directory,
    reset detector order numbers, initialise NeXus and SPEC file writers,
    and record a session-start note in the Obsidian logbook.

``newSample(sample)``
    Called whenever the user changes samples.  Updates the sample directory
    PV and appends a new-sample note to the Obsidian logbook.

Session state is persisted in a hidden JSON file ``~/.user_info.json``
so that instrument-control scripts can restore the current user/sample
context after a restart without user interaction.

``matchUserInApsBss(user)`` queries the APS Beamtime Scheduling System REST
API to locate the active ESAF and proposal for *user*, writes all fields
to the ``usxTerms:bss:`` EPICS PVs, and sets ``RE.md["esaf_id"]`` and
``RE.md["proposal_id"]``.  Called automatically by :func:`newUser`.
"""

import datetime
import json
import logging
import os
from pathlib import Path

from apsbits.core.instrument_init import oregistry
from apstools.utils import cleanupText

from usaxs.utils.bss import BssApi
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordNewSample
from usaxs.utils.obsidian import recordUserStart

# from ..devices import user_data
user_data = oregistry["user_data"]

logger = logging.getLogger(__name__)

# Live RunEngine / NeXus writer references, populated by usaxs.startup via
# set_runtime_context(). newUser() reads these when called without an explicit
# RE (e.g. from the queue-monitor GUI / `qserver function execute newUser`).
#
# Why not `from usaxs.startup import RE`? In the queueserver worker the startup
# code is executed as '__main__' and its modules are dropped from sys.modules
# afterwards, so that lazy import RE-EXECUTES the whole of startup.py (creating a
# second set of devices and failing). Because the newUser function object keeps
# its __globals__ (this module's dict) alive, these references persist and stay
# valid even after the worker clears sys.modules.
_RE = None
_nxwriter = None


def set_runtime_context(RE=None, nxwriter=None):
    """Register the live RunEngine / NeXus writer for later newUser() calls.

    Called once by ``usaxs.startup`` after the RunEngine and NeXus writer are
    created. Passing ``None`` for either leaves the previously registered value
    unchanged.
    """
    global _RE, _nxwriter
    if RE is not None:
        _RE = RE
    if nxwriter is not None:
        _nxwriter = nxwriter


APSBSS_SECTOR = "12"
APSBSS_BEAMLINE = "12-ID-E"

NX_FILE_EXTENSION = ".h5"
# we need these so we can reset order numbers, if we start a new user.
saxs_det = oregistry["saxs_det"]
terms = oregistry["terms"]
waxs_det = oregistry["waxs_det"]


def _setNeXusFileName(path, scan_id=1, nxwriter=None):
    """
    NeXus file name
    """
    if nxwriter is None:
        logger.warning("no instance of nxwriter detected")

    fname = os.path.join(path, f"{os.path.basename(path)}{NX_FILE_EXTENSION}")
    nxwriter.file_name = fname
    logger.debug(f"NeXus file name : {nxwriter.file_name!r}")
    logger.debug("File will be written at end of next bluesky scan.")


# def _setSpecFileName(path, scan_id=1):
#     """
#     SPEC file name
#     """
#     from usaxs.startup import RE

#     fname = os.path.join(path, f"{os.path.basename(path)}.dat")
#     if filename_exists(fname):
#         logger.warning(">>> file already exists: %s <<<", fname)
#         specwriter.newfile(fname, RE=RE)
#         handled = "appended"
#     else:
#         specwriter.newfile(fname, scan_id=scan_id, RE=RE)
#         handled = "created"
#     logger.debug(f"SPEC file name : {specwriter.spec_filename}")
#     logger.debug(f"File will be {handled} at end of next bluesky scan.")


def newUser(
    user=None,
    sample=None,
    scan_id=1,
    year=None,
    month=None,
    day=None,
    skip_bss=False,
    RE=None,
    nxwriter=None,
):
    """Set up the instrument for a new user beamtime session.

    Creates (if necessary) the monthly base folder and the user data directory,
    resets detector file/order numbers to 1, configures NeXus and SPEC file
    writers, and records a session-start note in the Obsidian logbook.

    If called without arguments and a ``.user_info.json`` file exists from a
    previous session, those values are restored automatically (no prompts).
    If no state file exists, the user is prompted interactively for a name.

    Parameters
    ----------
    user : str, optional
        User name (used in the directory name and EPICS PV).  Prompts if None
        and no prior session file is found.
    sample : str, optional
        Initial sample directory name.  Defaults to ``"data"``.
    scan_id : int, optional
        Starting scan ID for SPEC file.  Default is 1.
    year, month, day : int, optional
        Override the current date.  Useful for recovering a prior session's
        folder without creating a new one.
    skip_bss : bool, optional
        If ``True``, clear all ``usxTerms:bss:`` PVs and skip the BSS lookup
        entirely.  Use this for setup runs or commissioning sessions that have
        no active ESAF or proposal.  Default is ``False``.
    RE : RunEngine, optional
        RunEngine to wire BSS metadata into. Defaults to the one
        instantiated in ``usaxs.startup`` — pass an explicit RunEngine
        only when you need a different instance.
    nxwriter : NXWriter, optional
        NeXus writer to set the per-session file name on. Defaults to the
        one instantiated in ``usaxs.startup`` — pass an explicit writer
        only when you need a different instance.

    Returns
    -------
    str
        Absolute path to the user data directory.

    Directory layout
    ----------------
    ======================  ========================
    purpose                 folder
    ======================  ========================
    user data folder base   <CWD>/MM_DD_USER
    SPEC data file          <CWD>/MM_DD_USER/MM_DD_USER.dat
    AD folder - SAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_saxs/
    folder - USAXS          <CWD>/MM_DD_USER/sample/MM_DD_USER_usaxs/
    AD folder - WAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_waxs/
    ======================  ========================

    CWD = usaxscontrol:/share1/USAXS_data/YYYY-MM
    """
    # Fall back to the references registered by startup (see set_runtime_context).
    # Do NOT `from usaxs.startup import ...` here: in the queueserver worker that
    # re-executes all of startup.py (see the module-level note above).
    if RE is None:
        RE = _RE
        if RE is None:
            logger.warning("no instance of RE detected")
    if nxwriter is None:
        nxwriter = _nxwriter
        if nxwriter is None:
            logger.warning("no instance of nxwriter detected")

    # this will revidse main to match what is needed for server...
    # it is useful for regular operations also...
    # this is where the data will ALWAYS be
    base_path = Path("~/share1/USAXS_data").expanduser()
    folder_name = datetime.datetime.now().strftime("%Y-%m")
    # this defines current folder: ~/share1/USAXS_data/2025-10/
    working_folder = base_path / folder_name

    if working_folder.exists():
        # print(f"Folder already exists: {working_folder}")
        pass
    else:
        working_folder.mkdir(parents=True)
        print(f"Folder created: {working_folder}")

    # Set permissions to 777 regardless
    os.chmod(working_folder, 0o777)
    print("Permissions set to 777")
    # go to the working folder.
    os.chdir(working_folder)

    cwd = Path.cwd()
    print(f"Your Path Is : {cwd}")

    # global specwriter
    filename = ".user_info.json"  # Store if a new user was created
    # check the file exists
    file_exists = (working_folder / filename).is_file()
    # print(f"File exists: {file_exists}")

    # if user is set, we are starting a new user and therefore will also reset order numbers:
    if user is not None:
        logger.debug("Synchronizing detector order numbers to %d", 1)
        # terms = oregistry["terms"]
        terms.FlyScan.order_number.put(1)
        # saxs_det = oregistry["saxs_det"]
        saxs_det.hdf1.file_number.put(1)
        # waxs_det = oregistry["waxs_det"]
        waxs_det.hdf1.file_number.put(1)
        # caput("usxLAX:USAXS:FS_OrderNumber",1)
        # caput("usaxs_eiger1:HDF1:FileNumber",1)
        # caput("usaxs_pilatus3:HDF1:FileNumber",1)
        # caput("usaxs_eiger1:cam1:FileNumber",1)
        # caput("usaxs_pilatus3:cam1:FileNumber",1)

    #### If the file exists and user is None, we are running this automatically and therefore restore old values:
    if user is None and file_exists:
        logger.debug("Found existing user info file: %s", filename)
        with open(filename, "r") as file:
            data = json.load(file)
            user = data.get("user_name")
            sample = data.get("sample_dir")
            year = data.get("year")
            month = data.get("month")
            day = data.get("day")
    elif user is None and not file_exists:
        user = input("Please provide the name of the new user: ").strip()

    dt = datetime.datetime.now()
    year = year or dt.year  # lgtm [py/unused-local-variable]
    month = month or dt.month
    day = day or dt.day
    sample = sample or "data"

    # now, if we overwrite the input by explicitly setting and month, eg: year=2025, month=9,day=29
    # we want to return to prior YYYY-MM folder:
    year_month = f"{year:04d}-{month:02d}"
    # print(f"Year-Month: {year_month}, Folder Name: {folder_name}")
    if year_month != folder_name:
        print("inside wrong folder, switching to correct one")
        os.chdir(base_path / year_month)
        cwd = Path.cwd()
        print("Your current path is now : %s", cwd)

    # prepare data for new json file.
    data = {
        "user_name": user,
        "sample_dir": sample,
        "year": year,
        "month": month,
        "day": day,
    }

    #### Load data into the json file
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)  # indent=4 for pretty formatting

    user_data.user_name.put(user)  # set in the PV
    user_data.sample_dir.put(sample)  # set in the PV

    path = (
        cwd  # we are in working directory where we want to save the data, that is all done above.
        / f"{month:02d}_{day:02d}_{cleanupText(user)}"
    )

    # BSS lookup runs before Obsidian so the note can include ESAF/proposal info.
    esaf, prop = None, None
    if skip_bss:
        _clear_bss_pvs(RE=RE)
        logger.info("BSS: skipped (skip_bss=True) — PVs cleared")
    else:
        try:
            esaf, prop = matchUserInApsBss(user, RE=RE)
        except Exception as exc:
            logger.warning("BSS lookup failed (non-fatal): %s", exc)

    if not path.exists():
        logger.debug("Creating user directory: %s", path)
        path.mkdir(parents=True)
        user_data.user_dir.put(str(path))  # set in the PV, needed by recordUserStart
        recordUserStart(esaf=esaf, proposal=prop)
    else:
        logger.debug("User directory already exists: %s", path)
        appendToMdFile("")  # ensure md file exists

    logger.debug("Current working directory: %s", cwd)
    user_data.user_dir.put(str(path))  # set in the PV

    _setNeXusFileName(str(path), scan_id=scan_id, nxwriter=nxwriter)
    # _setSpecFileName(str(path), scan_id=scan_id)
    user_data.spec_scan.put(scan_id)  # set in the PV

    logger.info(data)
    return str(path.absolute())


def newSample(sample=None):
    """
    Setup for a new sample name.

    Updates the sample directory PV and records the new sample in the
    Obsidian log.  Reads user/date info from the ``.user_info.json`` state
    file written by :func:`newUser`; raises ``RuntimeError`` if that file is
    not present (i.e. ``newUser()`` has not been called yet).

    Parameters
    ----------
    sample : str, optional
        Sample directory name.  If None, prompts the user interactively.

    Directory layout created by the combined newUser/newSample workflow:

    ======================  ========================
    purpose                 folder
    ======================  ========================
    user data folder base   <CWD>/MM_DD_USER
    SPEC data file          <CWD>/MM_DD_USER/MM_DD_USER.dat
    AD folder - SAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_saxs/
    folder - USAXS          <CWD>/MM_DD_USER/sample/MM_DD_USER_usaxs/
    AD folder - WAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_waxs/
    ======================  ========================

    CWD = usaxscontrol:/share1/USAXS_data/YYYY-MM
    """
    filename = ".user_info.json"  # Store if a new user was created
    cwd = Path.cwd()

    print(f"Your Path Is : {cwd}")

    file_exists = Path(filename).is_file()

    #### If the file exists:
    if file_exists:
        logger.info("Found existing user info file: %s", filename)
        with open(filename, "r") as file:
            data = json.load(file)
            user = data.get("user_name")
            year = data.get("year")
            month = data.get("month")
            day = data.get("day")
    else:
        # abort code execution
        raise RuntimeError(
            f"User info file {filename} not found. Please run newUser() first."
        )

    if sample is None:
        sample = input("Please provide the name of the new sample: ").strip()

    dt = datetime.datetime.now()
    user = user or "user"
    year = year or dt.year  # lgtm [py/unused-local-variable]
    month = month or dt.month
    day = day or dt.day
    sample = sample or "data"

    data = {
        "user_name": user,
        "sample_dir": sample,
        "year": year,
        "month": month,
        "day": day,
    }

    #### Load json data into file
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)  # indent=4 for pretty formatting

    user_data.sample_dir.put(sample)  # set in the PV

    # Obsidian recording, recordNewSample, md file if needed, make recoding about new sample.
    recordNewSample()

    return


## now Bss
# this works fine:
#


def _pick_active(records, user: str, now: datetime.datetime):
    """Return the first record whose date range covers *now* and whose user
    list contains *user* (case-insensitive last-name match).

    Falls back to the first record that covers *now* if no name match is found,
    and to the first record overall if none cover *now*.
    """
    name_lower = user.strip().lower()

    def covers_now(r):
        # Strip timezone info before comparing: proposal datetimes from
        # fromisoformat() may be tz-aware while now and ESAF datetimes are naive.
        start = r.start.replace(tzinfo=None)
        end = r.end.replace(tzinfo=None)
        return start <= now <= end

    def name_match(r):
        return any(
            name_lower in u.last_name.lower() or name_lower in u.first_name.lower()
            for u in r.users
        )

    active = [r for r in records if covers_now(r)]
    for r in active:
        if name_match(r):
            return r
    return active[0] if active else (records[0] if records else None)


def _clear_bss_pvs(RE=None):
    """Clear all ``usxTerms:bss:`` PVs and remove BSS keys from RE.md.

    Called by newUser(skip_bss=True) when no BSS data should be associated
    with the session (e.g. beamline setup runs without an active ESAF).
    """
    if RE is None:
        logger.warning("no instance of RE detected")

    bss_device = oregistry["bss"]
    for sig in (
        bss_device.esaf.id,
        bss_device.esaf.title,
        bss_device.esaf.description,
        bss_device.esaf.sector,
        bss_device.esaf.status,
        bss_device.esaf.start,
        bss_device.esaf.end,
        bss_device.esaf.user_last_names,
        bss_device.esaf.user_badges,
        bss_device.esaf.pi_name,
        bss_device.proposal.id,
        bss_device.proposal.title,
        bss_device.proposal.start,
        bss_device.proposal.end,
        bss_device.proposal.user_last_names,
        bss_device.proposal.user_badges,
        bss_device.proposal.pi_name,
    ):
        sig.put("")
    bss_device.esaf.user_count.put(0)
    bss_device.proposal.user_count.put(0)
    bss_device.proposal.duration.put(0)
    bss_device.proposal.mail_in.put(0)
    bss_device.proposal.proprietary.put(0)
    RE.md.pop("esaf_id", None)
    RE.md.pop("proposal_id", None)


def matchUserInApsBss(user, RE=None):
    """Query the APS BSS REST API for the active ESAF and proposal matching
    *user*, write all fields to the ``usxTerms:bss:`` PVs, and update
    ``RE.md`` with the proposal and ESAF IDs.

    Parameters
    ----------
    user : str
        User last name (or first name) to match against BSS records.
    RE : RunEngine, optional
        RunEngine to write ESAF/proposal IDs into. Defaults to the one
        instantiated in ``usaxs.startup``.

    Returns
    -------
    tuple[Esaf | None, Proposal | None]
        The matched ESAF and proposal objects, either of which may be None
        if no match was found.
    """
    if RE is None:
        logger.warning("no instance of RE detected")

    bss_device = oregistry["bss"]

    credfile = Path("~/.config/dmcredentials").expanduser()
    uname, pwd, stationname, uri = credfile.read_text().splitlines()

    now = datetime.datetime.now()
    year = str(now.year)
    month = now.month
    if month <= 4:
        cycle = f"{year}-1"
    elif month <= 8:
        cycle = f"{year}-2"
    else:
        cycle = f"{year}-3"

    with BssApi(username=uname, password=pwd, station_name=stationname, uri=uri) as api:
        esafs_all = api.esafs(beamline="12-ID-E", year=year)
        props_all = api.proposals(beamline="12-ID-E", cycle=cycle)

    logger.info(
        "BSS: found %d ESAFs, %d proposals for %s/%s",
        len(esafs_all),
        len(props_all),
        year,
        cycle,
    )

    esaf = _pick_active(esafs_all, user, now)
    prop = _pick_active(props_all, user, now)

    if esaf is None:
        logger.warning("BSS: no matching ESAF found for user %r", user)
    else:
        pi_users = [u for u in esaf.users if u.is_pi]
        pi = pi_users[0] if pi_users else esaf.users[0]
        bss_device.esaf.id.put(esaf.esaf_id)
        bss_device.esaf.title.put(esaf.title[:254])
        bss_device.esaf.description.put(esaf.description[:2047])
        bss_device.esaf.sector.put(esaf.sector)
        bss_device.esaf.status.put(esaf.status)
        bss_device.esaf.start.put(str(esaf.start))
        bss_device.esaf.end.put(str(esaf.end))
        bss_device.esaf.user_count.put(len(esaf.users))
        bss_device.esaf.user_last_names.put(
            ", ".join(u.last_name for u in esaf.users)[:254]
        )
        bss_device.esaf.user_badges.put(", ".join(u.badge for u in esaf.users)[:254])
        bss_device.esaf.pi_name.put(f"{pi.first_name} {pi.last_name}")
        RE.md["esaf_id"] = esaf.esaf_id
        logger.info("BSS: ESAF %s — %s", esaf.esaf_id, esaf.title)

    if prop is None:
        logger.warning("BSS: no matching proposal found for user %r", user)
    else:
        pi_users = [u for u in prop.users if u.is_pi]
        pi = pi_users[0] if pi_users else prop.users[0]
        bss_device.proposal.id.put(prop.proposal_id)
        bss_device.proposal.title.put(prop.title[:254])
        bss_device.proposal.start.put(str(prop.start))
        bss_device.proposal.end.put(str(prop.end))
        bss_device.proposal.duration.put(prop.duration.total_seconds() / 3600)
        bss_device.proposal.mail_in.put(1 if prop.mail_in else 0)
        bss_device.proposal.proprietary.put(1 if prop.proprietary else 0)
        bss_device.proposal.user_count.put(len(prop.users))
        bss_device.proposal.user_last_names.put(
            ", ".join(u.last_name for u in prop.users)[:254]
        )
        bss_device.proposal.user_badges.put(
            ", ".join(u.badge for u in prop.users)[:254]
        )
        bss_device.proposal.pi_name.put(f"{pi.first_name} {pi.last_name}")
        RE.md["proposal_id"] = prop.proposal_id
        logger.info("BSS: proposal %s — %s", prop.proposal_id, prop.title)

    return esaf, prop


# this shoudl find esafs
# import datetime as dt
# from typing import Sequence

# def filter_esafs(
#     esafs: Sequence["Esaf"],
#     *,
#     name: str,
#     status: str,
#     now: dt.datetime | None = None,
#     case_insensitive: bool = True,
# ) -> list["Esaf"]:
#     """
#     Keep ESAFs where:
#       1) `name` is contained in any user's first_name or last_name
#       2) esaf.start >= now - 1 day
#       3) esaf.end >= now
#       4) esaf.status matches `status`
#     Return sorted by start ascending (closest to now first).

#     Assumes all datetimes are naive and in local time.
#     """
#     if now is None:
#         now = dt.datetime.now()  # local, naive

#     cutoff = now - dt.timedelta(days=1)

#     def norm(s: str) -> str:
#         return s.casefold() if case_insensitive else s

#     name_n = norm(name.strip())
#     status_n = norm(status.strip())

#     out: list["Esaf"] = []

#     for e in esafs:
#         if e.start < cutoff:
#             continue
#         if e.end < now:
#             continue
#         if norm(e.status) != status_n:
#             continue

#         if not any(
#             (
#                 u.first_name and name_n in norm(u.first_name)
#             ) or (
#                 u.last_name and name_n in norm(u.last_name)
#             )
#             for u in (e.users or [])
#         ):
#             continue

#         out.append(e)

#     out.sort(key=lambda e: e.start)
#     return out

# def _pick_esaf(esafs_all, user, now):
#     """
#     Pick the first matching ESAF

#     Criteria:

#     * match user name
#     * has not yet expired
#     * earliest start

#     RETURNS

#     esaf_id or None
#     """
#     def esafSorter(obj):
#         return obj["experimentStartDate"]

#     esafs = [
#         esaf["esafId"]
#         for esaf in sorted(esafs_all, key=esafSorter)
#         # pick those that have not yet expired
#         if esaf["experimentEndDate"] > now
#         # and match user last name
#         if user in [
#             entry["lastName"]
#             for entry in esaf["experimentUsers"]
#         ]
#     ]

#     if len(esafs) == 0:
#         #logger.warning(
#         print(
#             "No unexpired ESAFs found that match user %s",
#             user
#         )
#         return None
#     elif len(esafs) > 1:
#         #logger.warning(
#         print(
#             "ESAF(s) %s match user %s at this time, picking first one",
#             str(esafs), user)

#     return str(esafs[0])


# def _pick_proposal(user, now, cycle):
#     """
#     Pick the first matching proposal

#     Criteria:

#     * match user name
#     * has not yet expired
#     * earliest start

#     RETURNS

#     proposal_id or None
#     """
#     def proposalSorter(obj):
#         return obj["startTime"]

#     get_proposals = apsbss.api_bss.listProposals
#     proposals = [
#         p["id"]
#         for p in sorted(
#             get_proposals(beamlineName=APSBSS_BEAMLINE, runName=cycle),
#             key=proposalSorter
#             )
#         # pick those that have not yet expired
#         if p["endTime"] > now
#         # and match user last name
#         if user in [
#             entry["lastName"]
#             for entry in p["experimenters"]
#         ]
#     ]

#     if len(proposals) == 0:
#         logger.warning(
#             "No unexpired proposals found that match user %s",
#             user
#         )
#         return None
#     elif len(proposals) > 1:
#         logger.warning(
#             "proposal(s) %s match user %s at this time, picking first one",
#             str(proposals), user)

#     return str(proposals[0])


# def _apsbss_summary_table(apsbss_object):
#     """return a table of apsbss local PVs"""
#     contents = {
#         "ESAF number" : apsbss_object.esaf.esaf_id,
#         "ESAF title" : apsbss_object.esaf.title,
#         "ESAF names" : apsbss_object.esaf.user_last_names,
#         "ESAF start" : apsbss_object.esaf.start_date,
#         "ESAF end" : apsbss_object.esaf.end_date,
#         "Proposal number" : apsbss_object.proposal.proposal_id,
#         "Proposal title" : apsbss_object.proposal.title,
#         "Proposal names" : apsbss_object.proposal.user_last_names,
#         "Proposal start" : apsbss_object.proposal.start_date,
#         "Proposal end" : apsbss_object.proposal.end_date,
#         "Mail-in flag" : apsbss_object.proposal.mail_in_flag,
#     }
#     table = pyRestTable.Table()
#     table.labels="key value PV".split()
#     for k, v in contents.items():
#         table.addRow((k, v.get(), v.pvname))

#     return table


# def matchUserInApsbss(user):
#     """
#     pull information from apsbss matching on user name and date
#     """
#     dt = datetime.datetime.now()
#     now = str(dt)
#     cycle = apsbss.getCurrentCycle()

#     esaf_id = _pick_esaf(user, now, cycle)
#     proposal_id = _pick_proposal(user, now, cycle)

#     if esaf_id is not None or proposal_id is not None:
#         # update the local apsbss PVs
#         logger.info("ESAF %s", esaf_id)
#         logger.info("Proposal %s", proposal_id)

#         prefix = apsbss_object.prefix
#         apsbss.epicsSetup(
#             prefix,
#             APSBSS_BEAMLINE,
#             cycle
#             )
#         apsbss.epicsClear(prefix)

#         apsbss_object.esaf.esaf_id.put(esaf_id or "")
#         apsbss_object.proposal.proposal_id.put(proposal_id or "")

#         logger.info("APSBSS PVs updated from APS Oracle databases.")
#         apsbss.epicsUpdate(prefix)

#         table = _apsbss_summary_table(apsbss_object)
#         logger.info("ESAF & Proposal Overview:\n%s", str(table))
#     else:
#         logger.warning("APSBSS not updated.")
#     logger.warning(
#         "You should check that PVs in APSBSS contain correct information.")
