"""
Live tune/alignment plots for the Live View tab (Phase 3).

Documents flow from the headless RE Worker to this GUI over the network:

    RE Worker: RE.subscribe(Publisher("localhost:5567"))
        -> bluesky-0MQ-proxy 5567 5568
        -> RemoteDispatcher("localhost:5568")   (here)
        -> stream_documents_into_runs(...)       (flat docs -> BlueskyRuns)
        -> Lines(x, ys, max_runs=N)              (one model per tune type)
        -> QtFigures                             (embedded below)

Each incoming run is routed to the ``Lines`` model whose ``plan_names`` contains
the run's start-doc ``plan_name`` (see ``settings.plot_config``). ``max_runs``
keeps the last N scans overlaid; "Clear plots" drops them all.
"""

from bluesky_widgets.models.plot_builders import Lines
from bluesky_widgets.models.plot_specs import FigureList
from bluesky_widgets.qt.figures import QtFigures
from bluesky_widgets.qt.zmq_dispatcher import RemoteDispatcher
from bluesky_widgets.utils.streaming import stream_documents_into_runs
from qtpy.QtWidgets import QHBoxLayout
from qtpy.QtWidgets import QLabel
from qtpy.QtWidgets import QPushButton
from qtpy.QtWidgets import QVBoxLayout
from qtpy.QtWidgets import QWidget


class UsaxsPlots(QWidget):
    """Live-plot panel: a QtFigures view fed by a 0MQ document stream."""

    def __init__(self, plot_config, zmq_proxy_info_addr, *args, **kwargs):
        """Build Lines models from ``plot_config`` and wire the dispatcher.

        Parameters
        ----------
        plot_config : list of dict
            Each dict has ``title``, ``x`` (field), ``ys`` (list of fields),
            ``plan_names`` (set/iterable), and optional ``max_runs``.
        zmq_proxy_info_addr : str
            Address of the 0MQ proxy PUB socket, e.g. ``"localhost:5568"``.
        """
        super().__init__(*args, **kwargs)

        self._addr = zmq_proxy_info_addr
        self._models = []  # list of (Lines, plan_names set)

        figures = []
        for cfg in plot_config:
            lines = Lines(cfg["x"], list(cfg["ys"]), max_runs=cfg.get("max_runs", 5))
            lines.figure.title = cfg["title"]
            self._models.append((lines, set(cfg.get("plan_names") or ())))
            figures.append(lines.figure)

        self._figure_list = FigureList(figures)
        self._qt_figures = QtFigures(self._figure_list)

        # --- Controls row ---
        self._pb_connect = QPushButton("Connect stream")
        self._pb_connect.setCheckable(True)
        self._pb_connect.setToolTip(
            f"Subscribe to live documents from the 0MQ proxy at {self._addr}."
        )
        self._pb_connect.clicked.connect(self._toggle_connect)

        self._pb_clear = QPushButton("Clear plots")
        self._pb_clear.setToolTip("Remove all overlaid scans from every plot.")
        self._pb_clear.clicked.connect(self.clear)

        self._status_lbl = QLabel("stream: disconnected")

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self._pb_connect)
        controls.addWidget(self._pb_clear)
        controls.addWidget(self._status_lbl, stretch=1)
        controls.addStretch()

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addLayout(controls)
        vbox.addWidget(self._qt_figures, stretch=1)
        self.setLayout(vbox)

        # RemoteDispatcher is created lazily on first connect so that a bad
        # address does not break window construction.
        self._dispatcher = None
        self._connected = False

    # --- Document routing ---
    @staticmethod
    def _make_adder(model, plan_names):
        seen_uids = set()

        def add_run(run):
            start = run.metadata.get("start") or {}
            plan_name = start.get("plan_name")
            if plan_names and plan_name not in plan_names:
                return
            uid = start.get("uid")
            # bluesky-widgets' stream_documents_into_runs can deliver the same
            # run twice (event_model.RunRouter >= 1.14 passes the 'start' doc to
            # the factory callback a second time). Adding a run twice later
            # crashes RunManager._cull_runs/_on_run_removed with a KeyError on
            # the duplicate uid. Guard so each run is added at most once.
            if uid is not None and uid in seen_uids:
                return
            seen_uids.add(uid)
            model.add_run(run)

        return add_run

    # --- Stream connect / disconnect ---
    def connect_stream(self):
        """Start receiving documents from the 0MQ proxy."""
        if self._connected:
            return
        try:
            self._dispatcher = RemoteDispatcher(self._addr)
            for model, plan_names in self._models:
                self._dispatcher.subscribe(
                    stream_documents_into_runs(self._make_adder(model, plan_names))
                )
            self._dispatcher.start()
        except Exception as ex:
            self._status_lbl.setText(f"stream error: {ex}")
            self._dispatcher = None
            self._pb_connect.setChecked(False)
            return
        self._connected = True
        self._pb_connect.setChecked(True)
        self._pb_connect.setText("Disconnect stream")
        self._status_lbl.setText(f"stream: connected ({self._addr})")

    def disconnect_stream(self):
        """Stop receiving documents. A fresh dispatcher is made on reconnect."""
        if self._dispatcher is not None:
            try:
                self._dispatcher.stop()
            except Exception:
                pass
            self._dispatcher = None
        self._connected = False
        self._pb_connect.setChecked(False)
        self._pb_connect.setText("Connect stream")
        self._status_lbl.setText("stream: disconnected")

    def _toggle_connect(self):
        if self._connected:
            self.disconnect_stream()
        else:
            self.connect_stream()

    # --- Clear ---
    def clear(self):
        """Discard all overlaid runs from every plot."""
        for model, _ in self._models:
            for run in list(model._run_manager.runs):
                model.discard_run(run)

    def stop(self):
        """Release background workers (call on application shutdown)."""
        self.disconnect_stream()
