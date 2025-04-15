"""
basic surveillance and logging of users' measurement code

A function to be called from users' custom code that
will archive that code for posterity. Similar to how the SPEC macros are recorded.

* Must be simple for user to call: yield from some_name()
* Must provide some value to user (or else they will not use it).
* Must copy user's code into posterity archive.

EXAMPLE::

    def myPlan(t_start, t_end, t_steps):
        text = f"measure from {t_start} to {t_end} in {t_steps} steps"
        instrument_archive(text)   # <---- ADD HERE

        t = t_start
        while t < t_end:
            yield from bps.mv(linkam.temperature, t)
            yield from bp.scan([detector], motor, 10, 20, 120)
            t += t_step

"""

import datetime
import inspect
import logging
import os
import resource
from collections import OrderedDict

import psutil

logger = logging.getLogger(os.path.split(__file__)[-1])


def _write_archive_dict_(archive_dict):
    """
    writes dictionary contents to USAXS archive file as text, returns revised dict
    """
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    archive_path = "/share1/log/macros"
    archive_file = os.path.join(archive_path, f"{ts}-usaxs.txt")
    archive_dict["archive_file"] = archive_file
    archive_dict["archive_timestamp"] = ts

    with open(archive_file, "w") as fp:
        for k, v in archive_dict.items():
            fp.write(f"# {k}:\n")
            if k == "source_contents":
                fp.write("-" * 20 + " source " + "-" * 20 + "\n")
                fp.writelines(v)
                fp.write("-" * 20 + " source " + "-" * 20 + "\n")
            else:
                fp.write(f"{v}\n")
            fp.write("\n")
        logger.debug("Archive: %s", archive_file)
    return archive_dict


def _create_archive_dict_(frame, text):
    """creates an archive dictionary from a stack frame (from usaxs_support)"""
    archive = OrderedDict()
    archive["text"] = text
    archive["source"] = frame.filename
    archive["is_file"] = not frame.filename.startswith("<")
    archive["line"] = frame.lineno
    archive["caller"] = frame.function
    archive["caller_code"] = "".join(frame.code_context)
    if archive["is_file"]:
        if os.path.exists(frame.filename):
            with open(frame.filename, "r") as fp:
                archive["source_contents"] = fp.readlines()
            logger.debug("source code file: %s", frame.filename)
        else:
            logger.debug("FileNotFound: %s", frame.filename)
            archive["source_contents"] = "source not found"
    return archive


def instrument_archive(text=None):
    """
    copies caller function (and its source file) to permanent archive, returns dict

    Any text supplied by the caller will be written at the start of the archive.
    """
    frameinfo = inspect.getouterframes(inspect.currentframe(), 2)
    logger.debug("instrument_archive() called from: %s", frameinfo[1].filename)

    # archive text and caller source file
    _write_archive_dict_(_create_archive_dict_(frameinfo[1], text or ""))

    # only return the text
    return text or ""


def looky():
    """Monitor and report system status.

    This function continuously monitors various system parameters and
    reports their status, including temperature, pressure, and other
    critical values.
    """
    text = """
    archive custom user code #228
    https://github.com/APS-USAXS/ipython-usaxs/issues/228

    This is just a demonstration.
    """
    print(instrument_archive(text))


def resource_usage(title=None, vmem=False):
    """
    report on current resource usage
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    msg = ""
    if title is not None:
        msg += f"{title}:"
    msg += f" user:{usage[0]:.3f}s"
    msg += f" sys:{usage[1]:.3f}s"
    msg += f" mem:{usage[2]/1000:.2f}MB"
    msg += f" cpu:{psutil.cpu_percent()}%"
    if vmem:
        msg += f" {psutil.virtual_memory()}"
    return msg.strip()


def get_current_time():
    """Get the current time in a formatted string.

    Returns:
        str: Current time formatted as 'YYYY-MM-DD HH:MM:SS'
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_current_date():
    """Get the current date in a formatted string.

    Returns:
        str: Current date formatted as 'YYYY-MM-DD'
    """
    return datetime.datetime.now().strftime("%Y-%m-%d")
