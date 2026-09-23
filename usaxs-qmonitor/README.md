# usaxs-qmonitor

Customized bluesky-queueserver monitor GUI for the USAXS / SAXS / WAXS instrument
at APS 12-ID-E. Built by subclassing and composing
[bluesky-widgets](https://github.com/bluesky/bluesky-widgets) — not a fork.

See `../USAXS-GUI-IMPLEMENTATION.md` and `../USAXS-GUI-PLAN.md` for the design.

## Install (development)

```bash
conda activate usaxs_qmon
pip install -e ~/GitHub/bluesky-widgets      # editable local checkout
pip install -e ~/GitHub/bluesky-bits/usaxs_qmonitor
```

## Run

Against the beamline queueserver (default ZMQ ports 60615 / 60625):

```bash
usaxs-qmonitor
```

Against a local demo RE Manager for development (no EPICS needed):

```bash
# terminal 1
start-re-manager --zmq-publish-console ON
# terminal 2
usaxs-qmonitor
```

Override addresses via CLI (`--zmq-control-addr`, `--zmq-info-addr`) or the
`QSERVER_ZMQ_CONTROL_ADDRESS` / `QSERVER_ZMQ_INFO_ADDRESS` environment variables.
