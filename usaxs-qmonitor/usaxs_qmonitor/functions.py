"""
USAXS custom action bar: script upload (Phase 1) and function buttons (Phase 2).

The bar takes the ``UsaxsRunEngineClient`` model and calls its extra methods
(``script_upload``, ``function_execute``). Queueserver tasks run asynchronously
in the RE Worker, so results are polled with a non-blocking ``QTimer`` and the
outcome (success or traceback) is surfaced to the user.
"""

import os
import time

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from .settings import SETTINGS

# How long to wait for an uploaded script's task to finish (plan definitions are
# effectively instant; a slow import is the worst case).
_TASK_TIMEOUT_S = 30
_POLL_INTERVAL_MS = 300


class QtUsaxsActionBar(QWidget):
    """Row of USAXS-specific action buttons above the command designer."""

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model  # UsaxsRunEngineClient

        self._work_dir = SETTINGS.plans_dir

        self._pb_load_plan = QPushButton("Load plan file…")
        self._pb_load_plan.setToolTip(
            "Upload a Python file into the running RE Worker (like 'qserver "
            "script upload'). New/updated plans appear in the command designer."
        )
        self._pb_load_plan.clicked.connect(self._load_plan_file_clicked)

        self._status_lbl = QLabel("")

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(self._pb_load_plan)
        hbox.addWidget(self._status_lbl, stretch=1)
        hbox.addStretch()
        self.setLayout(hbox)

        # Async task polling state.
        self._pending_uid = None
        self._pending_name = ""
        self._poll_deadline = 0.0
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_task)

    # --- Script upload ("Load plan file…") ---
    def _load_plan_file_clicked(self):
        if self._pending_uid is not None:
            QMessageBox.information(
                self, "Busy", "A script upload is already in progress."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load plan file", self._work_dir, "Python (*.py);; All (*)"
        )
        if not file_path:
            return
        self._work_dir = os.path.dirname(file_path)
        name = os.path.basename(file_path)

        try:
            resp = self.model.script_upload(file_path)
        except Exception as ex:  # file read / connection error
            QMessageBox.critical(self, "Upload failed", f"{type(ex).__name__}: {ex}")
            return

        uid = resp.get("task_uid")
        if not resp.get("success") or not uid:
            QMessageBox.critical(
                self, "Upload rejected", resp.get("msg") or "Unknown error"
            )
            return

        self._pending_uid = uid
        self._pending_name = name
        self._poll_deadline = time.monotonic() + _TASK_TIMEOUT_S
        self._set_busy(True)
        self._status_lbl.setText(f"Uploading {name}…")
        self._poll_timer.start()

    def _poll_task(self):
        uid = self._pending_uid
        if uid is None:
            self._poll_timer.stop()
            return

        try:
            res = self.model.task_result(uid)
        except Exception:
            # Task may not be registered yet, or a transient error; retry next tick.
            if time.monotonic() > self._poll_deadline:
                self._finish(ok=False, message="Upload timed out (no task result).")
            return

        if res.get("status") == "running":
            if time.monotonic() > self._poll_deadline:
                self._finish(ok=False, message="Upload timed out (task still running).")
            return

        # Task finished (status == "completed"); inspect the payload.
        payload = res.get("result") or {}
        if payload.get("success"):
            self._finish(ok=True, message=f"Loaded {self._pending_name} ✓")
        else:
            tb = payload.get("traceback") or payload.get("msg") or "Unknown error."
            self._finish(
                ok=False,
                message=f"Load failed: {self._pending_name}",
                traceback_text=tb,
            )

    def _finish(self, *, ok, message, traceback_text=None):
        self._poll_timer.stop()
        name = self._pending_name
        self._pending_uid = None
        self._pending_name = ""
        self._set_busy(False)
        self._status_lbl.setText(message)
        if ok:
            # Refresh allowed plans so newly defined plans appear in the editor.
            try:
                self.model.load_allowed_plans()
            except Exception as ex:
                print(f"Failed to refresh allowed plans: {ex}")
        elif traceback_text is not None:
            self._show_traceback(name, traceback_text)

    def _set_busy(self, busy):
        self._pb_load_plan.setEnabled(not busy)

    def _show_traceback(self, name, traceback_text):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Script upload failed")
        box.setText(f"Uploading {name!r} raised an error in the RE Worker.")
        box.setInformativeText("The worker namespace was not changed by the failed part.")
        box.setDetailedText(traceback_text)
        box.exec_()
