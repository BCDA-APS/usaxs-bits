"""
USAXS queue-monitor layout: two tabs.

Tab 1 "Queue Control" — connection/env/queue/execution controls, USAXS action
bar (New User / New Sample / Load plan file — wired in Phases 1-2), the command
designer (plan editor + queue), running plan, and history.

Tab 2 "Live View" — live tune/alignment plots (Phase 3) over the console
(terminal) view of the running Bluesky session.

Composes reusable Qt widgets from bluesky_widgets; USAXS customization lives in
the arrangement here plus our own action-bar / plots widgets.
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bluesky_widgets.qt.run_engine_client import (
    QtReConsoleMonitor,
    QtReEnvironmentControls,
    QtReExecutionControls,
    QtReManagerConnection,
    QtRePlanEditor,
    QtRePlanHistory,
    QtRePlanQueue,
    QtReQueueControls,
    QtReRunningPlan,
    QtReStatusMonitor,
)

from .functions import QtUsaxsActionBar


class QtRunEngineManager_Control(QWidget):
    """Tab 1: everything for driving the queue."""

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model

        vbox = QVBoxLayout()

        # --- Top control row ---
        hbox = QHBoxLayout()
        hbox.addWidget(QtReManagerConnection(model))
        hbox.addWidget(QtReEnvironmentControls(model))
        hbox.addWidget(QtReQueueControls(model))
        hbox.addWidget(QtReExecutionControls(model))
        hbox.addWidget(QtReStatusMonitor(model))
        hbox.addStretch()
        vbox.addLayout(hbox)

        # --- USAXS action bar (Load plan file [Phase 1]; New User/Sample [Phase 2]) ---
        self._action_bar = QtUsaxsActionBar(model)
        vbox.addWidget(self._action_bar)

        # --- Command designer (left) + running/history (right) ---
        hbox = QHBoxLayout()

        left = QVBoxLayout()
        pe = QtRePlanEditor(model)
        pq = QtRePlanQueue(model)
        # Double-clicking a queued item opens it in the editor.
        pq.registered_item_editors.append(pe.edit_queue_item)
        left.addWidget(pe, stretch=1)
        left.addWidget(pq, stretch=1)
        hbox.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(QtReRunningPlan(model), stretch=1)
        right.addWidget(QtRePlanHistory(model), stretch=2)
        hbox.addLayout(right)

        vbox.addLayout(hbox)
        self.setLayout(vbox)


class QtRunEngineManager_LiveView(QWidget):
    """Tab 2: live plots over the console/terminal view."""

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model

        splitter = QSplitter(Qt.Vertical)

        # Plots area (Phase 3: RemoteDispatcher -> Lines -> QtFigures).
        self._plots_placeholder = QLabel(
            "Live tune/alignment plots appear here (Phase 3).\n"
            "Requires bluesky-0MQ-proxy running and Publisher in the worker startup."
        )
        self._plots_placeholder.setAlignment(Qt.AlignCenter)
        splitter.addWidget(self._plots_placeholder)

        # Console / terminal view of the running Bluesky session.
        self._console_monitor = QtReConsoleMonitor(model)
        splitter.addWidget(self._console_monitor)

        splitter.setSizes([2, 1])

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(splitter)
        self.setLayout(vbox)


class QtViewer(QTabWidget):
    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model

        self.setTabPosition(QTabWidget.West)

        self._tab_control = QtRunEngineManager_Control(model.run_engine)
        self.addTab(self._tab_control, "Queue Control")

        self._tab_liveview = QtRunEngineManager_LiveView(model.run_engine)
        self.addTab(self._tab_liveview, "Live View")
