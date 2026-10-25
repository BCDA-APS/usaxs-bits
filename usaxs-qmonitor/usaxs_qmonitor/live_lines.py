"""
Lightweight live line plots.

This replaces ``bluesky_widgets.models.plot_builders.Lines`` +
``bluesky_widgets.qt.figures.QtFigure`` for the tune plots.  The upstream pair
is correct but, for this instrument, unusably slow: every new point re-derives
the line's data by calling ``call_or_eval`` -> ``construct_namespace``, which
builds an xarray Dataset over **every column of the stream, twice**.  A USAXS
tune run carries 84 columns (the whole FX4 is read at each point), so that is
656 ms of work per call on a 31-point run, measured — against a point budget of
roughly 800 ms.  The GUI spent about half of each point's time rebuilding data
it already had, with spikes that ate the whole budget.

What this module does instead:

- **Accumulate, never rebuild.**  x and y are appended from the event documents
  as they arrive and handed to ``Line2D.set_data``.  No ``DocumentCache``, no
  ``BlueskyRun``, no xarray.  Cost per point is a list append.
- **Decouple drawing from document arrival.**  Points mark the figure dirty;
  a timer in the owning panel repaints at most every ``REDRAW_INTERVAL_MS``.
  A burst of documents therefore costs one repaint, not one per point.
- **Never draw what is not on screen.**  A hidden figure stays dirty and is
  repainted when it is shown.

Measured on one real ``tune_ar`` (84 columns x 31 points): 12.2 s of main-thread
time with the upstream models, 0.89 s with this one, and most of that remainder
is matplotlib's own rendering (28.7 ms per repaint, now throttled).

Only the fields actually plotted are ever touched, so the width of the event
stream no longer matters.
"""

import logging
import time

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from qtpy.QtWidgets import QVBoxLayout
from qtpy.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Upper bound on repaint rate. Tune points arrive roughly every 0.8 s, so this
# is well inside "live" while capping the cost of any faster stream.
REDRAW_INTERVAL_MS = 200

# matplotlib's tab10, matching the colours Matilda uses for the same plots.
PLOT_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]

# A run still being collected is drawn in black so it stands out from the
# finished scans it is overlaid on (same convention as bluesky-widgets).
LIVE_COLOR = "black"

# Base text size, in points, for everything on a figure.  matplotlib's own
# defaults (10 pt body, 12 pt title) are sized for a full-window figure; three
# of these sit side by side in one tab, so the text crowded the axes and the
# legend ran out of room.  Sizes are applied per figure rather than through
# rcParams, which would leak into any other matplotlib use in the process.
DEFAULT_FONT_SIZE = 8
TITLE_FONT_OFFSET = 2  # title sits above the body size, as matplotlib does
LEGEND_FONT_OFFSET = -1  # legend sits below it; it is the densest text here


class _Trace:
    """One scan's points and the Line2D drawing them."""

    __slots__ = ("x", "y", "artist", "label", "complete")

    def __init__(self, artist, label):
        """Hold the growing x/y buffers for one run."""
        self.x = []
        self.y = []
        self.artist = artist
        self.label = label
        self.complete = False


class LivePlot(QWidget):
    """A single figure overlaying the last ``max_runs`` scans of one tune type.

    Parameters
    ----------
    title : str
        Axes title, e.g. ``"tune_ar"``.
    x_field, y_field : str
        Event-document field names, e.g. ``"a_stage_r"`` and ``"UPD"``.
    max_runs : int
        Scans kept overlaid, oldest dropped first.
    """

    def __init__(
        self,
        title,
        x_field,
        y_field,
        max_runs=5,
        font_size=DEFAULT_FONT_SIZE,
        parent=None,
    ):
        """Build the figure and its canvas."""
        super().__init__(parent)
        self.title = title
        self.x_field = x_field
        self.y_field = y_field
        self.max_runs = max_runs
        self._font_size = font_size

        # Margins are set once rather than with tight_layout/constrained_layout,
        # which re-solve the layout on *every* draw: measured 66.8 ms per
        # repaint with tight_layout against 35.3 ms with fixed margins, for the
        # same five-curve figure. The axis labels here are short and known, so
        # there is nothing for an auto-layout to earn. They are tuned for
        # DEFAULT_FONT_SIZE; a much larger font_size may need more room.
        self._figure = Figure(figsize=(4, 3.2))
        self._figure.subplots_adjust(left=0.16, right=0.97, top=0.91, bottom=0.14)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._axes = self._figure.add_subplot(111)
        self._axes.set_title(title, fontsize=font_size + TITLE_FONT_OFFSET)
        self._axes.set_xlabel(x_field, fontsize=font_size)
        self._axes.set_ylabel(y_field, fontsize=font_size)
        self._axes.tick_params(labelsize=font_size)
        self._axes.grid(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        # uid -> _Trace, insertion-ordered so the oldest is dropped first.
        self._traces = {}
        self._color_index = 0
        self._dirty = False
        self._legend_dirty = False
        # Set when a run produced no usable points, so the panel can say why
        # a plot stayed empty instead of leaving the user guessing.
        self.last_warning = ""

    # --- Data ---
    def start_run(self, uid, label):
        """Begin a new trace, dropping the oldest if ``max_runs`` is exceeded."""
        if uid in self._traces:
            return
        (artist,) = self._axes.plot([], [], color=LIVE_COLOR, label=label)
        self._traces[uid] = _Trace(artist, label)
        while len(self._traces) > self.max_runs:
            old_uid = next(iter(self._traces))
            self._remove(old_uid)
        self._legend_dirty = True
        self._dirty = True

    def add_points(self, uid, xs, ys):
        """Append points to a trace. Unknown uids are ignored."""
        trace = self._traces.get(uid)
        if trace is None:
            return
        trace.x.extend(xs)
        trace.y.extend(ys)
        trace.artist.set_data(np.asarray(trace.x), np.asarray(trace.y))
        self._dirty = True

    def finish_run(self, uid):
        """Mark a trace complete and give it a colour from the cycle."""
        trace = self._traces.get(uid)
        if trace is None:
            return
        trace.complete = True
        trace.artist.set_color(PLOT_COLORS[self._color_index % len(PLOT_COLORS)])
        self._color_index += 1
        if not trace.x:
            self.last_warning = (
                f"{self.title}: run finished with no points "
                f"(no {self.x_field!r}/{self.y_field!r} in its primary stream)"
            )
            logger.warning(self.last_warning)
        self._legend_dirty = True
        self._dirty = True

    def _remove(self, uid):
        trace = self._traces.pop(uid, None)
        if trace is not None:
            try:
                trace.artist.remove()
            except (ValueError, NotImplementedError):
                pass

    def clear(self):
        """Discard every overlaid scan."""
        for uid in list(self._traces):
            self._remove(uid)
        self._color_index = 0
        self.last_warning = ""
        self._legend_dirty = True
        self._dirty = True
        self.redraw_if_needed(force=True)

    # --- Drawing ---
    def redraw_if_needed(self, force=False):
        """Repaint if there is new data and the figure is actually on screen.

        Returns True if a repaint happened.  A hidden figure keeps its dirty
        flag and is repainted by ``showEvent``.
        """
        if not self._dirty:
            return False
        if not force and not self.isVisible():
            return False
        if self._legend_dirty:
            # legend() is relatively expensive and only changes when a trace is
            # added, removed or completed -- not when a point arrives.
            if self._traces:
                # Compact spacing as well as a smaller size: five overlaid
                # scans put five "#1522 09:37:26" rows in the corner of a
                # quarter-width figure.
                self._axes.legend(
                    loc=1,
                    fontsize=self._font_size + LEGEND_FONT_OFFSET,
                    labelspacing=0.3,
                    handlelength=1.2,
                    borderpad=0.3,
                    framealpha=0.8,
                )
            elif self._axes.get_legend() is not None:
                self._axes.get_legend().remove()
            self._legend_dirty = False
        self._axes.relim()
        self._axes.autoscale_view()
        self._canvas.draw_idle()
        self._dirty = False
        return True

    def showEvent(self, event):
        """Repaint a figure that accumulated data while it was hidden."""
        super().showEvent(event)
        self.redraw_if_needed()


class RunCollector:
    """Pull one run's x/y points out of its documents and feed them to plots.

    Instances are returned by the ``RunRouter`` factory in ``plots.py``; the
    router calls them as ``collector(name, doc)``.  Only the ``primary`` stream
    and only the plotted fields are looked at.

    Parameters
    ----------
    uid : str
        Run start uid.
    label : str
        Legend label for this run.
    targets : list of LivePlot
        Plots this run feeds (normally exactly one).
    """

    def __init__(self, uid, label, targets):
        """Register the run with each target plot."""
        self.uid = uid
        self.targets = targets
        self._primary_descriptors = set()
        for plot in targets:
            plot.start_run(uid, label)

    def __call__(self, name, doc):
        """Handle one document for this run."""
        try:
            if name == "descriptor":
                if doc.get("name") == "primary":
                    self._primary_descriptors.add(doc["uid"])
            elif name == "event_page":
                self._event_page(doc)
            elif name == "event":
                self._event_page(
                    {
                        "descriptor": doc["descriptor"],
                        "data": {k: [v] for k, v in doc["data"].items()},
                    }
                )
            elif name == "stop":
                for plot in self.targets:
                    plot.finish_run(self.uid)
        except Exception:
            # A malformed or partial document must never take the stream down.
            logger.exception("Error collecting %r document for %s", name, self.uid)

    def _event_page(self, doc):
        if doc.get("descriptor") not in self._primary_descriptors:
            return
        data = doc.get("data") or {}
        for plot in self.targets:
            xs = data.get(plot.x_field)
            ys = data.get(plot.y_field)
            if xs is None or ys is None:
                continue
            plot.add_points(self.uid, xs, ys)


def run_label(start_doc):
    """Legend label for a run: scan id and start time, as Matilda does it."""
    scan_id = start_doc.get("scan_id")
    tstamp = start_doc.get("time")
    timestr = time.strftime("%H:%M:%S", time.localtime(tstamp)) if tstamp else ""
    return f"#{scan_id} {timestr}".strip() if scan_id is not None else timestr
