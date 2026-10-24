"""
Batched 0MQ document dispatcher.

``bluesky_widgets.qt.zmq_dispatcher.RemoteDispatcher`` yields **once per
document** from its worker thread, and every yield crosses into the Qt main
thread as a queued signal.  Three consequences, all of which showed up as GUI
lag at the beamline:

- **No back-pressure.**  Qt's posted-event queue is unbounded, so when documents
  arrive faster than the main thread can process them the queue grows without
  limit.  Qt drains posted events ahead of window-system input, so mouse clicks
  and key presses are serviced late — the GUI appears to freeze and then replays
  the user's actions minutes later.
- **A main-thread wake-up every 10 ms even when nothing is happening**, because
  the idle path (``time.sleep(LOADING_LATENCY); yield``) also yields.
- **The receive thread is never stopped.**  ``RemoteDispatcher.stop()`` only
  sets ``closed = True``, which prevents the *next* worker from being scheduled;
  the generator already running loops forever, and its socket and context are
  never released.  Every disconnect/reconnect cycle leaked a thread and a
  socket.

``BatchedRemoteDispatcher`` keeps the upstream wire format and deserialization
(still done off the main thread) and changes only the delivery policy:

- messages are drained into a batch of up to ``max_batch`` and handed over in a
  single queued signal;
- the idle path sleeps without yielding, so a quiet beamline costs nothing;
- the worker blocks while more than ``max_in_flight`` batches are awaiting
  processing, which pushes the backlog into the 0MQ receive buffer (bounded,
  drops oldest) instead of into Qt's event queue;
- the loop exits on ``stop()`` and closes the socket and context on its way out.
"""

import pickle
import time
from threading import Lock

import zmq
from bluesky.run_engine import Dispatcher
from bluesky.run_engine import DocumentNames
from bluesky_widgets.qt.threading import create_worker
from qtpy.QtCore import QObject
from qtpy.QtCore import QTimer

# How long the worker sleeps when the socket has nothing for it.  Larger than
# upstream's 10 ms because an empty poll no longer wakes the main thread, so
# this only sets the latency of the first document of a scan.
IDLE_SLEEP = 0.05  # sec

# Upper bound on documents handed to the main thread in one signal.
MAX_BATCH = 200

# Batches allowed to be in flight (emitted but not yet processed) before the
# worker stops reading the socket.  This is the back-pressure limit.
MAX_IN_FLIGHT = 4

# How long the worker waits before re-checking the in-flight count.
BACKPRESSURE_SLEEP = 0.02  # sec


class BatchedRemoteDispatcher(QObject):
    """Dispatch 0MQ documents to Qt in batches, with back-pressure.

    Parameters
    ----------
    address : str | tuple
        0MQ proxy PUB address, ``"localhost:5568"`` or ``("localhost", 5568)``.
    prefix : bytes, optional
        Publisher prefix filter; empty means accept everything.
    deserializer : callable, optional
        Defaults to ``pickle.loads``, matching ``bluesky.callbacks.zmq``.
    """

    def __init__(
        self,
        address,
        *,
        prefix=b"",
        deserializer=pickle.loads,
        max_batch=MAX_BATCH,
        max_in_flight=MAX_IN_FLIGHT,
        parent=None,
    ):
        """Open the SUB socket and prepare the dispatcher (does not start it)."""
        super().__init__(parent)
        if isinstance(prefix, str):
            raise ValueError("prefix must be bytes, not string")
        if b" " in prefix:
            raise ValueError(f"prefix {prefix!r} may not contain b' '")
        self._prefix = prefix
        if isinstance(address, str):
            address = address.split(":", maxsplit=1)
        self.address = (address[0], int(address[1]))
        self._deserializer = deserializer
        self._max_batch = max_batch
        self._max_in_flight = max_in_flight

        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect("tcp://%s:%d" % self.address)
        self._socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._dispatcher = Dispatcher()
        self.subscribe = self._dispatcher.subscribe

        self.closed = False
        self._waiting_for_start = True
        self._worker = None

        # Back-pressure bookkeeping, written from both threads.
        self._lock = Lock()
        self._in_flight = 0

        # Documents dropped by 0MQ (or undeliverable) since the last connect.
        # Surfaced by the caller; not fatal, but it means a plot may have gaps.
        self.n_errors = 0

    # --- Worker side (background thread) ---
    def _recv_batch(self):
        """Drain up to ``max_batch`` messages without blocking. May return []."""
        batch = []
        while len(batch) < self._max_batch:
            try:
                message = self._socket.recv(zmq.NOBLOCK)
            except zmq.ZMQError:
                break
            if not message:
                continue
            prefix, name, doc = message.split(b" ", 2)
            if self._prefix and prefix != self._prefix:
                continue
            name = name.decode()
            if self._waiting_for_start:
                # Subscribed mid-run: documents whose 'start' we never saw
                # cannot be assembled into a run, so skip to the next 'start'.
                if name != "start":
                    continue
                self._waiting_for_start = False
            batch.append((name, self._deserializer(doc)))
        return batch

    def _receive_data(self):
        """Generator worker: yield lists of ``(name, doc)`` until stopped."""
        try:
            while not self.closed:
                with self._lock:
                    saturated = self._in_flight >= self._max_in_flight
                if saturated:
                    # Main thread is behind. Stop reading so the backlog stays
                    # in the 0MQ buffer rather than in Qt's event queue.
                    time.sleep(BACKPRESSURE_SLEEP)
                    continue

                batch = self._recv_batch()
                if not batch:
                    # Nothing to do: sleep *without* yielding, so an idle
                    # beamline does not wake the main thread at all.
                    time.sleep(IDLE_SLEEP)
                    continue

                with self._lock:
                    self._in_flight += 1
                yield batch
        finally:
            self._close_socket()

    def _close_socket(self):
        """Release the socket and context (called from the worker thread)."""
        try:
            self._socket.close(linger=0)
        except Exception:
            pass
        try:
            self._context.term()
        except Exception:
            pass

    # --- Main thread ---
    def start(self):
        """Start the receive worker."""
        if self.closed:
            raise RuntimeError(
                f"{self!r} has already been stopped. Create a fresh instance."
            )
        self._work_loop()

    def _work_loop(self):
        if self.closed:
            return
        worker = create_worker(self._receive_data)
        self._worker = worker
        worker.yielded.connect(self._process_result)
        # The generator only returns when `closed` is set, so this reschedule
        # is a safety net for an unexpected exit, not the normal path.
        worker.finished.connect(
            lambda: QTimer.singleShot(int(IDLE_SLEEP * 1000), self._work_loop)
        )
        worker.start()

    def _process_result(self, batch):
        """Hand a batch of documents to the subscribed callbacks (main thread)."""
        try:
            if not batch:
                return
            for name, doc in batch:
                try:
                    self._dispatcher.process(DocumentNames[name], doc)
                except Exception:
                    # A dropped document (0MQ discards oldest when its buffer
                    # overflows) leaves a descriptor or event unroutable. Count
                    # it and keep going -- one gap in a plot must not take the
                    # stream down.
                    self.n_errors += 1
        finally:
            with self._lock:
                self._in_flight = max(0, self._in_flight - 1)

    def stop(self):
        """Stop the worker; its socket and context are closed as it unwinds.

        The generator exits on its own within ``IDLE_SLEEP`` once ``closed`` is
        set, which runs its ``finally`` and releases the socket.  ``worker.quit()``
        is deliberately *not* used: ``GeneratorWorker.work()`` breaks out of its
        loop on abort without closing the generator, so the cleanup would be
        deferred to garbage collection.
        """
        self.closed = True
        self._worker = None
