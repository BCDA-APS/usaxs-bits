"""
return a clean version of input text
"""

import logging
import os
import pathlib

from apsbits.core.instrument_init import oregistry

logger = logging.getLogger(__name__)
logger.info(__file__)

user_data = oregistry["user_data"]

# import re

# def cleanupText(text):
#     """
#     given some input text string, return a clean version

#     remove troublesome characters, perhaps other cleanup as well

#     this is best done with regular expression pattern matching
#     """
#     pattern = "[a-zA-Z0-9_]"

#     def mapper(c):
#         if re.match(pattern, c) is not None:
#             return c
#         return "_"

#     return "".join([mapper(c) for c in text])


def get_data_dir():
    """
    Get the data directory from EPICS.

    The directory MUST exist or raises a FileNotFoundError exception.
    """
    data_path = pathlib.Path(user_data.user_dir.get())
    if not data_path.exists():
        raise FileNotFoundError(f"Cannot find user directory: {data_path}")
    return str(data_path)


def techniqueSubdirectory(technique):
    """
    Create a technique-based subdirectory per table in ``newUser()``.

    NOTE:   Assumes CWD is now the directory returned by ``newFile()``
            Add a subdirectory based on user_data.sample_name 
    """
    data_path = get_data_dir()  # this is typically /share1/USAXS_data/02_05_Username

    sampleFolder = user_data.sample_name.get().strip()  # should be set in newUser(), shoudl return relatively simple name for sample, e.g., Sample1
    if sampleFolder == "":
        sampleFolder = "sample"
    sampleFolder = sampleFolder.replace(" ", "_")       # replace spaces with underscores
    data_path = os.path.join(data_path, sampleFolder)   # add sample name to path
    if not os.path.exists(data_path):                   # create sample directory if needed
        logger.info("Creating sample directory: %s", data_path)
        os.mkdir(data_path)

    stub = os.path.basename(data_path)                  # should be something like Sample1
    path = os.path.join(data_path, f"{stub}_{technique}")# shoudl add Sample1_usaxs etc. 

    if not os.path.exists(path):
        logger.info("Creating technique directory: %s", path)
        os.mkdir(path)

    return os.path.abspath(path)
