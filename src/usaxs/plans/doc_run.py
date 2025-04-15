"""
Save text as a bluesky run.
"""

__all__ = [
    "documentation_run",
]

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from bluesky import plan_stubs as bps
from ophyd import Signal

from ..framework import bec

logger = logging.getLogger(__name__)
logger.info(__file__)


def documentation_run(
    words: str, md: Optional[Dict[str, Any]] = None, stream: Optional[str] = None
) -> Generator[Any, None, str]:
    """
    Save text as a bluesky run.
    """
    text = Signal(value=words, name="text")
    stream = stream or "primary"
    _md = dict(
        purpose="save text as bluesky run",
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
