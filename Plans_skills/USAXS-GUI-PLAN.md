# USAXS Queue Monitor — Custom GUI Planning Document

Author: planning session with Claude, 2026-07-11
Target: a customized queue-monitor GUI for the USAXS beamline, built on bluesky-widgets + bluesky-queueserver.

---

## 1. How the pieces fit together (what you asked to understand)

There are three separate processes at runtime:

```
┌─────────────────────┐   ZMQ control    ┌──────────────────────┐
│  GUI (your app)     │ ───────────────► │  RE Manager          │
│  bluesky-widgets    │                  │  (start-re-manager)  │
│  Qt widgets         │ ◄─────────────── │                      │
└─────────┬───────────┘   ZMQ console/   └─────────┬────────────┘
          │               status info              │ spawns/controls
          │                                        ▼
          │  ZMQ document stream         ┌──────────────────────┐
          │  (via 0MQ proxy) — NEW,      │  RE Worker           │
          └───── to be added ─────────── │  (runs your startup  │
                                         │  scripts, RE, plans) │
                                         └──────────────────────┘
```

- **RE Manager + RE Worker** = the queueserver (`qserver` CLI talks to the Manager). The Worker holds the IPython-like namespace: your devices, plans, `newUser()`, `tune_ar()`, etc. It is **headless** — this is why matplotlib windows "disappear" under queueserver.
- **GUI**: the queue-monitor app is a thin shell (4 small files in `bluesky_widgets/apps/queue_monitor/`) that assembles reusable widgets:
  - `models/run_engine_client.py` → `RunEngineClient`: the non-GUI *model*. It wraps `bluesky_queueserver_api` (`REManagerAPI_ZMQ` or `_HTTP`) and holds all state (queue, history, status). No Qt code in it.
  - `qt/run_engine_client.py`: the Qt *views* (`QtRePlanQueue`, `QtRePlanEditor`, `QtReStatusMonitor`, `QtReConsoleMonitor`, ...). Each takes the model and subscribes to its events.
  - `apps/queue_monitor/{viewer,widgets,settings,main}.py`: layout + entry point.
- The model↔view split means: **to add a capability you (a) add a method on a `RunEngineClient` subclass that calls the queueserver API, (b) add/modify a Qt widget that calls it.** That is the whole pattern; everything below follows it.

Key fact: `RunEngineClient` already holds `self._client`, a full `bluesky_queueserver_api.REManagerAPI` instance. That API already supports everything you need (`function_execute`, `script_upload`, `permissions_reload`, ...) — the GUI model simply doesn't expose most of it yet.

---

## 2. Repo strategy — "Do I rename this repo?"

**No. Do not fork/rename bluesky-widgets.** Recommended structure:

Create a **new small package** (e.g. `usaxs-qmonitor`, living in or next to `bluesky-bits`) that *depends on* `bluesky-widgets` from PyPI:

```
usaxs-qmonitor/
├── pyproject.toml          # depends on bluesky-widgets, bluesky-queueserver-api, qtpy, PyQt5
└── usaxs_qmonitor/
    ├── main.py             # entry point (copied/adapted from apps/queue_monitor/main.py)
    ├── settings.py         # ZMQ addresses, plan-file directory, USAXS defaults
    ├── viewer.py           # window + menus
    ├── widgets.py          # your layout; imports Qt widgets from bluesky_widgets.qt.run_engine_client
    ├── run_engine_client.py# class UsaxsRunEngineClient(RunEngineClient): adds function_execute, script_upload
    └── plots.py            # live-plot tab (Section 5)
```

Why this and not a fork:

- The queue_monitor app itself is ~450 lines total — trivially copied as a seed. The heavy machinery (the 4300-line model/view files) stays upstream and you keep getting fixes with `pip install -U bluesky-widgets`.
- You customize by **subclassing and composing**, not editing upstream files.
- Only if you must change the *internals* of an upstream widget (e.g., rip columns out of `QtRePlanQueue`) do you vendor that one class into your package — copy the single class, note the upstream version you copied from in a comment, and diff against upstream occasionally.
- Fork only as a last resort (many deep changes). A fork makes you the maintainer of 100% of the code and updates become painful merges.

Pin versions in `pyproject.toml` (`bluesky-widgets==X.Y.Z`, `bluesky-queueserver-api==...`). bluesky-widgets is still beta and its API moves; pinning + deliberate upgrades beats surprise breakage at the beamline.

---

## 3. Feature 1 — Run Python functions (`newUser()`, `newSample()`) from the GUI

**Solvable: yes, two supported routes.** Both require the function to exist in the RE Worker namespace (defined in your startup scripts in bluesky-bits).

### Option A — `function_execute` API (recommended for these)
`bluesky_queueserver_api` has `RM.function_execute(BFunc("newUser", "userName", param=value), run_in_background=True)`.

- Runs the function immediately in the worker (not queued). `run_in_background=True` lets it run even while a plan is executing (only safe for functions that don't move hardware).
- **Permissions**: function names must be allowed in `user_group_permissions.yaml` under the group's `allowed_functions` (regex list), same file that governs allowed plans. This is a one-time config change on the queueserver side.
- GUI side: add to `UsaxsRunEngineClient`:
  ```python
  from bluesky_queueserver_api import BFunc
  def function_execute(self, name, *args, run_in_background=False, **kwargs):
      return self._client.function_execute(
          BFunc(name, *args, **kwargs), run_in_background=run_in_background)
  ```
  Then a simple Qt form: dropdown or dedicated buttons ("New User…", "New Sample…") opening a small dialog for parameters. For a handful of known functions, hand-built dialogs are simpler and friendlier than a generic form.
- Returns a task uid; result retrievable via `RM.task_result(uid)` — show success/failure in a status line.

### Option B — wrap them as plans
Make trivial plan wrappers in your startup code (`def new_user_plan(name, ...): yield from bps.null(); newUser(name, ...)` or a proper generator). They then appear in `plans_allowed` and the **existing** `QtRePlanEditor` gives you parameter entry, validation, and queueing for free.

- Pro: zero new GUI code; functions become queueable (e.g., queue "newSample" between scans).
- Con: they execute only via the queue/RE machinery; clunky for instant metadata-setting actions.

**Recommendation**: Option A for interactive actions (user/sample setup, "do it now" semantics), Option B for anything users might want *in the queue* between scans. They coexist fine.

### Environment persistence caveat
`newUser()` presumably sets globals in the worker namespace. That state lives only inside the worker environment — it survives across plans but is lost on "Destroy/Close environment". Document this for users; consider having `newUser` persist to a file that startup scripts re-read.

---

## 4. Feature 2 — Upload updated plan files (the `qserver script upload` equivalent)

**Solvable: yes, directly supported.** `qserver script upload file.py` maps to `RM.script_upload(script_text)`, and yes — it is effectively `%run` into the live worker namespace: the code executes in the worker and may define or replace plans/functions/devices. By default the allowed plans/devices lists refresh automatically afterwards (`update_lists=True`), so new plans immediately appear in the GUI plan editor.

GUI design:

1. Add to `UsaxsRunEngineClient`:
   ```python
   def script_upload(self, file_path, run_in_background=False):
       with open(file_path) as f:
           script = f.read()
       return self._client.script_upload(script, run_in_background=run_in_background)
   ```
2. Add a **"Load plan file…"** button that opens `QFileDialog` pinned to your agreed plans directory (e.g. `src/usaxs/user/`) — set this directory in `settings.py`. Users pick the agent-generated plan file; one click loads it.
3. After upload completes (it returns a task uid — poll `task_result`), call `self.load_allowed_plans()` (already in the base model) so the GUI refreshes, and surface the task result: if the script raised (syntax error etc.), show the traceback in a message box instead of failing silently.
4. Optional nicety: a small list widget showing `*.py` files in the plans directory sorted by mtime, with a "Load selected" button — easier than a file dialog for users looking for "the newest plan the agent made for me."

Caveats to document:
- Uploading a script mutates the live namespace; a bad script can shadow a real plan. Keep worker startup scripts authoritative; treat uploads as session-scoped.
- Environment must be open; upload of long-running scripts blocks the manager unless `run_in_background=True` (keep it foreground for plan definitions — they're instant).

---

## 5. Feature 3 — Live tune/alignment plots (the challenging one)

**Solvable: yes — but not by embedding the worker's matplotlib figures.** The worker is a separate headless process; its matplotlib objects cannot be re-parented into your GUI. Under IPython, `RE(tune_ar())` plots because the `BestEffortCallback` subscribes to the RunEngine's **document stream** locally. The correct queueserver-era solution is to ship that same document stream over the network to the GUI and rebuild the plots there. bluesky-widgets was designed for exactly this.

### Architecture

```
RE Worker startup script:                     GUI:
RE.subscribe(Publisher("localhost:5567"))     RemoteDispatcher("localhost:5568")
        │                                            │
        ▼                                            ▼
   bluesky-0MQ-proxy 5567 5568  ─────────►  stream_documents_into_runs
   (small daemon, ships docs)                        │
                                                     ▼
                                        models.plot_builders.Lines(x, y, max_runs=5)
                                                     │
                                                     ▼
                                        qt.figures.QtFigures  (embedded in your tab)
```

Concretely:

1. **Beamline side (bluesky-bits change)**: in the queueserver startup scripts add
   ```python
   from bluesky.callbacks.zmq import Publisher
   RE.subscribe(Publisher("localhost:5567"))
   ```
   and run the tiny proxy daemon: `bluesky-0MQ-proxy 5567 5568` (ships with bluesky; run under systemd/supervisor next to the RE Manager).
2. **GUI side**: `bluesky_widgets.qt.zmq_dispatcher.RemoteDispatcher` (already in this repo) receives documents on 5568 in a Qt-friendly background worker.
3. **Plot models**: `bluesky_widgets.models.plot_builders.Lines(x="ar", y=["signal"], max_runs=5)` — note **`max_runs` natively implements your "keep the last ~5 scans overlaid" behavior** (FIFO: oldest line drops off). One `Lines` model per plot type (tune_ar, tune_a2rp, transmission line scan, ...), each rendered by `QtFigure`/`QtFigures` in a "Plots" tab of your app. Streams update live while the scan runs.
4. **Routing scans to the right plot**: filter documents by metadata. Your tune plans should stamp `md={"purpose": "tune", "tuned_motor": "ar"}` (or you filter on `plan_name`). A small dispatcher function inspects each run's start doc and feeds it to the matching `Lines` model. `models.utils.RunManager`/`streaming utilities` in this repo handle the plumbing; see `examples/kafka_figures.py` and `examples/qt_app_integration.py` for working patterns.
5. **Stale-plot cleanup** (your "we kill them when geometry changes"): give the Plots tab a **"Clear plots"** button that empties/recreates the `Lines` models (`figures` list clear, or rebuild the models). Optionally auto-clear when a `newUser`/geometry-change function runs.

### Alternatives considered

- **Kafka** (`qt/kafka_dispatcher.py`): same pattern, Kafka instead of 0MQ proxy. Choose it only if your APS group already runs Kafka for bluesky documents (many APS beamlines do — check with your controls group; if a broker already publishes your documents, you skip step 1 entirely).
- **Polling databroker/tiled** after each scan: simplest, but not live and adds latency; fallback only.
- **Worker saves PNGs to disk, GUI displays files**: crude but very robust; a reasonable stopgap in Phase 1 if the document-stream work slips. A `best_effort`-style callback in the worker writes `tune_ar_latest.png`; GUI shows and auto-refreshes it. No overlaid history without extra work, though.

**Recommendation**: 0MQ proxy + `Lines(max_runs=5)` + `QtFigures`. It reproduces your IPython experience (live line plot, last-N overlay) with components that already exist in this repo. Prerequisite check: confirm your tune plans emit normal documents through `RE` (they do if `RE(tune_ar())` produced BEC plots) and identify the actual signal/motor names to plot — that requires reading `bluesky-bits` (not accessible in this session; do this first in implementation).

---

## 6. Critical decisions to make now

| Decision | Options | Recommendation / consequence |
|---|---|---|
| Transport GUI↔Manager | ZMQ direct vs bluesky-httpserver | **ZMQ** (you chose same-machine/subnet). Note: switching to HTTP later is easy — `RunEngineClient` supports both via one constructor arg — so remote access is not foreclosed. |
| Document streaming | 0MQ proxy vs Kafka vs file-based | **0MQ proxy** unless APS already gives you Kafka. This is the one choice that touches beamline infrastructure (a daemon + startup-script line), so decide early. |
| Functions | `function_execute` vs plan wrappers | Both; per-case (Section 3). Requires editing `user_group_permissions.yaml` — coordinate now. |
| Package layout | New package vs fork | **New package** depending on pinned bluesky-widgets (Section 2). |
| Qt binding | PyQt5 / PySide2/6 via qtpy | Match whatever your beamline conda env already has (repo tests against PyQt5/PySide2). |
| User identity | default "GUI Client" vs real names | Set `user_name`/`user_group` per operator if you ever want per-group permissions; cheap to do now, annoying to retrofit. |

Nothing in the recommended path locks you out later: ZMQ→HTTP is a config change, widgets can be vendored one at a time, and the document-stream tab is additive.

---

## 7. Implementation phases (each independently shippable)

**Phase 0 — Scaffold (½ day)**
Create `usaxs-qmonitor` package; copy the four `apps/queue_monitor` files; rename classes; confirm it runs against your beamline qserver exactly like stock queue-monitor. Acceptance: connect, view queue, run a plan.

**Phase 1 — Script upload button (½–1 day)**
`UsaxsRunEngineClient.script_upload()` + "Load plan file…" button + task-result error display + allowed-plans refresh. Acceptance: load `ptc10_plan2.py` from GUI; new plan appears in plan editor; a deliberately broken file shows its traceback.

**Phase 2 — Function execution (1–2 days)**
`allowed_functions` in `user_group_permissions.yaml`; `function_execute()` on the model; dedicated "New User" / "New Sample" dialogs. Acceptance: `newUser("test")` from GUI has same effect as from IPython.

**Phase 3 — Live plots (3–5 days, the real work)**
Add `Publisher` to startup scripts + deploy `bluesky-0MQ-proxy`; verify docs arrive (`bluesky.callbacks.zmq.RemoteDispatcher` + print, from a terminal). Then Plots tab: `RemoteDispatcher` → routing by start-doc metadata → per-tune `Lines(max_runs=5)` → `QtFigures`; "Clear plots" button. Acceptance: run `tune_ar` from queue; live curve appears; five successive tunes overlay; clear works; GUI restart shows subsequent (not historical) scans.

**Phase 4 — Layout redesign + polish (open-ended)**
Rearrange tabs/widgets for your workflow (pure Qt layout work in `widgets.py`); vendor+trim individual upstream widgets only if needed; settings file for beamline addresses; systemd/desktop launcher.

**Phase 5 — Verification & docs**
User-facing one-pager; test destroy/reopen-environment flows (stale namespace, stale plots); pin final versions.

---

## 8. Risks and gotchas

- **bluesky-widgets is beta**: pin it. Before upgrading, diff `apps/queue_monitor` and the widget classes you rely on.
- **Console monitor** requires `zmq_info_addr` (RE Manager's `--zmq-info-addr`) — keep it configured or the console tab is blank.
- **Permissions file** (`user_group_permissions.yaml`) governs plans *and* functions; a regex typo silently hides plans. Keep it in bluesky-bits under version control.
- **Script upload replaces objects live**; agree on a convention (uploads only define plans, never devices).
- **Plot routing** depends on consistent metadata in tune plans — small edits to bluesky-bits plans may be needed; do this when you add the Publisher.
- **This session could not read `/Users/ilavsky/GitHub/bluesky-bits`** — signal names, tune-plan structure, and startup-script layout in Sections 3–5 are assumptions to verify first.

## 9. References

- Queueserver features (script upload, function execute, permissions): https://blueskyproject.io/bluesky-queueserver/features_and_config.html
- API package: https://blueskyproject.io/bluesky-queueserver-api/
- Document streaming over 0MQ: https://blueskyproject.io/bluesky/callbacks.html (Publisher/RemoteDispatcher)
- In this repo: `bluesky_widgets/models/plot_builders.py` (`Lines`, `max_runs`), `bluesky_widgets/qt/zmq_dispatcher.py`, `bluesky_widgets/qt/figures.py`, `examples/kafka_figures.py`, `examples/qt_app_integration.py`
