"""Entry point for the USAXS queue-monitor GUI (ZMQ transport)."""

import argparse
import os

from bluesky_widgets.qt import gui_qt

from .settings import SETTINGS
from .viewer import UsaxsViewer


def main(argv=None):
    """Parse ZMQ address args/env and launch the USAXS queue-monitor window."""
    parser = argparse.ArgumentParser(description="USAXS Queue Monitor")
    parser.add_argument(
        "--zmq-control-addr",
        default=None,
        help="Address of the RE Manager control socket, e.g. tcp://localhost:60615. "
        "Overrides QSERVER_ZMQ_CONTROL_ADDRESS. Defaults to the queueserver default.",
    )
    parser.add_argument(
        "--zmq-info-addr",
        default=None,
        help="Address of the RE Manager PUB-SUB (console/status) socket, e.g. "
        "tcp://localhost:60625. Overrides QSERVER_ZMQ_INFO_ADDRESS. Defaults to "
        "the queueserver default.",
    )
    args = parser.parse_args(argv)

    zmq_control_addr = args.zmq_control_addr or os.environ.get(
        "QSERVER_ZMQ_CONTROL_ADDRESS", None
    )
    zmq_info_addr = args.zmq_info_addr or os.environ.get(
        "QSERVER_ZMQ_INFO_ADDRESS", None
    )

    print("Initializing: communication with Queue Server directly via 0MQ sockets ...")
    SETTINGS.http_server_uri = None
    SETTINGS.http_server_api_key = None
    SETTINGS.zmq_re_manager_control_addr = zmq_control_addr
    SETTINGS.zmq_re_manager_info_addr = zmq_info_addr

    with gui_qt("USAXS Queue Monitor"):
        from qtpy.QtWidgets import QApplication

        viewer = UsaxsViewer()

        # Clean shutdown. bluesky-widgets' gui_qt wires wait_for_workers_to_quit
        # to aboutToQuit, but the console-monitor worker runs a non-yielding loop
        # that also restarts itself on finish, so that wait blocks forever and
        # the process hangs on close (Ctrl-C does not help). Replace it: stop our
        # background workers, then exit immediately. os._exit is required because
        # the bluesky-queueserver-api client keeps non-daemon comm threads alive
        # that would otherwise stall interpreter shutdown.
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.disconnect()  # drop gui_qt's blocking wait
            except (TypeError, RuntimeError):
                pass
            app.aboutToQuit.connect(viewer.shutdown_background)
            app.aboutToQuit.connect(lambda: os._exit(0))

    # Backstop if the event loop ever returns normally.
    os._exit(0)


if __name__ == "__main__":
    main()
