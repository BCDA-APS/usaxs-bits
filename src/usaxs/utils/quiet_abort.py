"""A user-requested abort is not an error -- stop printing it as one.

When the operator asks for a stop (the GUI sets ``usxLAX:StopBeforeNextScan``,
which :func:`usaxs.plans.requested_stop.IfRequestedStopBeforeNextScan` turns
into a ``RequestAbort``), everything downstream behaves correctly: shutters
close, ``after_command_list(aborted=True)`` cleans up, the abort is recorded in
Obsidian, and the queueserver reports ``Plan state: completed``.

The console, however, shows a sixty-line Python traceback at level ``E``.  That
comes from bluesky's RunEngine, which logs the control-flow exceptions the same
way it logs a crash::

    except (FailedPause, RequestAbort, asyncio.CancelledError, PlanHalt):
        self._exit_status = "abort"
        ...
        self.log.exception("Run aborted")

``log.exception`` forces ``exc_info``, so the whole stack is rendered, and to an
operator it reads as a failure when nothing has failed.

:func:`quiet_user_abort` installs a filter on the ``bluesky`` logger -- the
logger ``RE.log`` wraps -- that rewrites exactly that one record into a single
informational line.  It is deliberately narrow: it fires only on the message
``"Run aborted"`` carrying a ``RequestAbort`` or ``PlanHalt``, both of which
mean *a human stopped this*.  A genuine plan failure is logged from a different
branch of the RunEngine and keeps its traceback; ``asyncio.CancelledError`` and
``FailedPause`` are left alone too, because those do not mean the user asked.

Mutating the level inside a filter is safe here.  The logger's level check has
already passed by the time filters run, so this only changes how the record is
rendered -- ``E`` becomes ``I`` under the apsbits console format
``"%(levelname)-.1s %(asctime)s.%(msecs)03d: %(message)s"``.
"""

import logging

from bluesky.utils import PlanHalt
from bluesky.utils import RequestAbort

logger = logging.getLogger(__name__)

#: The RunEngine logs its abort under this exact message.
_ABORT_MESSAGE = "Run aborted"

#: Exceptions that mean the user asked for the stop, not that something broke.
_USER_ABORTS = (RequestAbort, PlanHalt)


class UserAbortIsNotAnError(logging.Filter):
    """Rewrite the RunEngine's ``Run aborted`` traceback for a user stop."""

    def filter(self, record):
        """Reshape *record* in place; never drop it."""
        if record.msg == _ABORT_MESSAGE and record.exc_info:
            exception = record.exc_info[1]
            if isinstance(exception, _USER_ABORTS):
                record.exc_info = None
                record.exc_text = None
                record.levelno = logging.INFO
                record.levelname = "INFO"
                record.msg = "Run aborted at user request: %s"
                record.args = (exception,)
        return True


def quiet_user_abort():
    """Install :class:`UserAbortIsNotAnError` on the ``bluesky`` logger.

    Idempotent, so re-importing ``usaxs.startup`` does not stack filters.
    """
    bluesky_logger = logging.getLogger("bluesky")
    for existing in bluesky_logger.filters:
        if isinstance(existing, UserAbortIsNotAnError):
            return
    bluesky_logger.addFilter(UserAbortIsNotAnError())
    logger.debug("User-requested aborts will be logged without a traceback.")
