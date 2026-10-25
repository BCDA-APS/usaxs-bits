"""
Environment Open/Close/Destroy that cannot freeze the window.

``bluesky_widgets``' ``QtReEnvironmentControls`` calls
``RunEngineClient.environment_close()`` directly from the button handler, and
that method waits forever by default -- see ``nonblocking_ops`` for the shape
of the loop and the incident that motivated replacing it.

The three buttons are re-wired here onto :class:`PolledOperationMixin`, so the
window stays live and a stuck operation ends in a dialog that names the likely
cause and offers the next step.
"""

from bluesky_widgets.qt.run_engine_client import QtReEnvironmentControls
from qtpy.QtWidgets import QMessageBox

from .nonblocking_ops import PolledOperationMixin

# Opening loads every device and talks to EPICS, so it gets much longer than
# the other two.
OPEN_TIMEOUT_S = 180
CLOSE_TIMEOUT_S = 60
DESTROY_TIMEOUT_S = 60


class QtUsaxsEnvironmentControls(PolledOperationMixin, QtReEnvironmentControls):
    """Environment controls that never block the Qt main thread."""

    def __init__(self, model, parent=None):
        """Re-wire the three buttons onto non-blocking handlers."""
        super().__init__(model, parent)

        for button, slot in (
            (self._pb_env_open, self._open_clicked),
            (self._pb_env_close, self._close_clicked),
            (self._pb_env_destroy, self._destroy_clicked),
        ):
            try:
                button.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            button.clicked.connect(slot)

        self._init_polling()

    # --- Button handlers ---
    def _open_clicked(self):
        self._begin(
            "Open environment",
            self.model._client.environment_open,
            lambda s: (
                s.get("worker_environment_exists") and s.get("manager_state") == "idle"
            ),
            OPEN_TIMEOUT_S,
            self._timed_out_opening,
        )

    def _close_clicked(self):
        self._begin(
            "Close environment",
            self.model._client.environment_close,
            lambda s: (
                not s.get("worker_environment_exists")
                and s.get("manager_state") == "idle"
            ),
            CLOSE_TIMEOUT_S,
            self._timed_out_closing,
        )

    def _destroy_clicked(self):
        self._begin(
            "Destroy environment",
            self.model._client.environment_destroy,
            lambda s: (
                not s.get("worker_environment_exists")
                and s.get("manager_state") == "idle"
            ),
            DESTROY_TIMEOUT_S,
            self._timed_out_destroying,
        )

    # --- Timeout dialogs: each names the cause and the next step ---
    def _timed_out_opening(self):
        QMessageBox.warning(
            self,
            "Environment did not open",
            f"The environment has not opened after {OPEN_TIMEOUT_S} s.\n\n"
            "It may still be loading devices -- check the console in the Live "
            "View tab. If it is stuck, use Destroy Environment and try again.",
        )

    def _timed_out_closing(self):
        answer = QMessageBox.question(
            self,
            "Environment will not close",
            f"The environment has not closed after {CLOSE_TIMEOUT_S} s.\n\n"
            "This usually means the RE worker process has died without "
            "telling the manager, which then keeps reporting an environment "
            "that is no longer there. A normal close can never finish in that "
            "state.\n\n"
            "Destroy the environment now? Nothing is lost if the queue is "
            "empty and no plan is running.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._destroy_clicked()

    def _timed_out_destroying(self):
        QMessageBox.critical(
            self,
            "Environment will not be destroyed",
            f"The environment is still present {DESTROY_TIMEOUT_S} s after "
            "Destroy was requested.\n\n"
            "The queue server itself needs restarting:\n"
            "    ./scripts/usaxs_qs_host.sh restart\n\n"
            "This window stays usable; nothing here is frozen.",
        )

    # --- Keep the buttons disabled while an operation is in flight ---
    def slot_update_widgets(self, is_connected, status):
        """Apply the base enablement rules, then lock during an operation."""
        super().slot_update_widgets(is_connected, status)
        if self._pending:
            self._pb_env_open.setEnabled(False)
            self._pb_env_close.setEnabled(False)
            self._pb_env_destroy.setEnabled(False)
