"""
Run queue-server operations without freezing the window.

Several ``bluesky_widgets`` model methods are called straight from a Qt button
handler -- i.e. on the main thread -- and default to ``timeout=0``, which means
*wait forever*::

    if timeout:
        t_stop = time.time() + timeout
    while True:
        self.load_re_manager_status()
        if <done>:
            break
        if timeout and (time.time() > t_stop):   # never true when timeout == 0
            raise RuntimeError(...)
        time.sleep(0.5)

Affected: ``environment_close``, ``environment_destroy``, ``re_resume``,
``re_stop``, ``re_abort``, ``re_halt`` (``environment_open`` and ``re_pause``
guard or omit their loops). If the condition can never be satisfied, the whole
GUI is dead -- no repaint, no menu, no way to reach the one action that would
fix it.

That is not hypothetical. On 2026-10-25 the RE worker exited without telling
the manager. The manager has no handler for that case -- its periodic poll does
``ws, _ = await self._worker_request_state()`` followed by ``if ws is not
None:`` with no ``else`` -- so it kept advertising
``worker_environment_exists: True`` indefinitely. Every press of "Close
Environment" froze the GUI permanently, *including after restarting it*,
because the fault was server-side.

``PolledOperationMixin`` replaces that pattern with: send the request once,
then watch for completion from a ``QTimer`` that reads the status dict the
background poller already maintains. Nothing blocks the main thread, nothing
adds I/O to it, and every operation has a deadline that ends in a dialog
saying what happened and what to do next.

Note that the queue server does not care whether we are watching: the request
is delivered when it is sent. The polling here only keeps the UI honest, so a
deadline expiring is informational, never destructive.
"""

import logging

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)

# How often to re-check the manager status. Only reads an already-maintained
# dict, so the cost is negligible.
POLL_INTERVAL_MS = 500


class PolledOperationMixin:
    """Mixin giving a Qt widget non-blocking, deadlined queue-server actions.

    The host widget must provide ``self.model`` (a ``RunEngineClient``) and
    implement ``_lock_buttons(locked)``; it should also call
    ``self._init_polling()`` at the end of its ``__init__``.
    """

    # Class-level default: the base class wires signals before our instance
    # attributes exist, and the enablement slot reads this.
    _pending = None

    def _init_polling(self):
        """Set up the completion-watching timer."""
        self._ticks_left = 0
        self._done_predicate = None
        self._on_timeout = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

    def _begin(self, label, request, done_predicate, timeout_s, on_timeout):
        """Send one request, then watch for completion until ``timeout_s``.

        Parameters
        ----------
        label : str
            Human-readable operation name, used in dialogs.
        request : callable
            Sends the request; returns the manager's reply dict.
        done_predicate : callable
            ``f(status_dict) -> bool``, True when the operation has landed.
        timeout_s : float
            Deadline, after which ``on_timeout`` is called.
        on_timeout : callable
            Invoked with no arguments once the deadline passes.
        """
        if self._pending:
            QMessageBox.information(
                self, "Busy", f"{self._pending} is already in progress."
            )
            return
        try:
            reply = request()
        except Exception as ex:
            QMessageBox.critical(self, f"{label} failed", f"{type(ex).__name__}: {ex}")
            return
        if not reply.get("success"):
            # The manager rejects invalid requests with a usable message
            # ("RE Worker environment already exists", etc.).
            QMessageBox.warning(
                self, f"{label} refused", reply.get("msg") or "Unknown error."
            )
            return

        self._pending = label
        self._done_predicate = done_predicate
        self._on_timeout = on_timeout
        self._ticks_left = max(1, int(timeout_s * 1000 / POLL_INTERVAL_MS))
        self._refresh_buttons()
        self._poll_timer.start()

    def _poll(self):
        """Check whether the pending operation finished or ran out of time."""
        if not self._pending:
            self._poll_timer.stop()
            return

        if not self.model.re_manager_connected:
            label = self._pending
            self._finish()
            QMessageBox.critical(
                self,
                "Queue server unreachable",
                f"Lost contact with the RE Manager while waiting for "
                f"{label.lower()} to finish.\n\n"
                "The operation may or may not have completed.",
            )
            return

        status = self.model.re_manager_status or {}
        try:
            done = bool(self._done_predicate(status))
        except Exception:
            logger.exception("Error evaluating completion for %s", self._pending)
            done = False
        if done:
            self._finish()
            return

        self._ticks_left -= 1
        if self._ticks_left <= 0:
            on_timeout = self._on_timeout
            self._finish()
            on_timeout()

    def _finish(self):
        """Clear the pending operation and re-enable the buttons."""
        self._poll_timer.stop()
        self._pending = None
        self._done_predicate = None
        self._on_timeout = None
        self._refresh_buttons()

    def _refresh_buttons(self):
        """Re-apply enablement from the current model state."""
        self.slot_update_widgets(
            bool(self.model.re_manager_connected), self.model.re_manager_status or {}
        )
