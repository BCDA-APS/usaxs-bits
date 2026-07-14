"""
USAXS custom action bar: script upload (Phase 1) and function execution (Phase 2).

The bar takes the ``UsaxsRunEngineClient`` model and calls its extra methods
(``script_upload``, ``function_execute``). Queueserver tasks run asynchronously
in the RE Worker, so every task's result is polled with a shared non-blocking
``QTimer`` and the outcome (success, return value, or traceback) is surfaced to
the user.

The dialogs always pass explicit arguments: ``newUser`` / ``newSample`` fall back
to ``input()`` when an argument is ``None``, which would hang the headless worker.
"""

import os
import time

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QCheckBox
from qtpy.QtWidgets import QDialog
from qtpy.QtWidgets import QDialogButtonBox
from qtpy.QtWidgets import QFileDialog
from qtpy.QtWidgets import QFormLayout
from qtpy.QtWidgets import QHBoxLayout
from qtpy.QtWidgets import QLabel
from qtpy.QtWidgets import QLineEdit
from qtpy.QtWidgets import QMessageBox
from qtpy.QtWidgets import QPushButton
from qtpy.QtWidgets import QSpinBox
from qtpy.QtWidgets import QWidget

from .settings import SETTINGS

# How long to wait for a worker task to finish (plan definitions and metadata
# functions are quick; newUser does some filesystem work but is still short).
_TASK_TIMEOUT_S = 60
_POLL_INTERVAL_MS = 300


class NewUserDialog(QDialog):
    """Collect arguments for ``newUser(...)``."""

    def __init__(self, parent=None):
        """Build the New User dialog form."""
        super().__init__(parent)
        self.setWindowTitle("New User")

        self._user = QLineEdit()
        self._user.setPlaceholderText("required — user/beamtime name")
        self._sample = QLineEdit("data")
        self._scan_id = QSpinBox()
        self._scan_id.setRange(1, 1_000_000)
        self._scan_id.setValue(1)
        self._skip_bss = QCheckBox("Skip BSS lookup (commissioning / no ESAF)")

        form = QFormLayout()
        form.addRow("User name:", self._user)
        form.addRow("Sample:", self._sample)
        form.addRow("Start scan ID:", self._scan_id)
        form.addRow("", self._skip_bss)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        form.addRow(buttons)
        self.setLayout(form)

    def _on_accept(self):
        if not self._user.text().strip():
            QMessageBox.warning(self, "Missing name", "User name is required.")
            return
        self.accept()

    def kwargs(self):
        """Return keyword args for newUser (only GUI-facing ones)."""
        return {
            "user": self._user.text().strip(),
            "sample": self._sample.text().strip() or "data",
            "scan_id": self._scan_id.value(),
            "skip_bss": self._skip_bss.isChecked(),
        }


class NewSampleDialog(QDialog):
    """Collect the sample name for ``newSample(...)``."""

    def __init__(self, parent=None):
        """Build the New Sample dialog form."""
        super().__init__(parent)
        self.setWindowTitle("New Sample")

        self._sample = QLineEdit()
        self._sample.setPlaceholderText("required — sample directory name")

        form = QFormLayout()
        form.addRow("Sample name:", self._sample)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)

    def _on_accept(self):
        if not self._sample.text().strip():
            QMessageBox.warning(self, "Missing name", "Sample name is required.")
            return
        self.accept()

    def kwargs(self):
        """Return keyword args for newSample."""
        return {"sample": self._sample.text().strip()}


class QtUsaxsActionBar(QWidget):
    """Row of USAXS-specific action buttons above the command designer."""

    def __init__(self, model, *args, **kwargs):
        """Build the action bar bound to a UsaxsRunEngineClient model."""
        super().__init__(*args, **kwargs)
        self.model = model  # UsaxsRunEngineClient

        self._work_dir = SETTINGS.plans_dir

        self._pb_new_user = QPushButton("New User…")
        self._pb_new_user.setToolTip("Run newUser(...) in the worker (do it now).")
        self._pb_new_user.clicked.connect(self._new_user_clicked)

        self._pb_new_sample = QPushButton("New Sample…")
        self._pb_new_sample.setToolTip("Run newSample(...) in the worker (do it now).")
        self._pb_new_sample.clicked.connect(self._new_sample_clicked)

        self._pb_load_plan = QPushButton("Load plan file…")
        self._pb_load_plan.setToolTip(
            "Upload a Python file into the running RE Worker (like 'qserver "
            "script upload'). New/updated plans appear in the command designer."
        )
        self._pb_load_plan.clicked.connect(self._load_plan_file_clicked)

        self._buttons = [self._pb_new_user, self._pb_new_sample, self._pb_load_plan]

        self._status_lbl = QLabel("")

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(QLabel("USAXS:"))
        hbox.addWidget(self._pb_new_user)
        hbox.addWidget(self._pb_new_sample)
        hbox.addWidget(self._pb_load_plan)
        hbox.addWidget(self._status_lbl, stretch=1)
        hbox.addStretch()
        self.setLayout(hbox)

        # Shared async task-polling state.
        self._pending_uid = None
        self._pending_label = ""
        self._on_success = None  # callable(payload) -> str message, or None
        self._poll_deadline = 0.0
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_task)

    # --- Readiness guard ---
    def _ready_or_warn(self):
        """Return True if the worker environment is open and the manager is idle.

        Otherwise show a clear message. This avoids the raw manager errors
        ("RE Worker environment is not open" / "must be in idle state") that
        appear if an action is triggered before the environment has finished
        opening — at the beamline, opening the environment can take a while.
        """
        status = self.model.re_manager_status or {}
        if not status.get("worker_environment_exists"):
            QMessageBox.warning(
                self,
                "Environment not open",
                "The RE Worker environment is not open (or is still opening).\n\n"
                "Open the environment and wait until the status shows 'idle', "
                "then try again.",
            )
            return False
        state = status.get("manager_state")
        if state != "idle":
            QMessageBox.warning(
                self,
                "Manager busy",
                f"The RE Manager is not idle (state: {state!r}).\n\n"
                "Wait until it is idle, then try again.",
            )
            return False
        return True

    # --- Buttons ---
    def _new_user_clicked(self):
        if self._busy() or not self._ready_or_warn():
            return
        dlg = NewUserDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        kw = dlg.kwargs()
        self._execute_function(
            "newUser",
            label=f"newUser({kw['user']!r})",
            kwargs=kw,
            on_success=lambda payload: self._data_dir_message("newUser", payload),
        )

    def _new_sample_clicked(self):
        if self._busy() or not self._ready_or_warn():
            return
        dlg = NewSampleDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        kw = dlg.kwargs()
        self._execute_function(
            "newSample",
            label=f"newSample({kw['sample']!r})",
            kwargs=kw,
            on_success=lambda payload: f"newSample: {kw['sample']} ✓",
        )

    def _load_plan_file_clicked(self):
        if self._busy() or not self._ready_or_warn():
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
        self._start_task(
            resp,
            label=f"Loaded {name}",
            busy_message=f"Uploading {name}…",
            reject_title="Upload rejected",
            on_success=self._on_plan_upload_success,
        )

    # --- Function execution helper ---
    def _execute_function(self, name, *, label, kwargs, on_success):
        try:
            resp = self.model.function_execute(name, **kwargs)
        except Exception as ex:
            QMessageBox.critical(self, "Execution failed", f"{type(ex).__name__}: {ex}")
            return
        self._start_task(
            resp,
            label=label,
            busy_message=f"Running {label}…",
            reject_title="Execution rejected",
            on_success=on_success,
        )

    # --- Shared task lifecycle ---
    def _busy(self):
        if self._pending_uid is not None:
            QMessageBox.information(
                self, "Busy", "Another action is already in progress."
            )
            return True
        return False

    def _start_task(self, resp, *, label, busy_message, reject_title, on_success):
        uid = resp.get("task_uid")
        if not resp.get("success") or not uid:
            QMessageBox.critical(self, reject_title, resp.get("msg") or "Unknown error")
            return
        self._pending_uid = uid
        self._pending_label = label
        self._on_success = on_success
        self._poll_deadline = time.monotonic() + _TASK_TIMEOUT_S
        self._set_busy(True)
        self._status_lbl.setText(busy_message)
        self._poll_timer.start()

    def _poll_task(self):
        uid = self._pending_uid
        if uid is None:
            self._poll_timer.stop()
            return

        try:
            res = self.model.task_result(uid)
        except Exception:
            # Task may not be registered yet, or a transient error; retry.
            if time.monotonic() > self._poll_deadline:
                self._finish(ok=False, message="Timed out (no task result).")
            return

        if res.get("status") == "running":
            if time.monotonic() > self._poll_deadline:
                self._finish(ok=False, message="Timed out (task still running).")
            return

        # Task finished; inspect the payload.
        payload = res.get("result") or {}
        if payload.get("success"):
            on_success = self._on_success
            message = None
            if on_success is not None:
                try:
                    message = on_success(payload)
                except Exception as ex:
                    print(f"on_success callback error: {ex}")
            self._finish(ok=True, message=message or f"{self._pending_label} ✓")
        else:
            tb = payload.get("traceback") or payload.get("msg") or "Unknown error."
            self._finish(
                ok=False,
                message=f"Failed: {self._pending_label}",
                traceback_text=tb,
            )

    def _finish(self, *, ok, message, traceback_text=None):
        self._poll_timer.stop()
        label = self._pending_label
        self._pending_uid = None
        self._pending_label = ""
        self._on_success = None
        self._set_busy(False)
        self._status_lbl.setText(message)
        if not ok and traceback_text is not None:
            self._show_traceback(label, traceback_text)

    # --- on_success helpers ---
    def _on_plan_upload_success(self, payload):
        # Refresh allowed plans so newly defined plans appear in the editor.
        try:
            self.model.load_allowed_plans()
        except Exception as ex:
            print(f"Failed to refresh allowed plans: {ex}")
        return f"{self._pending_label} ✓"

    @staticmethod
    def _data_dir_message(fn, payload):
        rv = payload.get("return_value")
        if isinstance(rv, str) and rv:
            return f"{fn} ✓  →  {rv}"
        return f"{fn} ✓"

    # --- UI helpers ---
    def _set_busy(self, busy):
        for pb in self._buttons:
            pb.setEnabled(not busy)

    def _show_traceback(self, label, traceback_text):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Action failed")
        box.setText(f"{label} raised an error in the RE Worker.")
        box.setDetailedText(traceback_text)
        box.exec_()
