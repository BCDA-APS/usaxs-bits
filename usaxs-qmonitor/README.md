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

## Keeping the GUI responsive

This is a *thin* client only if it is careful. The RE Worker publishes **every
document of every plan** to the 0MQ proxy — step scans, fly scans, SAXS/WAXS
exposures, and the baseline stream with its several hundred signals — while the
Live View plots only five tune plans. Everything bluesky-widgets does with
those documents happens on the Qt main thread, so anything done per-document,
or per-row, or per-line is paid for in UI latency.

Four deliberate choices follow from that; the knobs are in `settings.py`.

| Setting | Default | What it bounds |
| --- | --- | --- |
| `plots_autostart` | `False` | Whether the document stream is connected at launch |
| `plots_follow_tab` | `True` | Stream connects when Live View is shown, drops when hidden |
| `console_max_lines` | `200` | Console scrollback (the whole buffer is re-rendered several times a second while output arrives) |
| `history_max_rows` | `200` | History rows drawn (the table is rebuilt from scratch every time a plan finishes) |

Pressing "Connect stream" by hand pins the connection: tab changes will not
drop a stream the user asked for. The server keeps the full plan history
regardless of `history_max_rows`; use "Save Plan History" for the whole record.

Three modules exist only to keep this cost down, and each explains the upstream
behaviour it replaces in its docstring:

- `zmq_stream.py` — `BatchedRemoteDispatcher`. Upstream's `RemoteDispatcher`
  hands documents to the main thread one queued signal at a time with no
  back-pressure, wakes the main thread every 10 ms even when idle, and never
  stops its receive thread. This one batches, idles silently, applies
  back-pressure, and shuts down cleanly.
- `live_lines.py` — `LivePlot` / `RunCollector`, replacing bluesky-widgets'
  `Lines` + `QtFigure`. The upstream models re-derive a line's data from an
  xarray Dataset of *every* column of the stream, twice, on every new point.
  These accumulate x/y straight from the event documents and repaint on a
  timer instead.
- `console_monitor.py` — smaller console scrollback, including the cap that
  upstream raises to 10100 lines as soon as autoscroll is switched off.

`plots.py` uses a single subscription with one `RunRouter`, and filters on the
`start` document, so a run nobody plots costs nothing beyond its 'start'.

Measured on one real `tune_ar` (84 columns × 31 points, the whole FX4 is read
at every point), main-thread time for the whole scan:

| | per point | per scan |
| --- | --- | --- |
| bluesky-widgets `Lines` + `QtFigure` | 393 ms | 12.18 s |
| `LivePlot`, document handling | 0.3 ms | 0.01 s |
| `LivePlot`, matplotlib repaint | 40 ms | 1.23 s |

Against a point budget of roughly 800 ms that is a drop from ~50 % of the main
thread to ~5 %. matplotlib is now the whole remaining cost; if it ever needs to
go lower, the renderer is the thing to replace (pyqtgraph measured 0.2 ms per
repaint against matplotlib's 29–40 ms), but that is a new dependency and buys
nothing until the data path is fixed first — which is what this is.
