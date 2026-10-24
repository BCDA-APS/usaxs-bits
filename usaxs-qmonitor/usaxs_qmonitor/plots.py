"""
Live tune/alignment plots for the Live View tab (Phase 3).

Documents flow from the headless RE Worker to this GUI over the network:

    RE Worker: RE.subscribe(Publisher("localhost:5567"))
        -> bluesky-0MQ-proxy 5567 5568
        -> BatchedRemoteDispatcher("localhost:5568")   (here)
        -> one RunRouter, filtering on the 'start' document
        -> Lines(x, ys, max_runs=N)                    (one model per tune type)
        -> QtFigure, grouped into tabs below

Each incoming run is routed to the ``Lines`` models whose ``plan_names``
contains the run's start-doc ``plan_name`` (see ``settings.plot_config``).
``max_runs`` keeps the last N scans overlaid; "Clear plots" drops them all.

Plots are grouped into tabs by beamline sub-system (``PLOT_GROUPS``) with every
plot in a tab shown side by side, so users can compare related tunes at a
glance instead of clicking through one tab per plot (``QtFigures``' default).

Performance note
----------------
``RE.subscribe(Publisher(...))`` publishes **every** document of **every** plan
— step scans, fly scans, SAXS/WAXS exposures, and the baseline stream with its
several hundred signals — not just the five tune plans drawn here.  The GUI
therefore has to be cheap about everything it does not plot:

- There is **one** subscription and one ``RunRouter``.  The previous code
  subscribed ``stream_documents_into_runs`` once per plot model, so five
  independent ``DocumentCache``/``BlueskyRun`` objects were built, in the Qt
  main thread, for every run on the beamline.
- The ``plan_name`` filter is applied in the **factory**, i.e. on the 'start'
  document.  A run nobody plots gets no cache and no further per-document work
  at all.  (It used to be filtered only after the run object had been built.)
"""

import event_model
from bluesky_live.bluesky_run import BlueskyRun
from bluesky_live.bluesky_run import DocumentCache
from bluesky_widgets.models.plot_builders import Lines
from bluesky_widgets.qt.figures import QtFigure
from qtpy.QtWidgets import QHBoxLayout
from qtpy.QtWidgets import QLabel
from qtpy.QtWidgets import QPushButton
from qtpy.QtWidgets import QTabWidget
from qtpy.QtWidgets import QVBoxLayout
from qtpy.QtWidgets import QWidget

from .zmq_stream import BatchedRemoteDispatcher

# Tab title -> plot_config titles shown side by side in that tab, in this order.
PLOT_GROUPS = [
    ("Optics", ["tune_mr", "tune_ar", "tune_a2rp"]),
    ("Diode", ["tune_dx", "tune_dy"]),
]

# QtFigure hardcodes a 640px minimum canvas width; too wide to show three
# plots side by side on a normal screen, so shrink it here.
_CANVAS_MIN_WIDTH = 380

# Cap on the remembered run uids used to reject duplicate 'start' deliveries.
# Only needs to cover runs that are open at the same time; bounded so a GUI
# left running for weeks does not accumulate uids.
_SEEN_UIDS_MAX = 512


class UsaxsPlots(QWidget):
    """Live-plot panel: tabbed QtFigure groups fed by a 0MQ document stream."""

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

        # plan_name -> [Lines, ...]. A plan name absent from this map is
        # dropped on its 'start' document and costs nothing thereafter.
        self._models_by_plan_name = {}
        lines_by_title = {}
        for cfg in plot_config:
            lines = Lines(cfg["x"], list(cfg["ys"]), max_runs=cfg.get("max_runs", 5))
            lines.figure.title = cfg["title"]
            lines_by_title[cfg["title"]] = lines
            for plan_name in cfg.get("plan_names") or ():
                self._models_by_plan_name.setdefault(plan_name, []).append(lines)
        self._models = list(lines_by_title.values())

        self._qt_figures = QTabWidget()
        for tab_title, plot_titles in PLOT_GROUPS:
            page = QWidget()
            page_hbox = QHBoxLayout()
            page_hbox.setContentsMargins(0, 0, 0, 0)
            for plot_title in plot_titles:
                qt_figure = QtFigure(lines_by_title[plot_title].figure)
                qt_figure.figure.canvas.setMinimumWidth(_CANVAS_MIN_WIDTH)
                page_hbox.addWidget(qt_figure)
            page.setLayout(page_hbox)
            self._qt_figures.addTab(page, tab_title)

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

        # The dispatcher is created lazily on first connect so that a bad
        # address does not break window construction.
        self._dispatcher = None
        self._connected = False
        # True when the stream was connected by tab visibility rather than by
        # the user pressing the button. Only an automatic connection is taken
        # down automatically again -- an explicit Connect is left alone.
        self._auto_connected = False
        self._seen_uids = []

    # --- Document routing ---
    def _factory(self, name, doc):
        """RunRouter factory: build a cache only for runs we actually plot."""
        models = self._models_by_plan_name.get(doc.get("plan_name"))
        if not models:
            return [], []

        uid = doc.get("uid")
        # bluesky-widgets' stream_documents_into_runs could deliver the same
        # run twice (event_model.RunRouter >= 1.14 passes the 'start' doc to
        # the factory callback a second time). Adding a run twice later
        # crashes RunManager._cull_runs/_on_run_removed with a KeyError on the
        # duplicate uid. Guard so each run is added at most once.
        if uid is not None:
            if uid in self._seen_uids:
                return [], []
            self._seen_uids.append(uid)
            del self._seen_uids[:-_SEEN_UIDS_MAX]

        dc = DocumentCache()

        def build_and_add_run(event):
            run = BlueskyRun(dc)
            for model in models:
                model.add_run(run)

        dc.events.started.connect(build_and_add_run)
        return [dc], []

    # --- Stream connect / disconnect ---
    def connect_stream(self, *, auto=False):
        """Start receiving documents from the 0MQ proxy.

        ``auto=True`` marks the connection as made on the GUI's behalf (tab
        became visible), so ``auto_disconnect_stream`` may undo it later.
        """
        if self._connected:
            # An explicit connect over an automatic one makes it explicit.
            if not auto:
                self._auto_connected = False
            return
        try:
            self._dispatcher = BatchedRemoteDispatcher(self._addr)
            self._dispatcher.subscribe(event_model.RunRouter([self._factory]))
            self._dispatcher.start()
        except Exception as ex:
            self._status_lbl.setText(f"stream error: {ex}")
            self._dispatcher = None
            self._pb_connect.setChecked(False)
            return
        self._connected = True
        self._auto_connected = auto
        self._pb_connect.setChecked(True)
        self._pb_connect.setText("Disconnect stream")
        self._status_lbl.setText(f"stream: connected ({self._addr})")

    def _stop_dispatcher(self):
        """Stop the document dispatcher only (no UI updates). Safe at shutdown."""
        if self._dispatcher is not None:
            try:
                self._dispatcher.stop()
            except Exception:
                pass
            self._dispatcher = None
        self._connected = False
        self._auto_connected = False

    def disconnect_stream(self):
        """Stop receiving documents. A fresh dispatcher is made on reconnect."""
        self._stop_dispatcher()
        self._pb_connect.setChecked(False)
        self._pb_connect.setText("Connect stream")
        self._status_lbl.setText("stream: disconnected")

    def auto_disconnect_stream(self):
        """Disconnect only if the stream was connected automatically."""
        if self._connected and self._auto_connected:
            self.disconnect_stream()

    def _toggle_connect(self):
        if self._connected:
            self.disconnect_stream()
        else:
            self.connect_stream()

    # --- Clear ---
    def clear(self):
        """Discard all overlaid runs from every plot."""
        for model in self._models:
            for run in list(model._run_manager.runs):
                model.discard_run(run)

    def stop(self):
        """Release background workers (call on application shutdown).

        Only stops the dispatcher; does not touch Qt widgets, which may already
        be deleted during application teardown.
        """
        self._stop_dispatcher()
