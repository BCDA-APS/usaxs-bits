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
from epics import caput


from usaxs.callbacks.demo_spec_callback import specwriter
from usaxs.utils.obsidian import appendToMdFile, recordUserStart, recordNewSample

from ..callbacks.nxwriter_usaxs import nxwriter
from ..startup import RE
from .check_file_exists import filename_exists

# from ..devices import user_data
user_data = oregistry["user_data"]

logger = logging.getLogger(__name__)

APSBSS_SECTOR = "12"
APSBSS_BEAMLINE = "12-ID-E"

NX_FILE_EXTENSION = ".h5"
#we need these so we can reset order numbers, if we start a new user. 
saxs_det = oregistry["saxs_det"]
terms = oregistry["terms"]
waxs_det = oregistry["waxs_det"]

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


def newUser(user=None, sample=None, scan_id=1, year=None, month=None, day=None):
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
    AD folder - SAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_saxs/
    folder - USAXS          <CWD>/MM_DD_USER/sample/MM_DD_USER_usaxs/
    AD folder - WAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_waxs/
    ======================  ========================

    CWD = usaxscontrol:/share1/USAXS_data/YYYY-MM
    """
    #this will revidse main to match what is needed for server...
    # it is useful for regular operations also...
    # this is where the data will ALWAYS be
    base_path = Path("~/share1/USAXS_data").expanduser()
    folder_name = datetime.datetime.now().strftime("%Y-%m")
    #this defines current folder: ~/share1/USAXS_data/2025-10/
    working_folder = base_path / folder_name

    if working_folder.exists():
        #print(f"Folder already exists: {working_folder}")
        pass
    else:
        working_folder.mkdir(parents=True)
        print(f"Folder created: {working_folder}")

    # Set permissions to 777 regardless
    os.chmod(working_folder, 0o777)
    print(f"Permissions set to 777")
    # go to the working folder. 
    os.chdir(working_folder)

    cwd = Path.cwd()
    print(f"Your Path Is : {cwd}")
   
    
    #global specwriter
    filename = ".user_info.json"  # Store if a new user was created
    # check the file exists
    file_exists = (working_folder / filename).is_file()
    #print(f"File exists: {file_exists}")
    
    # if user is set, we are starting a new user and therefore will also reset order numbers:
    if user is not None :
        logger.debug("Synchronizing detector order numbers to %d", 1)
        # terms = oregistry["terms"]
        terms.FlyScan.order_number.put(1)
        # saxs_det = oregistry["saxs_det"]
        saxs_det.hdf1.file_number.put(1)
        #waxs_det = oregistry["waxs_det"]
        waxs_det.hdf1.file_number.put(1)
        # caput("usxLAX:USAXS:FS_OrderNumber",1)
        # caput("usaxs_eiger1:HDF1:FileNumber",1)
        # caput("usaxs_pilatus3:HDF1:FileNumber",1)        
        # caput("usaxs_eiger1:cam1:FileNumber",1)
        # caput("usaxs_pilatus3:cam1:FileNumber",1)
         
    #### If the file exists and user is None, we are running this automatically and therefore restore old values:
    if user is None and file_exists:
        logger.info("Found existing user info file: %s", filename)
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
    #print(f"Year-Month: {year_month}, Folder Name: {folder_name}")
    if year_month != folder_name:
        print("inside wrong folder, switching to correct one")
        os.chdir(base_path/year_month)
        cwd = Path.cwd()
        print("Your current path is now : %s", cwd)
    
     #prepare data for new json file. 
    data = {
        "user_name": user,
        "sample_dir":sample,
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
        /
        f"{month:02d}_{day:02d}_{cleanupText(user)}"
    )

    if not path.exists():
        logger.info("Creating user directory: %s", path)
        path.mkdir(parents=True)
        user_data.user_dir.put(str(path))  # set in the PV, we need this in recordUserStart
        # Obsidian recording, recordUserStart, md file if needed, make recoding about user.
        recordUserStart()   #if the path did not exist, we need to create a new md file also. 
    else:
        logger.info("User directory already exists: %s", path)
        appendToMdFile("") # just ensure the md file exists. If needed, create it. 

    logger.info("Current working directory: %s", cwd)
    user_data.user_dir.put(str(path))  # set in the PV

    _setNeXusFileName(str(path), scan_id=scan_id)   #this sets the path for Nexus file writer.  
    _setSpecFileName(str(path), scan_id=scan_id)    # this sets the path for spec file writer. 
    # user_data? This is likely not needed... 
    user_data.spec_scan.put(scan_id)  # set in the PV    
    # matchUserInApsbss(user)     # update ESAF & Proposal, if available
    # TODO: RE.md["proposal_id"] = <proposal ID value from apsbss>

    logger.info(data)
    return str(path.absolute())

def newSample(sample=None):
    """
    setup for a new sample name

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
    AD folder - SAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_saxs/
    folder - USAXS          <CWD>/MM_DD_USER/sample/MM_DD_USER_usaxs/
    AD folder - WAXS        <CWD>/MM_DD_USER/sample/MM_DD_USER_waxs/
    ======================  ========================

    CWD = usaxscontrol:/share1/USAXS_data/YYYY-MM
    """
    global specwriter
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
            sampleOld = data.get("sample_dir")
            year = data.get("year")
            month = data.get("month")
            day = data.get("day")
    else:
        #abort code execution
        raise RuntimeError(f"User info file {filename} not found. Please run newUser() first.")

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
        "sample_dir":sample,
        "year": year,
        "month": month,
        "day": day,
    }

    # Obsidian recording, recordNewSample, md file if needed, make recoding about new sample.
    recordNewSample()

    #### Load json data into file
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)  # indent=4 for pretty formatting

    user_data.sample_dir.put(sample)  # set in the PV




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
