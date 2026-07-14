"""Window + menus for the USAXS queue-monitor GUI."""

import os

from bluesky_widgets.qt import Window
from qtpy.QtWidgets import QAction
from qtpy.QtWidgets import QFileDialog
from qtpy.QtWidgets import QMessageBox

from .run_engine_client import UsaxsRunEngineClient
from .settings import SETTINGS
from .widgets import QtViewer


class ViewerModel:
    """Holds the (non-Qt) models for the application."""

    def __init__(self):
        """Construct the UsaxsRunEngineClient from SETTINGS."""
        self.run_engine = UsaxsRunEngineClient(
            zmq_control_addr=SETTINGS.zmq_re_manager_control_addr,
            zmq_info_addr=SETTINGS.zmq_re_manager_info_addr,
            http_server_uri=SETTINGS.http_server_uri,
            http_server_api_key=SETTINGS.http_server_api_key,
            user_name=SETTINGS.user_name,
            user_group=SETTINGS.user_group,
        )


class UsaxsViewer(ViewerModel):
    """Extends the model with a Qt window as its view."""

    def __init__(self, *, show=True, title="USAXS Queue Monitor"):
        """Build the window, menus, and wire status updates."""
        super().__init__()

        self._work_dir = os.path.expanduser("~")

        self._widget = QtViewer(self)
        self._window = Window(self._widget, show=show)

        qt_window = self._window._qt_window
        qt_window.setWindowTitle(
            f"USAXS Queue Monitor — {SETTINGS.user_name}@{SETTINGS.user_group}"
        )
        qt_window.resize(1280, 900)

        # Auto-connect the live document stream (harmless if the proxy is down).
        if SETTINGS.plots_autostart:
            self.plots.connect_stream()

        menu_bar = self._window._qt_window.menuBar()
        menu_item_control = menu_bar.addMenu("Control Actions")
        self.action_activate_env_destroy = QAction(
            "Activate 'Destroy Environment'", self._window._qt_window
        )
        self.action_activate_env_destroy.setCheckable(True)
        self._update_action_env_destroy_state()
        self.action_activate_env_destroy.triggered.connect(
            self._activate_env_destroy_triggered
        )
        menu_item_control.addAction(self.action_activate_env_destroy)

        menu_item_save = menu_bar.addMenu("Save and Backup")
        self.action_save_history_as_txt = QAction(
            "Save Plan History (as .txt)", self._window._qt_window
        )
        self.action_save_history_as_txt.triggered.connect(
            self._save_history_as_txt_triggered
        )
        menu_item_save.addAction(self.action_save_history_as_txt)
        self.action_save_history_as_json = QAction(
            "Save Plan History (as .json)", self._window._qt_window
        )
        self.action_save_history_as_json.triggered.connect(
            self._save_history_as_json_triggered
        )
        menu_item_save.addAction(self.action_save_history_as_json)
        self.action_save_history_as_yaml = QAction(
            "Save Plan History (as .yaml)", self._window._qt_window
        )
        self.action_save_history_as_yaml.triggered.connect(
            self._save_history_as_yaml_triggered
        )
        menu_item_save.addAction(self.action_save_history_as_yaml)

        menu_item_help = menu_bar.addMenu("Help")
        self.action_connection_info = QAction(
            "Connection Info…", self._window._qt_window
        )
        self.action_connection_info.triggered.connect(self._show_connection_info)
        menu_item_help.addAction(self.action_connection_info)

        self._widget.model.run_engine.events.status_changed.connect(
            self.on_update_widgets
        )

    def _update_action_env_destroy_state(self):
        env_destroy_activated = self._widget.model.run_engine.env_destroy_activated
        self.action_activate_env_destroy.setChecked(env_destroy_activated)

    def _activate_env_destroy_triggered(self):
        env_destroy_activated = self._widget.model.run_engine.env_destroy_activated
        self._widget.model.run_engine.activate_env_destroy(not env_destroy_activated)

    def _save_history_as_txt_triggered(self):
        self._save_history_to_file("txt")

    def _save_history_as_json_triggered(self):
        self._save_history_to_file("json")

    def _save_history_as_yaml_triggered(self):
        self._save_history_to_file("yaml")

    def _save_history_to_file(self, file_format):
        try:
            fln_pattern = f"{file_format.upper()} (*.{file_format.lower()});; All (*)"
            file_path_init = os.path.join(
                self._work_dir, "plan_history." + file_format.lower()
            )
            file_path_tuple = QFileDialog.getSaveFileName(
                self._widget, "Save Plan History to File", file_path_init, fln_pattern
            )
            file_path = file_path_tuple[0]
            if file_path:
                self._work_dir = os.path.dirname(file_path)
                self._widget.model.run_engine.save_plan_history_to_file(
                    file_path=file_path, file_format=file_format
                )
                print(f"Plan history was successfully saved to file {file_path!r}")
        except Exception as ex:
            print(f"Failed to save data to file: {ex}")

    def _show_connection_info(self):
        """Show the queueserver / stream addresses and user identity."""
        control = (
            SETTINGS.zmq_re_manager_control_addr or "tcp://localhost:60615 (default)"
        )
        info = SETTINGS.zmq_re_manager_info_addr or "tcp://localhost:60625 (default)"
        connected = self.plots._connected
        lines = [
            f"User / group:   {SETTINGS.user_name} / {SETTINGS.user_group}",
            "",
            f"ZMQ control:    {control}",
            f"ZMQ info:       {info}",
            "",
            f"Doc stream:     {SETTINGS.zmq_proxy_info_addr} "
            f"({'connected' if connected else 'disconnected'})",
            f"Plans dir:      {SETTINGS.plans_dir}",
        ]
        QMessageBox.information(
            self._window._qt_window, "Connection Info", "\n".join(lines)
        )

    def shutdown_background(self):
        """Stop the plot stream and console-monitor worker (idempotent)."""
        try:
            self.plots.stop()
        except Exception as ex:
            print(f"Error stopping plot stream: {ex}")
        try:
            self._widget.model.run_engine.stop_console_output_monitoring()
        except Exception as ex:
            print(f"Error stopping console monitor: {ex}")

    def on_update_widgets(self, event):
        """React to a RunEngine status change (refresh menu state)."""
        self._update_action_env_destroy_state()

    @property
    def plots(self):
        """The live-plot panel in the Live View tab."""
        return self._widget._tab_liveview._plots

    @property
    def window(self):
        """The Qt Window wrapping the viewer widget."""
        return self._window

    def show(self):
        """Show and raise the window."""
        self._window.show()

    def close(self):
        """Close the window."""
        self._window.close()
