
"""
Save text as a bluesky run.
"""

__all__ = [
    "documentation_run",
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ..framework import bec
from bluesky import plan_stubs as bps
from ophyd import Signal


def documentation_run(words, md=None, stream=None):
    """
    Save text as a bluesky run.
    """
    text = Signal(value=words, name="text")
    stream = stream or "primary"
    _md = dict(
        purpose=f"save text as bluesky run",
        plan_name="documentation_run",
    )
    _md.update(md or {})
    bec.disable_plots()
    bec.disable_table()
    uid = yield from bps.open_run(md=_md)
    yield from bps.create(stream)
    yield from bps.read(text)
    yield from bps.save()
    yield from bps.close_run()
    bec.enable_table()
    bec.enable_plots()
    return uid
