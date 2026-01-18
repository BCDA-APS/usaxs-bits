'''
Docstring for usaxs.utils.obsidian

This code will support automatic recording of user operations in human language into Obsidian Vault
called experiments, located on /share1/Obsidian/Experiments
Notes will be in form of Markdown files used by Obsidian (filename.md)
These notes will have human language record of important events, suitabel for human and AI consumption with readable formating.

We need:
createMonthFolder(): if needed, create in folder /share1/Obsidian/Experiments folder in form of "YYYY-MM" with folder InstrumentRecords (e.g., 2026-02/InstrumentRecords) this is where the notes go.
createMdFile(): create MM-DD-username.md file if needed, inside YYYY-MM/InstrumentRecords folder. These functions need to create the folder/file only if needed, or just pass. 

Other functions will use above functions and append to the end of the md file. It needs to be always end of the file, since staff may decide to append stuff into the file manually, 
which is really useful in case notes are needed. 
To keep proper flow, code needs to append after staff additional notes :
a. recordUserStart() called on newUser(), records basic user metadata in human language.
b. recordNewSample() called by newSample(), records basic instrument settings
c. recordBeamDump()/RecordBeamRecovery(), records beam dump/recovery, called by suspenders
d. recordStaticSamples() - called by run_command_file() and records list of samples queued.
e. recordFunctionRun() - called by python function runs, need to record the command line which was used to execute the function. Not sure how to do this.
f. recordQserverRun() used by QueServer to record line by line what QueServer runs.
g. Do we need to record tuning? May be if run automatically? But, this info is in Database, so this may be unnneded for humans.
etc. record of recordUserAbort, recordProperEnd, ... Any other records needed? Making record of each scan seems excessive, that is also in database in case it is needed.
Now, to do this obsidian.py will need to import from oregistry instrument details (user info, folder info, wavelength, APS current ring, etc). We may need to pass some parameters from calling function to make life easier for the function to know proper data...

Eventually we need to add this through the code itself to make sure the records are made.

'''

#imports:
import datetime
import json
import logging
import os
from pathlib import Path

from apsbits.core.instrument_init import oregistry
from apstools.utils import cleanupText
from .check_file_exists import filename_exists
from ophyd import EpicsSignalRO
from ophyd import Component
from ophyd.device import Device


# from ..devices import user_data
user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]



logger = logging.getLogger(__name__)

APSBSS_SECTOR = "12"
APSBSS_BEAMLINE = "12-ID-E"


def createMonthFolder():
    # create in folder /share1/Obsidian/Experiments folder in form of "YYYY-MM" with folder InstrumentRecords (e.g., 2026-02/InstrumentRecords) this is where the notes go
    base_path = Path("/share1/Obsidian/Experiments")
    folder_name = datetime.datetime.now().strftime("%Y-%m")
    #this defines current folder, e.g.: ~/share1/Obsidian/Experiments/2025-10/Instrument_Records
    working_folder = base_path / folder_name / "Instrument_Records"

    if working_folder.exists():
        #print(f"Folder already exists: {working_folder}")
        pass
    else:
        working_folder.mkdir(parents=True)
        #print(f"Folder created: {working_folder}")    

    return working_folder

def createMdFile():
    # create MM-DD-username.md file if needed, inside YYYY-MM/InstrumentRecords folder. These functions need to create the folder/file only if needed, or just pass. 
    working_folder = createMonthFolder()
    data_path = user_data.user_dir.get()
    # this returns something like /share1/USAXS_data/2026-01/1_14_setup 
    # we need the last folder name from data_path which will be the name of md file
    # we need to merge the working_folder/last folder name + ".md"
    last_folder_name = os.path.basename(os.path.normpath(data_path))
    # this returns "1_14_setup"
    md_filename = f"{last_folder_name}.md"
    md_file_path = working_folder / md_filename
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if md_file_path.exists():
        #print(f"Markdown file already exists: {md_file_path}")
        pass
    else:
        with open(md_file_path, "w") as f:
            f.write(f"# Experiment Notes by USAXS instrument\n")
            f.write(f"Date Time: {start_time}\n")
        #print(f"Markdown file created: {md_file_path}")
    return md_file_path

def appendToMdFile(text: str):
    # appends text to the end of the md file created above
    md_file_path = createMdFile()
    with open(md_file_path, "a") as f:
        f.write(text + "\n")
    #print(f"Appended to {md_file_path}: {text}")
    return

def recordUserStart():
    # called on newUser(), records basic user metadata in human language.
    user_name = user_data.user_name.get()
    sample_dir = user_data.sample_dir.get()
    #user_email = user_data.user_email.get()
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"## User Experiment Start\n \
            - **User Name:** {user_name}\n \
            - **Sample Dir:** {sample_dir}\n \
            - **Date Time:** {start_time}\n"
    appendToMdFile(text)
    return


def recordNewSample():
    # called by newSample(), records basic instrument settings
    mono_energy = monochromator.dcm.energy.readback
    aps_current = EpicsSignalRO("XFD:srCurrent", name="aps_current")    #this is how we get PV values from epics if needed. 
    und_energy = EpicsSignalRO("S12ID:USID:EnergyM.VAL", name="undualtor_energy")  #undulator energy in keV
    sample_dir = user_data.sample_dir.get()
    #undulator_energy = Component(EpicsSignalRO, "ID12ds:Energy")
    time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"## New Sample directory created\n \
            - **Sample dir:** {sample_dir}\n \
            - **APS Current (mA):** {aps_current.get()}\n  \
            - **Undulator Energy [keV]:** {und_energy.get()}\n \
            - **Mono X-ray Energy [keV]:** {mono_energy.get()}\n \
            - **Date Time:** {time_now}\n"
    appendToMdFile(text)
    return



