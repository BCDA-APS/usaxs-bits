"""Entry point for the USAXS queue-monitor GUI (ZMQ transport)."""

import argparse
import os

from bluesky_widgets.qt import gui_qt

from .settings import SETTINGS
from .viewer import UsaxsViewer


def main(argv=None):
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
        viewer = UsaxsViewer()  # noqa: F841


if __name__ == "__main__":
    main()
