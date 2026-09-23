# USAXS Queue Monitor — Testing Checklist

## Status (2026-07)

**Verified at the beamline** ✅
- Launch GUI, connect, open environment.
- Load plan file → new plans appear in the command designer.
- New User and New Sample run correctly.
- All tune scans plot with the **correct detectors and axes** — so the
  `settings.py plot_config` field names are confirmed correct.
- Off-site: full demo smoke test (queue a `count`, run it, upload good/broken
  plan files, live plots from a synthetic stream).

**Bugs found on-site and fixed** (relaunch `usaxs-qmonitor` to pick up — it's an
editable install)
- newUser via the GUI re-executed startup → fixed.
- Terminal hung after closing the GUI → fixed (clean force-exit).
- Live plots crashed the app after several scans (runs double-added) → fixed
  (de-duplicate by uid).

**Still to verify** — the short list below is all that's left.

---

## Remaining checks

### 1. Repeated tunes (re-verify after the crash fix)
- [ ] Run `tune_ar` 5–6 times → the last 5 scans overlay and **no crash**.
- [ ] `tune_mr` shows on its own plot (not on the AR plot).
- [ ] **Clear plots** empties them.

### 2. Robustness / edge cases
- [ ] **Destroy environment** (Control Actions menu → activate, then destroy)
      and re-open: plan list reloads; re-run `newUser` if needed; no crash.
- [ ] Close the GUI → terminal returns to the prompt cleanly.
- [ ] Kill/restart the queueserver while the GUI is open → GUI reflects the
      disconnect and recovers on reconnect.

### 3. Sign-off
- [ ] Decide day-to-day: immediate **New User/Sample buttons** vs. the queueable
      `new_user_plan`/`new_sample_plan` (both work; pick a convention).
- [ ] Merge `qmonitor-gui` → `bait`/`main` per your workflow.
- [ ] (Optional) Pin `bluesky-widgets` before an APS run — it is beta.

---

## Reference

### Re-confirming plot field names (only if a plot ever shows no curve)
Run while a tune executes and read the keys it prints:
```bash
python -c "from bluesky.callbacks.zmq import RemoteDispatcher; \
d=RemoteDispatcher('localhost:5568'); \
d.subscribe(lambda n,doc: print(n, list(doc.get('data',{}).keys()) or doc.get('plan_name'))); \
d.start()"
```
Update `usaxs-qmonitor/usaxs_qmonitor/settings.py` → `plot_config` `x`/`ys` to
match. (Already confirmed correct in 2026-07 testing.)

### Local demo (no beamline)
```bash
conda activate usaxs_qmon
redis-server --daemonize yes --port 6379
start-re-manager --zmq-publish-console ON      # terminal 1
usaxs-qmonitor                                 # terminal 2
```

### Tested dependency versions (off-site, 2026-07)
```
bluesky-widgets==0.0.18       bluesky==1.15.1        qtpy==2.4.3
bluesky-queueserver==0.0.24   ophyd==1.11.2          PyQt5==5.15.11
bluesky-queueserver-api==0.0.13  bluesky-live==0.0.8  matplotlib==3.11.0
event-model==1.24.0
```
`PyQt5==5.15.11` matches the beamline environment.
