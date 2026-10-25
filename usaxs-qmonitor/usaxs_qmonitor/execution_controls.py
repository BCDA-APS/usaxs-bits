"""
Resume / Stop / Abort / Halt that cannot freeze the window.

``RunEngineClient.re_resume``, ``.re_stop``, ``.re_abort`` and ``.re_halt`` all
end in ``_wait_for_completion(..., timeout=0)``, which loops forever on the Qt
main thread until the manager reaches the expected state -- see
``nonblocking_ops`` for the loop and the incident behind this.

These are the buttons someone reaches for at 3 a.m. when a scan has gone wrong,
and they are pressed in exactly the circumstances where the worker may be
unresponsive. Freezing the window at that moment is the worst possible
behaviour: the operator loses the console, the queue view, and any other way to
see what is happening.

``Pause`` is left alone -- upstream has its wait commented out, so it already
returns immediately.

Deadlines here are generous and purely informational. The request reaches the
queue server when it is sent; a plan that takes two minutes to abort is doing
its cleanup, not failing, so the dialog says so rather than offering to break
anything.
"""

from bluesky_widgets.qt.run_engine_client import QtReExecutionControls
from qtpy.QtWidgets import QMessageBox

from .nonblocking_ops import PolledOperationMixin

# A plan being stopped cleanly can take a while: cleanup, returning stages,
# finishing a sweep. Only after this does the user get a "still running" note.
RESUME_TIMEOUT_S = 180
STOP_TIMEOUT_S = 180


def _idle(status):
    return status.get("manager_state") == "idle"


def _running_or_idle(status):
    return status.get("manager_state") in ("idle", "executing_queue")


class QtUsaxsExecutionControls(PolledOperationMixin, QtReExecutionControls):
    """Execution controls that never block the Qt main thread."""

    def __init__(self, model, parent=None):
        """Re-wire resume/stop/abort/halt onto non-blocking handlers."""
        super().__init__(model, parent)

        for button, slot in (
            (self._pb_plan_resume, self._resume_clicked),
            (self._pb_plan_stop, self._stop_clicked),
            (self._pb_plan_abort, self._abort_clicked),
            (self._pb_plan_halt, self._halt_clicked),
        ):
            try:
                button.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            button.clicked.connect(slot)

        self._init_polling()

    # --- Button handlers ---
    def _resume_clicked(self):
        self._begin(
            "Resume",
            self.model._client.re_resume,
            _running_or_idle,
            RESUME_TIMEOUT_S,
            lambda: self._timed_out("Resume"),
        )

    def _stop_clicked(self):
        self._begin(
            "Stop",
            self.model._client.re_stop,
            _idle,
            STOP_TIMEOUT_S,
            lambda: self._timed_out("Stop"),
        )

    def _abort_clicked(self):
        self._begin(
            "Abort",
            self.model._client.re_abort,
            _idle,
            STOP_TIMEOUT_S,
            lambda: self._timed_out("Abort"),
        )

    def _halt_clicked(self):
        self._begin(
            "Halt",
            self.model._client.re_halt,
            _idle,
            STOP_TIMEOUT_S,
            lambda: self._timed_out("Halt"),
        )

    def _timed_out(self, label):
        QMessageBox.information(
            self,
            f"{label} not finished yet",
            f"The queue server accepted {label}, but the RunEngine has not "
            f"returned to idle after {STOP_TIMEOUT_S} s.\n\n"
            "The request was delivered -- this window simply stopped waiting "
            "for it. A plan can take a long time to unwind (returning stages, "
            "finishing a sweep). Watch the console in the Live View tab.\n\n"
            "If nothing moves at all, the worker may have died: close the "
            "environment, and accept the offer to destroy it if the close "
            "does not finish.",
        )

    # --- Keep the buttons disabled while an operation is in flight ---
    def slot_update_widgets(self, is_connected, status):
        """Apply the base enablement rules, then lock during an operation."""
        super().slot_update_widgets(is_connected, status)
        if self._pending:
            for button in (
                self._pb_plan_resume,
                self._pb_plan_stop,
                self._pb_plan_abort,
                self._pb_plan_halt,
            ):
                button.setEnabled(False)
