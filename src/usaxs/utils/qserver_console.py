"""Stop the queueserver console view from showing every log line twice.

The queueserver worker runs the session inside an IPython kernel
(``worker.use_ipython_kernel: true`` in ``qserver/qs-config.yml``), and that
arrangement makes a logging handler created during startup deliver its records
to the console twice.  The sequence, in ``bluesky_queueserver``'s worker:

1. ``setup_console_output_redirection()`` replaces ``sys.stdout``/``sys.stderr``
   with a ``ConsoleOutputStream`` that feeds the ZMQ console channel -- what the
   GUI console view displays.  The worker then aliases ``sys.__stdout__`` and
   ``sys.__stderr__`` to that same object.
2. ``IPKernelApp.initialize()`` runs with ``quiet = False``, so ``init_io()``
   builds an ipykernel ``OutStream`` whose ``echo`` is ``sys.__stderr__`` -- the
   console stream.  Output therefore reaches the console twice over: once
   through the echo, once through the iopub message the worker's monitor thread
   forwards.  That is deliberate: during initialization the monitor discards
   iopub ``stream`` messages (they carry no ``parent_header``), so the echo is
   the only path that works.
3. Still inside ``initialize()``, ``init_code()`` imports the startup module.
   Importing ``apsbits`` calls ``configure_logging()``, whose
   ``logging.basicConfig()`` creates the root console handler bound to
   ``sys.stderr`` *as it is at that moment* -- the echoing ``OutStream``.
4. ``initialize()`` returns, the worker sets ``quiet = True`` and calls
   ``init_io()`` again.  ``sys.stdout``/``sys.stderr`` become fresh, non-echoing
   ``OutStream``s, so ``print()`` from a plan is delivered once.  The root
   logging handler, however, still holds the *old* echoing stream -- so every
   ``logger.info(...)`` keeps arriving twice for the life of the session.

The fix is to stop pinning the handler to one stream object: point it at a
proxy that resolves ``sys.stderr`` on each write.  Records then follow whichever
stream is current -- the echoing one during startup (one copy, via the echo) and
the quiet one afterwards (one copy, via iopub).

Only relevant under the queueserver; a plain IPython console has no second
delivery path, so :func:`follow_live_stderr` is called only when
``running_in_queueserver()``.
"""

import io
import logging
import sys

logger = logging.getLogger(__name__)


class LiveStderr(io.TextIOBase):
    """Write-through proxy for whatever ``sys.stderr`` is at write time."""

    def write(self, s):
        """Write *s* to the current ``sys.stderr``."""
        return sys.stderr.write(s)

    def flush(self):
        """Flush the current ``sys.stderr``, ignoring a closed stream."""
        try:
            sys.stderr.flush()
        except (AttributeError, ValueError):
            pass

    def writable(self):
        """Report this stream as writable (``logging`` checks nothing else)."""
        return True


def follow_live_stderr():
    """Re-point the root console log handler at the live ``sys.stderr``.

    Call once, early in ``startup.py``, when running under the queueserver.
    File handlers are left alone.

    Returns
    -------
    int
        Number of handlers that were re-pointed.
    """
    count = 0
    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.StreamHandler):
            continue
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler.stream, LiveStderr):
            continue  # already done
        handler.setStream(LiveStderr())
        count += 1
    logger.debug("console log handlers re-pointed at live sys.stderr: %d", count)
    return count
