"""
test if file name exists, Windows-unique

see: https://github.com/APS-USAXS/ipython-usaxs/issues/343
"""

__all__ = [
    "filename_exists",
]


import os


def filename_exists(fname, case_insensitive=True):
    """
    test if a file name exists, even case-insensitive
    """
    if os.path.exists(fname):
        return True
    if not case_insensitive:
        return False

    # check all filenames for case-insensitive match
    # see: https://github.com/APS-USAXS/ipython-usaxs/issues/343
    path, filename = os.path.split(fname)
    if path == "":
        path = "."
    if not os.path.exists(path):
        return False

    fn_lower = filename.lower()
    for item in os.listdir(path):
        if fn_lower == item.lower():
            return True

    return False
