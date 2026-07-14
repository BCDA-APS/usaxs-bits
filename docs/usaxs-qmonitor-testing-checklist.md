# USAXS Queue Monitor — Testing Checklist

What to verify before trusting `usaxs-qmonitor` at the beamline. Phases 0–3 were
verified off-site against a **local demo queueserver** and **synthetic
documents**; the items marked **[BEAMLINE]** could only be confirmed with the
real 12-ID-E queueserver and hardware.

> Quick status: the GUI connects, drives the queue, uploads plan files, runs
> `function_execute`, and draws live plots from a 0MQ stream — all proven in a
> demo. The **plot field names** and the **real newUser/tune behaviour** are the
> main things still to confirm on-site.

---

## A. Off-site smoke test (no beamline, no EPICS)

Reproduces everything except real hardware. Needs `redis-server` and a demo
RE Manager.

```bash
# one-time environment (laptop)
conda create -y -n usaxs_qmon python=3.11
conda run -n usaxs_qmon pip install PyQt5 qtpy bluesky-queueserver \
    bluesky-queueserver-api matplotlib -e <path>/bluesky-widgets
conda install -y -n usaxs_qmon -c conda-forge redis-server
conda run -n usaxs_qmon pip install -e <repo>/usaxs-qmonitor

# run the demo
conda activate usaxs_qmon
redis-server --daemonize yes --port 6379
start-re-manager --zmq-publish-console ON      # terminal 1
usaxs-qmonitor                                 # terminal 2
```

Check:
- [ ] Window opens, title shows `usaxs@primary`, **Help → Connection Info** lists the ports.
- [ ] **Open environment** succeeds (needs `matplotlib` in the env).
- [ ] Build a `count` plan in the command designer, **Add to queue**, **Start** → it runs and appears in history.
- [ ] **Load plan file…** a small `.py` defining a plan → status `Loaded … ✓`, plan appears in the list; a broken file shows a traceback dialog.
- [ ] Live plots: to exercise the stream off-site, run `bluesky-0MQ-proxy 5567 5568` and publish synthetic docs (see `../USAXS-GUI-IMPLEMENTATION.md` §5b / the Phase-3 test), then confirm curves appear and **Clear plots** empties them.

---

## B. [BEAMLINE] Connect & drive the real queue

With the real queueserver running (`scripts/usaxs_qs_host.sh start`):

- [ ] `usaxs-qmonitor` connects; status monitor shows the Manager state.
- [ ] **Open environment** loads `usaxs.startup` without error (watch the terminal tab).
- [ ] The plan list is populated with USAXS plans (`USAXSscan`, `Flyscan`, `tune_*`, `mode_*`, …).
- [ ] Queue and run a **harmless** plan (e.g. a short `tune_mr` or a count) and confirm it executes and lands in history.
- [ ] The **terminal tab** shows the same console output you'd see in IPython.

---

## C. [BEAMLINE] New User / New Sample

- [ ] **New User…** with a test name → same effect as `newUser("test")` from IPython
      (data directory created; status line shows the path; check the Obsidian log entry).
- [ ] **New Sample…** with a name → same as `newSample(...)`; sample dir/PV updated.
- [ ] Running **New Sample** *before* New User shows the "run newUser() first" error dialog (expected).
- [ ] (Optional) Queue `new_user_plan` / `new_sample_plan` from the command designer and confirm the queued variant works too.

---

## D. [BEAMLINE] Live tune plots — **confirm field names first**

This is the item most likely to need a fix. The plot config guesses the
event-document field names; they must match the real documents.

**Prerequisites on the beamline side:**
- [ ] `iconfig.yml` → `DOC_STREAM.ENABLE: true` (default) and `PUBLISH_ADDR: localhost:5567`.
- [ ] `bluesky-0MQ-proxy` running next to the Manager (started automatically by
      `scripts/usaxs_qs_host.sh start`; confirm with `pgrep -f bluesky-0MQ-proxy`).
- [ ] GUI **Connection Info** shows the doc stream **connected**.

**Confirm the field names** — run this in the GUI env while a tune executes, and
read the keys it prints:

```bash
python -c "from bluesky.callbacks.zmq import RemoteDispatcher; \
d=RemoteDispatcher('localhost:5568'); \
d.subscribe(lambda n,doc: print(n, list(doc.get('data',{}).keys()) or doc.get('plan_name'))); \
d.start()"
```

Then run `tune_ar` (and `tune_mr`, etc.) from the queue and note:
- the motor field for x (expected `a_stage_r` for AR, `m_stage_r` for MR, …)
- the detector field for y (expected `UPD` for AR, `I0` for MR, …)

Update `usaxs-qmonitor/usaxs_qmonitor/settings.py` → `plot_config` so `x` and
`ys` match the real keys. (Wrong names draw an **empty** plot, not an error.)

**Then verify plotting:**
- [ ] Run `tune_ar` from the queue → a live curve appears on the `tune_ar` plot.
- [ ] Run it 5+ times → the last 5 scans overlay; the oldest drops off.
- [ ] `tune_mr` shows on its own plot (I0 vs MR), not on the AR plot (routing by `plan_name`).
- [ ] **Clear plots** empties them.
- [ ] Restart the GUI → it shows *subsequent* scans, not historical ones.

---

## E. [BEAMLINE] Robustness / edge cases

- [ ] **Destroy environment** (Control Actions menu → activate, then destroy) and
      re-open: the plan list reloads; re-run `newUser` if needed. No crash.
- [ ] After a geometry change, **Clear plots** so stale curves don't mislead.
- [ ] Upload a plan file that **shadows** an existing plan name — confirm the
      convention holds (uploads define plans, not devices) and behaviour is sane.
- [ ] Kill/restart the queueserver while the GUI is open → GUI reflects the
      disconnect and recovers on reconnect.

---

## F. Sign-off / hand-off

- [ ] Field names in `plot_config` corrected and committed.
- [ ] Decide which function route (immediate buttons vs queueable plans) staff
      should use day-to-day (both are implemented).
- [ ] Pin the tested dependency versions if desired (see below).
- [ ] Merge `qmonitor-gui` → `bait`/`main` per your workflow.

### Tested dependency versions (off-site, 2026-07)

```
bluesky-widgets==0.0.18       bluesky==1.15.1        qtpy==2.4.3
bluesky-queueserver==0.0.24   ophyd==1.11.2          PyQt5==5.15.11
bluesky-queueserver-api==0.0.13  bluesky-live==0.0.8  matplotlib==3.11.0
event-model==1.24.0
```
`PyQt5==5.15.11` matches the beamline environment. `bluesky-widgets` is beta —
pin it before an APS run and diff before upgrading.
