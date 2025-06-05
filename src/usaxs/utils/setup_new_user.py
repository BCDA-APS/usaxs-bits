"""
manage the user folder
"""

import datetime
import json
import logging
import os
from pathlib import Path

from apsbits.core.instrument_init import oregistry
from apstools.utils import cleanupText

from usaxs.callbacks.spec_data_file_writer import specwriter

from ..callbacks.nxwriter_usaxs import nxwriter
from ..startup import RE
from .check_file_exists import filename_exists

# from ..devices import user_data
user_data = oregistry["user_data"]

logger = logging.getLogger(__name__)

APSBSS_SECTOR = "12"
APSBSS_BEAMLINE = "12-ID-E"

NX_FILE_EXTENSION = ".h5"


def _setNeXusFileName(path, scan_id=1):
    """
    NeXus file name
    """

    fname = os.path.join(path, f"{os.path.basename(path)}{NX_FILE_EXTENSION}")
    nxwriter.file_name = fname
    logger.info(f"NeXus file name : {nxwriter.file_name!r}")
    logger.info("File will be written at end of next bluesky scan.")


def _setSpecFileName(path, scan_id=1):
    """
    SPEC file name
    """
    fname = os.path.join(path, f"{os.path.basename(path)}.dat")
    if filename_exists(fname):
        logger.warning(">>> file already exists: %s <<<", fname)
        specwriter.newfile(fname, RE=RE)
        handled = "appended"
    else:
        specwriter.newfile(fname, scan_id=scan_id, RE=RE)
        handled = "created"
    logger.info(f"SPEC file name : {specwriter.spec_filename}")
    logger.info(f"File will be {handled} at end of next bluesky scan.")


def newUser(user=None, scan_id=1, year=None, month=None, day=None):
    """
    setup for a new user

    Create (if necessary) new user directory in
    standard directory with month, day, and
    given user name as shown in the following table.
    Each technique (SAXS, USAXS, WAXS) will be
    reponsible for creating its subdirectory
    as needed.

    ======================  ========================
    purpose                 folder
    ======================  ========================
    user data folder base   <CWD>/MM_DD_USER
    SPEC data file          <CWD>/MM_DD_USER/MM_DD_USER.dat
    AD folder - SAXS        <CWD>/MM_DD_USER/MM_DD_USER_saxs/
    folder - USAXS          <CWD>/MM_DD_USER/MM_DD_USER_usaxs/
    AD folder - WAXS        <CWD>/MM_DD_USER/MM_DD_USER_waxs/
    ======================  ========================

    CWD = usaxscontrol:/share1/USAXS_data/YYYY-MM
    """
    global specwriter
    filename = ".user_info.json"  # Store if a new user was created
    cwd = Path.cwd()

    print("Your Path Is : %s", cwd)

    file_exists = Path(filename).is_file()

    #### If the file exists:
    if user is None and file_exists:
        logger.info("Found existing user info file: %s", filename)
        with open(filename, "r") as file:
            data = json.load(file)
            user = data.get("user_name")
            year = data.get("year")
            month = data.get("month")
            day = data.get("day")
    elif user is None and not file_exists:
        user = input("Please provide the name of the new user: ").strip()

    dt = datetime.datetime.now()
    year = year or dt.year  # lgtm [py/unused-local-variable]
    month = month or dt.month
    day = day or dt.day

    data = {
        "user_name": user,
        "year": year,
        "month": month,
        "day": day,
    }

    #### Load json data into file
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)  # indent=4 for pretty formatting

    user_data.user_name.put(user)  # set in the PV
    # user_data.spec_scan.put(scan_id)  # set in the PV

    # DATA_DIR_BASE = pathlib.Path("/") / "share1" / "USAXS_data"
    path = (
        cwd  # instead of DATA_DIR_BASE
        /
        # f"{year:04d}-{month:02d}" /
        f"{month:02d}_{day:02d}_{cleanupText(user)}"
    )

    if not path.exists():
        logger.info("Creating user directory: %s", path)
        path.mkdir(parents=True)
    logger.info("Current working directory: %s", cwd)
    user_data.user_dir.put(str(path))  # set in the PV

    _setNeXusFileName(str(path), scan_id=scan_id)
    _setSpecFileName(str(path), scan_id=scan_id)  # SPEC file name
    # matchUserInApsbss(user)     # update ESAF & Proposal, if available
    # TODO: RE.md["proposal_id"] = <proposal ID value from apsbss>

    logger.info(data)
    return str(path.absolute())


# def _pick_esaf(user, now, cycle):
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

#     get_esafs = apsbss.getCurrentEsafs
#     esafs = [
#         esaf["esafId"]
#         for esaf in sorted(get_esafs(APSBSS_SECTOR), key=esafSorter)
#         # pick those that have not yet expired
#         if esaf["experimentEndDate"] > now
#         # and match user last name
#         if user in [
#             entry["lastName"]
#             for entry in esaf["experimentUsers"]
#         ]
#     ]

#     if len(esafs) == 0:
#         logger.warning(
#             "No unexpired ESAFs found that match user %s",
#             user
#         )
#         return None
#     elif len(esafs) > 1:
#         logger.warning(
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
