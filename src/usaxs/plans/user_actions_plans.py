"""
Queueable wrappers for interactive user/sample setup functions.

These expose :func:`usaxs.utils.setup_new_user.newUser` and
:func:`usaxs.utils.setup_new_user.newSample` as Bluesky *plans* so they can be
placed in the queueserver queue (for example, queue ``new_sample_plan`` between
scans). For immediate, interactive use the GUI calls the functions directly via
the queueserver ``function_execute`` API; use these plan wrappers when you want
the action sequenced through the RunEngine/queue instead.

Both wrappers require explicit arguments: the underlying functions fall back to
``input()`` when an argument is ``None``, which would block the headless worker.
"""

from bluesky import plan_stubs as bps

from usaxs.utils.setup_new_user import newSample
from usaxs.utils.setup_new_user import newUser


def new_user_plan(user, sample="data", scan_id=1, skip_bss=False):
    """Bluesky plan: queueable wrapper around ``newUser()``.

    Parameters
    ----------
    user : str
        User/beamtime name (required; used in the directory name and EPICS PV).
    sample : str, optional
        Initial sample directory name. Default ``"data"``.
    scan_id : int, optional
        Starting scan ID for the SPEC file. Default ``1``.
    skip_bss : bool, optional
        If ``True``, skip the BSS lookup (commissioning / no active ESAF).
    """
    yield from bps.null()
    newUser(user=user, sample=sample, scan_id=scan_id, skip_bss=skip_bss)


def new_sample_plan(sample):
    """Bluesky plan: queueable wrapper around ``newSample()``.

    Parameters
    ----------
    sample : str
        Sample directory name (required). ``newUser()`` must have been run first
        (the ``.user_info.json`` state file must exist) or the underlying
        function raises ``RuntimeError``.
    """
    yield from bps.null()
    newSample(sample=sample)
