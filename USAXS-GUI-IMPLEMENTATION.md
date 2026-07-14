# USAXS Queue Monitor GUI — Implementation Plan

Branch: `qmonitor-gui` (off `bait`)
Companion to: `USAXS-GUI-PLAN.md` (the architecture/decision doc).
This document is the concrete, step-by-step build plan reflecting the decisions made 2026-07-14.

---

## 0. Decisions locked in

| Decision | Choice |
|---|---|
| Transport GUI ↔ Manager | **ZMQ only** (control `tcp://localhost:60615`, info `tcp://localhost:60625` — already the beamline defaults in `qs-config.yml`) |
| Document streaming | **0MQ proxy** (`bluesky-0MQ-proxy`), no Kafka |
| Functions | **Both** `function_execute` *and* plan wrappers |
| Package location | **In this repo**, new subdir `usaxs_qmonitor/`, own `pyproject.toml`, `pip install -e .` |
| bluesky-widgets dep | **Editable local checkout** (`pip install -e ~/GitHub/bluesky-widgets`) |
| Qt binding | **PyQt5** (matches beamline env: 5.15.11) |
| User identity | Permissions enabled; default `user_name="usaxs"`, `user_group="primary"` |
| GUI layout | **Two tabs** — Tab 1: queue control + buttons + history + command designer; Tab 2: plots + terminal |
| Test env (this laptop) | conda env `usaxs_qmon`, tested against a **local demo RE Manager** (no EPICS) |

### Verified facts (from reading both repos)
- `bluesky_widgets/apps/queue_monitor/` is 4 small files (~450 lines) — clean seed. ✔
- `RunEngineClient.__init__` already takes `user_name`/`user_group`. ✔
- Beamline `user_group_permissions.yaml` **already allows** `newUser` and `newSample` under group `primary`. ✔ (permissions largely done, as expected)
- `qs-config.yml` already has `zmq_publish_console: true` → console/terminal widget will work. ✔
- Tune plans stamp `md["plan_name"]` = `tune_mr`/`tune_ar`/… → **routing plots by `plan_name` is viable without new metadata**. ✔
- Phase-3 widgets all exist in the local checkout: `models/plot_builders.py` (`Lines`, `max_runs`), `qt/figures.py` (`QtFigures`), `qt/zmq_dispatcher.py` (`RemoteDispatcher`). ✔
- `RE` is created at `src/usaxs/startup.py:62` via `init_RE(iconfig, subscribers=[bec, cat])` — the single place to add the `Publisher`. ✔

---

## 1. Target package structure (new, in-repo)

```
bluesky-bits/
└── usaxs-qmonitor/               # project dir (hyphen) — must differ from package name
    ├── pyproject.toml            # deps: bluesky-widgets, bluesky-queueserver-api, qtpy, PyQt5, matplotlib
    ├── README.md
    └── usaxs_qmonitor/           # importable package (underscore)
        ├── __init__.py
        ├── main.py               # entry point (adapted from apps/queue_monitor/main.py)
        ├── settings.py           # ZMQ addrs, plans dir, proxy addr, USAXS user defaults
        ├── viewer.py             # window + menus (adapted)
        ├── widgets.py            # the 2-tab layout (our customization)
        ├── run_engine_client.py  # UsaxsRunEngineClient(RunEngineClient): script_upload, function_execute
        ├── functions.py          # "New User"/"New Sample" dialogs + script-upload widget
        └── plots.py              # Live-plot tab: RemoteDispatcher → routing → Lines → QtFigures
```

Beamline-side changes stay in `src/usaxs/` (Publisher line, plan wrappers, proxy launcher, permissions tweak) so they land on the same branch.

---

## 2. Phase 0 — Scaffold (½ day)

**Goal:** stock queue-monitor behaviour, running from our package against a demo qserver.

1. Create `usaxs_qmonitor/` with `pyproject.toml`:
   - `name = "usaxs-qmonitor"`, `requires-python = ">=3.11"`
   - deps: `bluesky-widgets`, `bluesky-queueserver-api`, `qtpy`, `PyQt5`
   - entry point: `usaxs-qmonitor = usaxs_qmonitor.main:main`
2. Copy the 4 app files (`main.py`, `settings.py`, `viewer.py`, `widgets.py`) as the seed; rename classes (`Viewer`→`UsaxsViewer`, etc.).
3. `settings.py`: hardcode-with-override the beamline ZMQ addrs, add `plans_dir`, `zmq_proxy_info_addr`, `user_name="usaxs"`, `user_group="primary"`.
4. `viewer.py`: construct `UsaxsRunEngineClient(...)` (Phase 1) instead of `RunEngineClient`, passing `user_name`/`user_group`.
5. **Acceptance:** `usaxs-qmonitor` launches, connects to a local demo RE Manager, shows/monitors the queue, runs a plan.

*Demo qserver for testing (no EPICS):*
```bash
conda activate usaxs_qmon
start-re-manager --zmq-publish-console ON       # ships with bluesky-queueserver
# separate terminal:
usaxs-qmonitor                                   # or: python -m usaxs_qmonitor.main
```

---

## 3. Phase 1 — Script upload button (½–1 day)

**Model** — `usaxs_qmonitor/run_engine_client.py`:
```python
from bluesky_widgets.models.run_engine_client import RunEngineClient

class UsaxsRunEngineClient(RunEngineClient):
    def script_upload(self, file_path, run_in_background=False):
        with open(file_path) as f:
            script = f.read()
        return self._client.script_upload(script, run_in_background=run_in_background)
```

**View** — in `functions.py`, a small widget:
- "Load plan file…" button → `QFileDialog` pinned to `settings.plans_dir` (`src/usaxs/user/`).
- Optional list widget of `*.py` in that dir sorted by mtime + "Load selected".
- After upload: poll `task_result(uid)`; on error show traceback in a `QMessageBox`; on success call `self.model.load_allowed_plans()` so the plan editor refreshes.

**Acceptance:** load a real plan file from the GUI → new plan appears in the command designer; a deliberately broken file shows its traceback.

---

## 4. Phase 2 — Function execution + plan wrappers (1–2 days)

### 4a. `function_execute` route (interactive "do it now")
Model addition:
```python
from bluesky_queueserver_api import BFunc

def function_execute(self, name, *args, run_in_background=False, **kwargs):
    return self._client.function_execute(
        BFunc(name, *args, **kwargs), run_in_background=run_in_background)
```
Dedicated dialogs in `functions.py`: **"New User…"** and **"New Sample…"** buttons → small parameter dialogs → `function_execute("newUser", …)`. Surface `task_result` success/failure in a status line.

Permissions: **already present** for `primary` (`newUser`, `newSample`). Only add new names here if we expose more functions.

### 4b. Plan-wrapper route (queueable between scans)
In `bluesky-bits` (`src/usaxs/plans/plans_user_facing.py` or a new `user_actions_plans.py`), add thin generator wrappers, e.g.:
```python
def new_user_plan(name, ...):
    yield from bps.null()
    newUser(name, ...)
```
Export in `startup.py`'s QS import block so they appear in `plans_allowed` and get the existing plan-editor UI for free.

**Acceptance:** `newUser("test")` from the GUI button has the same effect as from IPython; `new_user_plan` is queueable from the command designer.

---

## 5. Phase 3 — Live plots (3–5 days, the real work)

### 5a. Beamline side (`bluesky-bits`)
1. In `src/usaxs/startup.py`, right after `RE, sd = init_RE(...)` (line 62), subscribe a Publisher (guarded/optional via iconfig flag so it's a no-op if the proxy isn't running):
   ```python
   from bluesky.callbacks.zmq import Publisher
   RE.subscribe(Publisher("localhost:5567"))
   ```
   (Add unconditionally — harmless in IPython where BEC also plots locally; essential under queueserver.)
2. Run the proxy daemon next to the RE Manager (add to `qs_host.sh` or a systemd unit):
   ```bash
   bluesky-0MQ-proxy 5567 5568
   ```

### 5b. GUI side (`usaxs_qmonitor/plots.py`)
- `RemoteDispatcher("localhost:5568")` (from `bluesky_widgets.qt.zmq_dispatcher`).
- One `Lines(x=<motor field>, y=[<signal field>], max_runs=5)` model **per tune type** — `max_runs=5` natively keeps the last 5 scans overlaid (FIFO).
- Route each run to the right `Lines` model by inspecting the **start doc `plan_name`** (`tune_mr`→I0 vs MR motor field; `tune_ar`→UPD vs AR motor field).
- Render with `QtFigures` embedded in Tab 2.
- **"Clear plots"** button that rebuilds/empties the `Lines` models (the "kill on geometry change" behaviour); optionally auto-clear when a geometry-changing function runs.

> **Runtime verification required (cannot be determined statically):** the exact document **field names** for x (motor) and y (detector). From the plans, `tune_ar` scans `a_stage.r` reading `UPD`, `tune_mr` scans `m_stage.r` reading `I0`. The dispatcher must use the actual event-doc keys (e.g. `a_stage_r`, `UPD`). Confirm by printing one live doc:
> ```bash
> python -c "from bluesky.callbacks.zmq import RemoteDispatcher; d=RemoteDispatcher('localhost:5568'); d.subscribe(lambda n,doc: print(n, list(doc.get('data',{}).keys()) or doc.get('plan_name'))); d.start()"
> ```
> Run one `tune_ar` from the queue and read off the keys.

**Acceptance:** run `tune_ar` from the queue → live curve appears in Tab 2; five successive tunes overlay; "Clear plots" works; GUI restart shows only subsequent scans.

---

## 6. Phase 4 — Two-tab layout (folded into Phases 0–3, polished here)

`usaxs_qmonitor/widgets.py` — replace the stock 2-tab (`Monitor`/`Edit`) split with the requested layout:

- **Tab 1 — "Queue Control"** (`QtRunEngineManager_Control`):
  - Top row: `QtReEnvironmentControls`, `QtReQueueControls`, `QtReExecutionControls`, `QtReStatusMonitor`.
  - Our action bar: **New User**, **New Sample**, **Load plan file…** (from `functions.py`).
  - Command designer: `QtRePlanEditor` + `QtRePlanQueue` (wire `pq.registered_item_editors.append(pe.edit_queue_item)`).
  - History: `QtRePlanHistory`.
  - `QtReRunningPlan` for the currently-running plan.
- **Tab 2 — "Live View"** (`QtRunEngineManager_LiveView`):
  - `QtFigures` (plots) on top, `QtReConsoleMonitor` (terminal) below, in a vertical `QSplitter`.

Layout is pure Qt; tweak freely later.

---

## 7. Phase 5 — Verification & docs

- One-page user guide (launch, connect, run plan, new user/sample, load plan, read plots).
- Test destroy/reopen-environment: stale namespace (functions gone until re-run), stale plots (Clear).
- Note the **environment-persistence caveat**: `newUser()` state lives in the worker; lost on Destroy Environment. Consider persisting to file that startup re-reads.
- Pin final `bluesky-widgets` / `bluesky-queueserver-api` versions in `pyproject.toml` once stable.

---

## 8. Test environment on this laptop (built & verified)

conda env `usaxs_qmon` (py3.11), created with:
```bash
conda create -y -n usaxs_qmon python=3.11
conda run -n usaxs_qmon pip install PyQt5 qtpy bluesky-queueserver \
    bluesky-queueserver-api matplotlib -e ~/GitHub/bluesky-widgets
conda install -y -n usaxs_qmon -c conda-forge redis-server   # demo RE Manager needs redis
pip install -e ~/GitHub/bluesky-bits/usaxs-qmonitor          # the new package
```
Notes learned during Phase 0:
- **Project dir is `usaxs-qmonitor/` (hyphen), package is `usaxs_qmonitor/` (underscore).** The dir must NOT share the package name or it shadows the package as a namespace package when CWD is the repo root.
- **`matplotlib` is required** — the demo worker profile (and Phase-3 `QtFigures`) import it.
- **`redis-server` is required** for a local demo RE Manager.

**Local demo (no EPICS) — verified working:**
```bash
conda activate usaxs_qmon
redis-server --daemonize yes --port 6379          # once
start-re-manager --zmq-publish-console ON          # terminal 1
usaxs-qmonitor                                      # terminal 2
```
Phase-0 round-trip confirmed headlessly: connect → `manager_state=idle`, 35 demo plans allowed → open environment → queue `count` → execute → `count completed` in history → close environment. User identity defaults to `usaxs` / `primary`.

Full plot/tune verification (Phase 3 acceptance) still requires the real beamline worker (or a sim startup that emits documents) plus the 0MQ proxy.

**API note for Phase 2:** the queueserver API method is `function_execute` (present); there is no `functions_allowed` — allowed functions are governed by `permissions_get`/`permissions_set` and the permissions YAML.

---

## 9. Open questions / to confirm during build

1. **Plot field names** — resolved at runtime (Section 5b), not statically. First real task in Phase 3.
2. **`newSample` signature** — confirm required args for the "New Sample…" dialog (read `newSample` in bluesky-bits when building Phase 2).
3. **Proxy lifecycle** — where to run `bluesky-0MQ-proxy` at the beamline (add to `qs_host.sh` vs systemd). Beamline-ops decision; default: add to `qs_host.sh`.
4. **iconfig flag for Publisher** — add an on/off switch in `iconfig.yml` so the Publisher line is a no-op when the proxy isn't up? (Recommended: yes.)
5. **Which extra functions** beyond `newUser`/`newSample` to expose as buttons later (e.g. mode changes) — additive.
```

## 10. Build order summary

- [x] Phase 0 — scaffold package, run stock behaviour vs demo qserver
- [x] Phase 1 — script upload
- [x] Phase 2 — function_execute buttons + plan wrappers
- [x] Phase 3 — Publisher + proxy + live plots tab
- [ ] Phase 4 — two-tab layout polish
- [ ] Phase 5 — verify + docs + pin versions

### Phase 3 notes (verified end-to-end on this laptop)

Tested with a real `bluesky-0MQ-proxy 5567 5568` and a Publisher-fed RunEngine
running synthetic scans: routing by `plan_name` (tune_ar→ar, tune_mr→mr, other→
ignored), `max_runs=5` FIFO cap, artists drawn on the axes, and "Clear plots"
all pass.

Two things to know:
- **ZMQ SUB slow-joiner**: the very first run published in the ~1 s right after
  `connect_stream()` can be dropped before the subscription propagates. The GUI
  auto-connects at startup and then sits idle, so real scans (which happen later)
  are unaffected. Only relevant if you connect the stream mid-scan.
- **Field names still need beamline confirmation.** `settings.plot_config` uses
  the expected event-doc field names (`a_stage_r`/`UPD`, `m_stage_r`/`I0`, …) but
  these must be checked against a live document once the Publisher is running (see
  §5b). Wrong names produce an empty plot, not an error — so if a tune shows no
  curve, check the field names first.

Beamline wiring added: `iconfig.yml DOC_STREAM` block (ENABLE + PUBLISH_ADDR),
the `Publisher` subscription in `startup.py` (guarded by that flag), and
`bluesky-0MQ-proxy` start/stop in `scripts/usaxs_qs_host.sh`.
