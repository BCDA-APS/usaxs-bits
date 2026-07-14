#!/bin/bash
# Launch the USAXS queue-monitor GUI.
#
# Connects to the beamline RE Manager over ZMQ (default ports 60615/60625) and,
# if the 0MQ document proxy is running, draws live tune/alignment plots.
#
# Usage:
#   ./scripts/start-usaxs-qmonitor.sh
#
# Override addresses with environment variables or CLI args, e.g.:
#   QSERVER_ZMQ_CONTROL_ADDRESS=tcp://otherhost:60615 ./scripts/start-usaxs-qmonitor.sh
#   ./scripts/start-usaxs-qmonitor.sh --zmq-control-addr tcp://otherhost:60615

CONDA_ENV="${CONDA_ENV:-bits_usaxs}"

if ! command -v usaxs-qmonitor >/dev/null 2>&1; then
    echo "usaxs-qmonitor not found on PATH."
    echo "Activate the environment and install the package first:"
    echo "    conda activate ${CONDA_ENV}"
    echo "    pip install -e <repo>/usaxs-qmonitor"
    exit 1
fi

exec usaxs-qmonitor "$@"
