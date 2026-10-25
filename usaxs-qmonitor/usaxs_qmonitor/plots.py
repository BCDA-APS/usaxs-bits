"""
Live tune/alignment plots for the Live View tab (Phase 3).

Documents flow from the headless RE Worker to this GUI over the network:

    RE Worker: RE.subscribe(Publisher("localhost:5567"))
        -> bluesky-0MQ-proxy 5567 5568
        -> BatchedRemoteDispatcher("localhost:5568")   (here)
        -> one RunRouter, filtering on the 'start' document
        -> RunCollector                                (one per plotted run)
        -> LivePlot                                    (one per tune type)

Each incoming run is routed to the ``LivePlot``s whose ``plan_names`` contains
the run's start-doc ``plan_name`` (see ``settings.plot_config``).  ``max_runs``
keeps the last N scans overlaid; "Clear plots" drops them all.

Plots are grouped into tabs by beamline sub-system (``PLOT_GROUPS``) with every
plot in a tab shown side by side, so users can compare related tunes at a
glance instead of clicking through one tab per plot.

Performance note
----------------
``RE.subscribe(Publisher(...))`` publishes **every** document of **every** plan
— step scans, fly scans, SAXS/WAXS exposures, and the baseline stream with its
several hundred signals — not just the five tune plans drawn here.  Everything
below happens on the Qt main thread, so the panel is built around spending as
little of it as possible:

- There is **one** subscription and one ``RunRouter``.  Earlier code subscribed
  ``stream_documents_into_runs`` once per plot model, so five independent
  ``DocumentCache``/``BlueskyRun`` objects were built for every run on the
  beamline.
- The ``plan_name`` filter is applied in the **factory**, i.e. on the 'start'
  document.  A run nobody plots costs one dict lookup and nothing else.
- Plotted runs accumulate their points directly from the event documents (see
  ``live_lines``), instead of re-deriving them from an xarray Dataset of all 84
  columns on every point.
- Repainting is driven by a timer here, not by document arrival, so a burst of
  documents costs one repaint rather than one per point.
"""

import event_model
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QHBoxLayout
from qtpy.QtWidgets import QLabel
from qtpy.QtWidgets import QPushButton
from qtpy.QtWidgets import QTabWidget
from qtpy.QtWidgets import QVBoxLayout
from qtpy.QtWidgets import QWidget

from .live_lines import DEFAULT_FONT_SIZE
from .live_lines import REDRAW_INTERVAL_MS
from .live_lines import LivePlot
from .live_lines import RunCollector
from .live_lines import run_label
from .zmq_stream import BatchedRemoteDispatcher

# Tab title -> plot_config titles shown side by side in that tab, in this order.
PLOT_GROUPS = [
    ("Optics", ["tune_mr", "tune_ar", "tune_a2rp"]),
    ("Diode", ["tune_dx", "tune_dy"]),
]

# Enough width for three plots side by side on a normal screen.
_CANVAS_MIN_WIDTH = 380

# Cap on the remembered run uids used to reject duplicate 'start' deliveries.
# Only needs to cover runs that are open at the same time; bounded so a GUI
# left running for weeks does not accumulate uids.
_SEEN_UIDS_MAX = 512


class UsaxsPlots(QWidget):
    """Live-plot panel: tabbed figure groups fed by a 0MQ document stream."""

    def __init__(
        self,
        plot_config,
        zmq_proxy_info_addr,
        font_size=DEFAULT_FONT_SIZE,
        *args,
        **kwargs,
    ):
        """Build the LivePlots from ``plot_config`` and wire the dispatcher.

        Parameters
        ----------
        plot_config : list of dict
            Each dict has ``title``, ``x`` (field), ``ys`` (list of fields),
            ``plan_names`` (set/iterable), and optional ``max_runs``.
        zmq_proxy_info_addr : str
            Address of the 0MQ proxy PUB socket, e.g. ``"localhost:5568"``.
        font_size : int
            Base text size on the figures (see ``live_lines``).
        """
        super().__init__(*args, **kwargs)

        self._addr = zmq_proxy_info_addr

        # plan_name -> [LivePlot, ...]. A plan name absent from this map is
        # dropped on its 'start' document and costs nothing thereafter.
        self._plots_by_plan_name = {}
        plots_by_title = {}
        for cfg in plot_config:
            ys = list(cfg["ys"])
            if len(ys) != 1:
                # One y per plot is all the tune configs use, and all a single
                # Line2D per run can draw. Extra entries would be dropped
                # silently, so say so instead.
                raise ValueError(
                    f"plot_config {cfg['title']!r}: expected exactly one y "
                    f"field, got {ys!r}"
                )
            plot = LivePlot(
                title=cfg["title"],
                x_field=cfg["x"],
                y_field=ys[0],
                max_runs=cfg.get("max_runs", 5),
                font_size=font_size,
            )
            plot.setMinimumWidth(_CANVAS_MIN_WIDTH)
            plots_by_title[cfg["title"]] = plot
            for plan_name in cfg.get("plan_names") or ():
                self._plots_by_plan_name.setdefault(plan_name, []).append(plot)
        self._plots = list(plots_by_title.values())

        self._qt_figures = QTabWidget()
        for tab_title, plot_titles in PLOT_GROUPS:
            page = QWidget()
            page_hbox = QHBoxLayout()
            page_hbox.setContentsMargins(0, 0, 0, 0)
            for plot_title in plot_titles:
                page_hbox.addWidget(plots_by_title[plot_title])
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

        # Repainting is driven from here rather than from document arrival, so
        # a burst of documents costs one repaint instead of one per point. The
        # timer only runs while the stream is connected: nothing can become
        # dirty otherwise, and a disconnected panel should cost nothing.
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setInterval(REDRAW_INTERVAL_MS)
        self._redraw_timer.timeout.connect(self._redraw_tick)

    # --- Document routing ---
    def _factory(self, name, doc):
        """RunRouter factory: collect points only for runs we actually plot."""
        plots = self._plots_by_plan_name.get(doc.get("plan_name"))
        if not plots:
            return [], []

        uid = doc.get("uid")
        # event_model.RunRouter >= 1.14 can deliver the same run's 'start' to a
        # factory twice; starting a run twice would orphan the first trace.
        if uid is not None:
            if uid in self._seen_uids:
                return [], []
            self._seen_uids.append(uid)
            del self._seen_uids[:-_SEEN_UIDS_MAX]

        return [RunCollector(uid, run_label(doc), plots)], []

    # --- Drawing ---
    def _redraw_tick(self):
        """Repaint any plot with new data that is currently on screen."""
        warning = ""
        for plot in self._plots:
            plot.redraw_if_needed()
            warning = warning or plot.last_warning
        if warning and self._connected:
            self._status_lbl.setText(warning)

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
        self._redraw_timer.start()
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
        self._redraw_timer.stop()
        self._connected = False
        self._auto_connected = False

    def disconnect_stream(self):
        """Stop receiving documents. A fresh dispatcher is made on reconnect."""
        self._stop_dispatcher()
        # Flush whatever arrived since the last tick so the plots are not left
        # one repaint behind.
        for plot in self._plots:
            plot.redraw_if_needed()
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
        for plot in self._plots:
            plot.clear()
        if self._connected:
            self._status_lbl.setText(f"stream: connected ({self._addr})")

    def stop(self):
        """Release background workers (call on application shutdown).

        Only stops the dispatcher and the repaint timer; does not touch Qt
        widgets, which may already be deleted during application teardown.
        """
        self._redraw_timer.stop()
        self._stop_dispatcher()
