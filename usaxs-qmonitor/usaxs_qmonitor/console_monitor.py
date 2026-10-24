"""
Console monitor with a smaller text buffer.

``bluesky_widgets.qt.run_engine_client.QtReConsoleMonitor`` redraws by doing
``"\\n".join(self._text_list)`` followed by ``QTextEdit.setText(...)`` every
195 ms for as long as output keeps arriving — a full re-layout of the whole
buffer, on the Qt main thread, several times a second during a scan.  The cost
is proportional to the buffer size, so the buffer size is the knob.

Two defaults are lowered here:

- ``_max_lines`` 1000 -> ``MAX_LINES``.  Nobody reads a thousand lines of
  scrollback in this window; the SPEC/Obsidian records are the real log.
- ``_le_max_lines_max`` 10000 -> ``MAX_LINES_LIMIT``.  This one is not just the
  upper bound of the "Max. Lines" entry: ``_adjust_text_list_size`` uses
  ``_le_max_lines_max + 100`` as the cap whenever autoscroll is switched off,
  so with the stock value a user who unchecks Autoscroll silently gets a
  10100-line buffer and a correspondingly slower GUI.
"""

from bluesky_widgets.qt.run_engine_client import QtReConsoleMonitor

# Default size of the console scrollback, in lines.
MAX_LINES = 200

# Largest value the user may type into "Max. Lines" (and, plus 100, the cap
# applied while autoscroll is off).
MAX_LINES_LIMIT = 1000


class UsaxsConsoleMonitor(QtReConsoleMonitor):
    """QtReConsoleMonitor with a scrollback sized for a responsive GUI."""

    def __init__(self, model, parent=None, max_lines=MAX_LINES):
        """Build the console monitor and shrink its text buffer."""
        super().__init__(model, parent=parent)

        self._le_max_lines_max = MAX_LINES_LIMIT
        self._max_lines = min(max_lines, MAX_LINES_LIMIT)
        self._le_max_lines.setText(f"{self._max_lines}")
        self._le_max_lines.setToolTip(
            "Lines of console scrollback kept in this window. The whole buffer "
            "is re-rendered several times a second while output arrives, so a "
            "large value makes the GUI sluggish."
        )
