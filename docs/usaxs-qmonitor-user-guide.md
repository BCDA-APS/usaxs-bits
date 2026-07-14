# USAXS Queue Monitor — User Guide

`usaxs-qmonitor` is a customized graphical front-end for the USAXS / SAXS / WAXS
queueserver at APS 12-ID-E. It lets you drive the Bluesky queue, run the common
setup functions, load agent-generated plan files, and watch live tune/alignment
plots — all without the IPython console.

It is a thin package (in this repo under `usaxs-qmonitor/`) built **on top of**
[bluesky-widgets](https://github.com/bluesky/bluesky-widgets); it is not a fork.

---

## 1. How the pieces fit together

There are three separate processes at runtime:

```
  usaxs-qmonitor GUI  ──ZMQ control (60615)──►  RE Manager  ──►  RE Worker
   (this app)         ◄─ZMQ console/status ───  (queueserver)    (your devices,
        ▲              (60625)                                     plans, newUser…)
        │                                                              │
        └────────── live documents ◄── bluesky-0MQ-proxy ◄── Publisher┘
                     (proxy out 5568)      (5567 → 5568)
```

- **RE Manager + RE Worker** = the queueserver. The Worker holds the live
  namespace (devices, plans, `newUser()`, `tune_ar()`, …). It is **headless** —
  that is why matplotlib windows do not appear when running under queueserver.
- **The GUI** talks to the Manager over ZMQ for control (start/stop/queue) and
  console output, and it receives a **copy of the document stream** over a
  separate 0MQ channel so it can redraw the tune plots itself.

You only get live plots if the beamline side has the document stream enabled
(see the [testing checklist](usaxs-qmonitor-testing-checklist.md) and
`../USAXS-GUI-IMPLEMENTATION.md`).

---

## 2. Installing

The GUI depends on `bluesky-widgets`, `bluesky-queueserver-api`, `qtpy`, `PyQt5`,
and `matplotlib`. On the beamline run computer these are already in the
`bits_usaxs` environment; you only need to install this package.

```bash
conda activate bits_usaxs
pip install -e <repo>/usaxs-qmonitor
```

For a laptop/dev machine without the beamline environment, see the
[testing checklist](usaxs-qmonitor-testing-checklist.md) §A for a from-scratch
conda environment and a local demo queueserver.

---

## 3. Launching

```bash
# from the repo
./scripts/start-usaxs-qmonitor.sh
# or directly
usaxs-qmonitor
```

By default it connects to the RE Manager on the local host using the standard
queueserver ports (control `60615`, info `60625`) — the same ones in
`src/usaxs/qserver/qs-config.yml`. To point elsewhere:

```bash
usaxs-qmonitor --zmq-control-addr tcp://otherhost:60615 \
               --zmq-info-addr    tcp://otherhost:60625
# or via environment variables:
export QSERVER_ZMQ_CONTROL_ADDRESS=tcp://otherhost:60615
export QSERVER_ZMQ_INFO_ADDRESS=tcp://otherhost:60625
```

**Help → Connection Info…** shows the exact addresses, your user identity, and
whether the live-plot stream is connected.

### User identity

The GUI connects as user **`usaxs`**, group **`primary`** by default (shown in
the window title bar). The `primary` group already permits the `newUser` and
`newSample` functions in `user_group_permissions.yaml`. To change the defaults,
edit `usaxs-qmonitor/usaxs_qmonitor/settings.py` (`user_name` / `user_group`).

---

## 4. The two tabs

### Tab 1 — Queue Control

Everything for driving the queue, top to bottom:

1. **Control row** — connect/disconnect to the Manager, open/close/destroy the
   RE **environment**, queue controls (start/stop/pause), execution controls, and
   the live status monitor.
2. **USAXS action bar** — `New User…`, `New Sample…`, `Load plan file…`
   (see §5). A status line to the right shows the result of the last action.
3. **Command designer** (left) — the plan **editor** (pick a plan, fill in
   parameters, add to queue) above the **queue** table. Double-click a queued
   item to re-open it in the editor.
4. **Running plan + history** (right) — the currently running plan and the
   history of completed/failed plans.

**Typical flow:** Connect → *Open environment* → build a plan in the editor and
*Add to queue* (or queue several) → *Start* the queue. Watch progress in the
running-plan panel and the Live View terminal.

### Tab 2 — Live View

- **Top: live plots.** One plot per tune type (`tune_ar`, `tune_mr`, `tune_a2rp`,
  `tune_dx`, `tune_dy`), each keeping the **last 5 scans overlaid** (oldest drops
  off automatically). Plots update live as a scan runs.
  - **Connect stream / Disconnect stream** — toggle the live document feed. It
    auto-connects when the window opens.
  - **Clear plots** — remove all overlaid scans from every plot (use this after
    a geometry change so old curves don't mislead you).
- **Bottom: terminal.** The console output of the running Bluesky session
  (the same text you'd see in the IPython console), streamed from the Manager.

---

## 5. The USAXS actions

### New User…
Opens a dialog for user name (required), sample (default `data`), start scan ID,
and a "skip BSS" checkbox. Runs `newUser(...)` **immediately** in the worker
(not queued) and shows the resulting data directory in the status line.

> A name is always required — the underlying `newUser()` prompts on the console
> when called with no name, which would hang the headless worker. The dialog
> prevents that.

### New Sample…
Opens a dialog for the sample name (required) and runs `newSample(...)`
immediately. `newUser` must have been run first this session, or you'll see a
"run newUser() first" error in a dialog.

### Load plan file…
Uploads a Python file into the **running** worker (the equivalent of
`qserver script upload`). Use it to load an agent-generated or hand-written plan
file without restarting the queueserver:

1. Click **Load plan file…**; the dialog opens in `src/usaxs/user/` by default
   (configurable in `settings.py`).
2. Pick the `.py` file. On success the status shows `Loaded <file> ✓` and the new
   plans appear in the command designer's plan list.
3. If the file has an error, its **traceback is shown in a dialog** and nothing
   is added.

> Uploads change the live namespace for this session only. Keep the worker
> startup scripts authoritative; treat uploads as scratch. By convention, upload
> files that **define plans**, not devices.

### Queue vs. do-it-now
`New User` / `New Sample` run **immediately**. If instead you want these actions
**in the queue** (e.g. change sample between two scans), the queueable plan
wrappers `new_user_plan` and `new_sample_plan` are available in the command
designer's plan list.

---

## 6. Environment persistence (important)

`newUser()` / `newSample()` set state inside the **worker** namespace and in
files on disk. Worker-namespace state survives across plans but is **lost when
you Destroy/Close the environment**. After re-opening the environment you may
need to re-run `newUser` (the on-disk `.user_info.json` lets `newSample` and a
bare `newUser()` recover the previous session's values).

The **plots** likewise only show scans received *after* the GUI connected the
stream. Restarting the GUI (or reconnecting the stream) will not back-fill
historical scans; it shows subsequent ones.

---

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| GUI opens but everything is greyed out | Not connected to the Manager. Check **Connection Info**, the ports, and that the queueserver is running. |
| New User / New Sample / Load-plan pops **"Environment not open"** | The environment isn't open yet — at the beamline, opening it (loading `usaxs.startup`) can take a while. Wait until the status shows **idle**, then retry. The GUI now guards these actions and warns instead of sending a doomed request. |
| Console/terminal tab is blank | The Manager must publish console output (`zmq_publish_console: true`, `--zmq-info-addr` set). Already set in `qs-config.yml`. |
| A tune runs but **no curve** appears | Most likely the plot **field names** don't match the real document. See the [testing checklist](usaxs-qmonitor-testing-checklist.md) §D and fix `settings.py plot_config`. Wrong names draw nothing (no error). |
| Plots never update at all | The document stream isn't reaching the GUI: is `DOC_STREAM.ENABLE` true in `iconfig.yml`, and is `bluesky-0MQ-proxy` running next to the Manager? Check **Connection Info** shows "connected". |
| First scan right after connecting is missing | Known ZMQ "slow joiner": the very first run in the ~1 s after connecting can be dropped. Connect at startup and it won't affect real scans. |
| `New Sample` errors with "run newUser() first" | Run **New User** first this session. |
| Uploaded plan file "Load failed" | Read the traceback dialog — it's the actual error from the worker. Fix the file and re-upload. |
| Terminal doesn't return after closing the GUI | Fixed — the app now force-exits on close. If you run an older build and it hangs, it's only lingering background threads (nothing important); the queueserver is unaffected. Close the terminal or `kill` the process. |

---

## 8. Where things live

| Thing | Path |
|---|---|
| GUI package | `usaxs-qmonitor/usaxs_qmonitor/` |
| GUI settings (addresses, identity, plot config) | `usaxs-qmonitor/usaxs_qmonitor/settings.py` |
| Launcher | `scripts/start-usaxs-qmonitor.sh` |
| Queueserver config | `src/usaxs/qserver/qs-config.yml` |
| Permissions (plans + functions) | `src/usaxs/qserver/user_group_permissions.yaml` |
| Document-stream flag | `src/usaxs/configs/iconfig.yml` → `DOC_STREAM` |
| Publisher wiring | `src/usaxs/startup.py` (after `init_RE`) |
| Proxy start/stop | `scripts/usaxs_qs_host.sh` |
| Queueable user-action plans | `src/usaxs/plans/user_actions_plans.py` |
