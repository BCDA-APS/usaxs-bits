"""
Plan History table with the newest run at the top.

``bluesky_widgets.qt.run_engine_client.QtRePlanHistory`` draws history top-to-
bottom in the order the RE Manager reports it (oldest first). Users run the
queue top-to-bottom too, so a finished plan visually "moving up and rolling
off the top" reads backwards; showing newest-first matches how the queue
itself is read.

The RE Manager/model always index history oldest-first
(``model.selected_history_item_pos`` and ``plan_history_items``), so only the
*display row* a given model index is drawn into is flipped, via
``row = n - 1 - index``. Everything else (selection bookkeeping, "Copy to
Queue", double-click-to-rerun) keeps operating on model indices unchanged.

Only the newest ``MAX_DISPLAYED_ITEMS`` runs are drawn. The table is cleared
and fully repopulated on every history change (upstream behaviour, and upstream
carries a standing TODO about it freezing the GUI), with
``ResizeToContents`` measuring every cell — so the cost is linear in the number
of rows and is paid every time a plan finishes. The queue server keeps the full
history regardless; this only bounds what is rendered. Because the newest run
is at row 0, the cap simply drops the *oldest* rows, and the index mapping is
unchanged for every row that is still drawn.
"""

from bluesky_widgets.qt.run_engine_client import QtRePlanHistory
from qtpy.QtCore import Qt
from qtpy.QtCore import Slot
from qtpy.QtWidgets import QAbstractItemView
from qtpy.QtWidgets import QHeaderView
from qtpy.QtWidgets import QTableWidgetItem

# Newest N history entries to draw. At minutes per scan this is days of work;
# the full history is still on the server and in "Save Plan History".
MAX_DISPLAYED_ITEMS = 200


class QtRePlanHistoryReversed(QtRePlanHistory):
    """QtRePlanHistory, newest run on top, showing the newest N runs only."""

    def __init__(self, model, parent=None, max_displayed_items=MAX_DISPLAYED_ITEMS):
        """Build the history table, capped at ``max_displayed_items`` rows."""
        self._max_displayed_items = max_displayed_items
        # Number of rows actually drawn; <= self._n_table_items, which stays
        # the full history length because the index mapping depends on it.
        self._n_rows_shown = 0
        super().__init__(model, parent=parent)

    @staticmethod
    def _row_for_index(index, n):
        """Map a model history index to its display row (row = n - 1 - index)."""
        return n - 1 - index

    @Slot(object, object)
    def slot_plan_history_changed(self, plan_history_items, selected_item_pos):
        """Repopulate the table with the newest history item in row 0."""
        scroll_value = self._table.verticalScrollBar().value()
        scroll_maximum = self._table.verticalScrollBar().maximum()
        self._table_scrolled_to_bottom = scroll_value == scroll_maximum

        self._table.clearContents()
        n = len(plan_history_items)
        n_shown = min(n, self._max_displayed_items)
        self._table.setRowCount(n_shown)

        if n_shown:
            resize_mode = QHeaderView.ResizeToContents
        else:
            resize_mode = QHeaderView.Stretch
        self._table.horizontalHeader().setSectionResizeMode(resize_mode)

        # Rows 0..n_shown-1 are the newest items, i.e. model indices
        # n-n_shown..n-1. Older items are not drawn.
        for index in range(n - n_shown, n):
            item = plan_history_items[index]
            row = self._row_for_index(index, n)
            for nc, col_name in enumerate(self._table_column_labels):
                try:
                    value = self.model.get_item_value_for_label(
                        item=item, label=col_name
                    )
                except KeyError:
                    value = ""
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, nc, table_item)

        # _n_table_items stays the full history length: it is what the row
        # <-> model-index mapping is computed from. _n_rows_shown bounds the
        # rows that actually exist in the table.
        self._n_table_items = n
        self._n_rows_shown = n_shown

        if self._table_scrolled_to_bottom:
            scroll_maximum_new = self._table.verticalScrollBar().maximum()
            self._table.verticalScrollBar().setValue(scroll_maximum_new)

        self.slot_change_selection(selected_item_pos)

        self._update_button_states()

    def on_item_selection_changed(self):
        """Convert the table selection (display rows) to model indices."""
        if self._block_table_selection_processing:
            return

        sel_rows = self._table.selectionModel().selectedRows()
        try:
            if len(sel_rows) >= 1:
                n = self._n_table_items
                selected_item_pos = sorted(
                    self._row_for_index(r.row(), n) for r in sel_rows
                )
                self.model.selected_history_item_pos = selected_item_pos
                self._selected_items_pos = selected_item_pos
            else:
                raise Exception()
        except Exception:
            self.model.selected_history_item_pos = []
            self._selected_items_pos = []

    @Slot(object)
    def slot_change_selection(self, selected_item_pos):
        """Apply a model-index selection (`selected_item_pos`) to the table rows."""
        n = self._n_table_items
        # A selected item may have scrolled out of the displayed window (it is
        # older than the newest _n_rows_shown); such rows do not exist in the
        # table and must not be selected.
        rows = (
            sorted(
                row
                for row in (self._row_for_index(pos, n) for pos in selected_item_pos)
                if 0 <= row < self._n_rows_shown
            )
            if selected_item_pos
            else []
        )

        # Keep horizontal scroll value while the selection is changed (more consistent behavior)
        scroll_value = self._table.horizontalScrollBar().value()

        if not rows:
            self._table.clearSelection()
            self._selected_items_pos = []
        else:
            self._block_table_selection_processing = True
            self._table.clearSelection()
            for row in rows:
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item:
                        item.setSelected(True)
                    else:
                        print(
                            f"Plan History Table: attempting to select non-existing item: row={row} col={col}"
                        )

            if self._table.currentRow() not in rows:
                self._table.setCurrentCell(rows[0], 0)

            # rows[0] is the smallest row number, i.e. the item with the largest
            # (newest) model index among the selection — keep that one in view.
            row_visible = rows[0]
            item_visible = self._table.item(row_visible, 0)
            self._table.scrollToItem(item_visible, QAbstractItemView.EnsureVisible)
            self._block_table_selection_processing = False
            self._selected_items_pos = rows

        self._table.horizontalScrollBar().setValue(scroll_value)

        self.model.selected_history_item_pos = selected_item_pos
        self._update_button_states()
