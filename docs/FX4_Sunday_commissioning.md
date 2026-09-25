# FX4 commissioning runbook

**For the session at the ops computer.** Branch `fx4-conversion`.

> **If you are an agent starting a fresh session here:** read `PLAN.md` section
> 0 first (what is built, what is untested), then this file. Do not re-derive
> state from the diff. `PLAN.md` sections referenced below as "§n".

Nothing in this branch has ever touched hardware. Every FX4 PV name is an
assumption taken from `docs/FX4_config_cheatsheet.md`. Stage 0 exists to turn
those assumptions into facts before anything else runs.

Work the stages in order. Each one says what to run, what "good" looks like,
and what to change if it does not. **Record the result in the table at the
bottom as you go** — that table is the handover to the next session.

---

## Pre-flight

| | |
|---|---|
| ☐ | Hardware rewired: UPD → `usxFX4` ch1, TRD → ch4, I0 → `usxFX42` ch1 |
| ☐ | PSO gate on **D1 of both** FX4s, each with its own 50 Ω feed-through terminator (the PRL-414B is a 1:4 driver). Scope check: HIGH ≈ 2.5 V, not ~5 V |
| ☐ | `git fetch && git checkout fx4-conversion` on the ops computer |
| ☐ | Deploy `ADconfigs/` to `/share1/AreaDetectorConfig/` (see `ADconfigs/README.md`), **and re-run `WAXS_config/copy_attributes_to_template.py`** |
| ☐ | Restart the AD IOCs so they pick up the new attribute files |
| ☐ | `pre-commit run --all-files` and `pytest` still pass |

**Rollback at any point:** `git checkout main`, restart the session, rewire.
The window is weeks (§6) — a stage that fails is a thing to understand, not an
emergency.

---

## Stage 0 — bench checks (no beam, ~15 min)

Everything below is read-only except the last block. Paste the whole output
back into the session; several later stages branch on it.

```bash
# 0.1  THE BIG ONE: do the time-series records sit where the code expects?
dbl "usxFX4:FX4:Current1:*" | grep -i ts
caget usxFX4:FX4:Current1:TSMeanValue.NELM      # want >= 8000

# 0.2  usxFX42's autoranger -- added 2026-09-24, never checked against the code
dbl "usxFX42:FX4:seq01:*" | sort
caget usxFX42:FX4:seq01:channel                 # want 1 (I0)

# 0.3  enum strings -- the code writes these as strings, so spelling matters
caget -d 31 usxFX4:FX4:TriggerMode
caget -d 31 usxFX4:FX4:TriggerPolarity
caget -d 31 usxFX4:FX4:AcquireMode
caget -d 31 usxFX4:FX4:Range

# 0.4  UNITS -- a factor of 1e12 if this is wrong
caget usxFX4:FX4:Current1:MeanValue_RBV
caget usxFX4:FX4:ch1_CurrentScale usxFX4:FX4:Current1:MeanValue_RBV.EGU

# 0.5  PSO strobe width -- sets the fly-scan VPR ceiling
dbl "usxAERO:pm1:*" | grep -i "pulse\|width"
caget usxAERO:pm1:PulseWidth usxAERO:pm1:NumPulses usxAERO:pm1:NumPoints

# 0.6  present state, for the record
caget usxFX4:FX4:ValuesPerRead usxFX4:FX4:SampleTime_RBV \
      usxFX4:FX4:AveragingTime usxFX4:FX4:RingOverflows \
      usxFX4:FX4:Current1:EnableCallbacks usxFX4:FX4:Current1:CallbacksBlock
```

**One live test** (shutter closed; note the settings from 0.6 first):

```bash
caput usxFX4:FX4:TriggerMode "Free run"
caput usxFX4:FX4:AcquireMode Single
caput usxFX4:FX4:ValuesPerRead 100
caput usxFX4:FX4:Current1:EnableCallbacks Enable
caput usxFX4:FX4:Current1:CallbacksBlock  Yes
caput usxFX4:FX4:AveragingTime 3.0
time caput -w 20 usxFX4:FX4:Acquire 1     # must take ~3 s, NOT return instantly
caget usxFX4:FX4:NumAveraged_RBV usxFX4:FX4:RingOverflows
#     expect ~3000 at VPR=100, RingOverflows unchanged
caput usxFX4:FX4:AveragingTime 10.0
time caput -w 30 usxFX4:FX4:Acquire 1
caget usxFX4:FX4:NumAveraged_RBV usxFX4:FX4:RingOverflows
#     expect ~10000 and STILL no new overflow -> VPR=100 gives a 10 s ceiling
```

### What each answer changes

| finding | action |
|---|---|
| TS records are `Current1:TS:TSMeanValue`, not `Current1:TSMeanValue` | edit the five `ADComponent` suffixes in `StatsPluginQuadEM` (`devices/fx4_quadem.py`) **and** the `pvname=` entries in `ADconfigs/Flyscan_config/saveFlyData.xml` |
| `usxFX42:FX4:seq01:` record names differ from `usxFX4`'s | `FX4AutorangeDevice` needs a variant class; today both use the same one |
| an enum string differs | fix the literal in `plans/fx4_setup.py` (`"Free run"`, `"Ext. bulb"`, `"Negative"`, `"Continuous"`, `"Single"`) |
| `MeanValue_RBV` is in **A**, not pA | either fix `CurrentScale` in the IOC (preferred — the code, the XML and the reduction all assume pA), or change every pA reference. Do not leave it ambiguous |
| `Range` label is not `"<number> <unit>"` (e.g. `"fast 100 nA"`) | `utils/fx4_ranges.py` returns `None` and the autoscale falls back to absolute backstops — it still works, but extend `_LABEL` to parse it |
| `Acquire` returns instantly with `CallbacksBlock=Yes` | **stop.** The whole step-scan trigger model assumes the falling edge means "mean is ready". Raise it before going further |
| `RingOverflows` increments at 10 s / VPR=100 | `RING_SIZE` is below 10000; lower the max count time or raise `RING_SIZE` in `FX4.cmd` |

---

## Stage 1 — the session starts (no beam)

```bash
./scripts/start-usaxs-bits.sh
```

Good: it reaches the prompt with no traceback. Then:

```python
fx4.current1.mean_value.get()      # a current, in pA
UPD.name, I0.name, TRD.name        # 'UPD', 'I0', 'TRD'
upd_controls                       # <FX4DetectorControls UPD: fx4 ch1 (auto)>
I0_controls                        # ... fx42 ch1 (auto)
I00_controls                       # ... fx42 ch2 (fixed range)
```

A static check already confirmed all 206 module-level registry lookups resolve
against the YAML, so an import error here means a *device* failed to connect,
not a missing name.

---

## Stage 2 — count once (beam, shutter control)

```python
RE(prepare_fx4_counting(0.1))
RE(bps.trigger(fx4, wait=True))
UPD.get()          # pA, plausible, changes when you open the shutter
```

**This is the single most important check in the whole runbook.** If a bare
`bps.trigger` on an unstaged device raises `RuntimeError`, the `trigger()`
override in `QuadFX4` is not doing its job and nothing downstream works.

---

## Stage 3 — autoscale and dark current

```python
RE(autoscale_amplifiers([upd_controls, I0_controls]))
upd_controls.auto.lurange.get()    # settled range
upd_controls.auto.channel.get()    # 1  <- must be UPD, not 4
```

Expect convergence in 2-3 reads once seeded; the log prints the range and where
the reading sits in it (`ok` / `above` / `below the useful window`).

Then check the channel juggling, which is the failure mode with no error
message:

```python
RE(autoscale_amplifiers([trd_controls]))
upd_controls.auto.channel.get()    # 4 now
RE(autoscale_amplifiers([upd_controls, I0_controls]))
upd_controls.auto.channel.get()    # back to 1
RE(autoscale_amplifiers([upd_controls, trd_controls]))   # must RAISE
#   FX4RangeConflictError: fx4: cannot autorange UPD and TRD together
```

Dark currents, shutter closed:

```python
RE(measure_background([upd_controls, I0_controls]))
upd_controls.auto.ranges.range0.background.get()
```

**Tune the convergence window here** — live signals, no code edit:

```python
upd_controls.auto.min_fraction.put(0.10)
upd_controls.auto.max_fraction.put(0.90)
```

---

## Stage 4 — tune one axis

```python
RE(tune_mr())     # uses I0 on fx42
RE(tune_ar())     # uses UPD on fx4
```

Good: one trace on the plot (not four, not eight), the peak is found, the
LiveTable shows `UPD` and `I0` in pA. If several traces appear, `select_fx4_plot`
is not doing its job.

Then `tune_a2rp`, `tune_dx`, `tune_dy`, and `find_ar` — `find_ar` is the one that
leaves the sequence program in `automatic` for a wide sweep, so watch that the
range moves during the scan and that it is ranging on **UPD**.

---

## Stage 5 — transmission

```python
RE(measure_USAXS_Transmission())
terms.USAXS.transmission.diode_counts.get()   # pA
terms.USAXS.transmission.diode_gain.get()     # 1.0 exactly
upd_controls.auto.channel.get()               # 1  <- restored
```

The channel restore runs from a finaliser, so check it holds after an abort too
(Ctrl-C mid-measurement, then read `channel` again). A scan started with the
channel left on TRD produces plausible-looking wrong data.

---

## Stage 6 — step USAXS

```python
RE(USAXSscanStep(x, y, thickness, "FX4 commissioning step scan"))
```

Good: `UPD` and `I0` in the LiveTable in pA, `TRD`/`I00` absent, no ring-overflow
warning at the end. Check the saved HDF5 carries `counting_chain = "FX4"`.

With `useDynamicTime` on, the dwell changes by thirds across the scan — each
value should be a whole number of mains cycles (a multiple of 16.667 ms).

---

## Stage 7 — PSO / VPR commissioning ⭐

**The one genuinely empirical task. Budget real time for it.** Full reasoning in
§5.2; the short version is that two opposite effects both look like missed
pulses:

| symptom | cause | fix |
|---|---|---|
| fewer points, `NumAveraged` normal | samples dropped in transit | **raise** VPR |
| fewer points, `NumAveraged` ≈ 2× on the short intervals | neighbouring exposures merged | **lower** VPR, or widen the strobe |

Procedure — short trajectory (a few hundred pulses), VPR ∈ {5, 10, 20, 50}:

```python
from usaxs.plans.fx4_setup import fx4_flyscan_mode
RE(fx4_flyscan_mode(fx4, 8192, values_per_read=VPR))
RE(fx4_flyscan_mode(fx42, 8192, values_per_read=VPR))
# ... run the trajectory ...
fx4.current1.ts_current_point.get()      # vs usxAERO:pm1:NumPulses
fx4.ring_overflows.get()                 # must stay 0
```

Record captured/expected and the `NumAveraged` spread for each VPR. Pick the
**largest** VPR that captures 100 %, then confirm at full length (8000 pulses)
**with both boxes streaming at once** — they share a host, and the throughput
limit belongs to the host, not to one box.

Set the winner as `DEFAULT_FLYSCAN_VPR` in `plans/fx4_setup.py`.

If the window between "drops" and "merges" turns out to be uncomfortably narrow,
the other lever is widening the PSO strobe in the Aerotech configuration.

---

## Stage 8 — fly scan

```python
RE(Flyscan(x, y, thickness, "FX4 commissioning fly scan"))
```

Watch the progress log: the `pulses` column should climb steadily and `samples`
should stay in a tight cluster — a scattered `samples` column means the AR sweep
is not tracking and the stage wants retuning.

Then open the HDF5 and check:

- `entry/flyScan/upd_current`, `I0_current` — full length, sensible pA
- `entry/flyScan/channel_time` — present, ≈ the expected interval, low spread
- `entry/flyScan/ring_overflows`, `ring_overflows_I0` — both 0
- `entry/flyScan@counting_chain` = `"FX4"`, `<saveFlyData version="2.0">`

Reduce it: `I(q)` comes from `upd_current / I0_current` with **no gain term and
no dwell-time term**.

---

## Stage 9 — SAXS and WAXS

```python
RE(saxsExp(x, y, thickness, "FX4 commissioning SAXS"))
RE(waxsExp(x, y, thickness, "FX4 commissioning WAXS"))
```

Check in the frame's NeXus metadata: `I0_cts_gated` non-zero and scaling with
exposure time, `Exp_time_gated` ≈ the acquire time, `counting_chain = "FX4"`,
and `/entry/control/integral` resolving.

Remember what this is: the integration window is **software-timed**, only
approximately the exposure window (§5.0). Uniform exposures are fine; the proper
gating is a shutdown task.

---

## Stage 10 — validate

Measure the standard reference material and reduce it exactly as usual.

**Check the absolute level, not only the curve shape.** `diode / I0` is a ratio,
so a scale error common to both channels cancels in the shape and shows up only
in the absolute intensity — which is precisely what the SRM pins down.

If the shape is right and the level is off: understand why before changing
anything. Absolute-scale work can wait for commissioning time before the next
user run; what matters today is knowing the cause.

---

## Troubleshooting

| symptom | first place to look |
|---|---|
| `RuntimeError: not ready to trigger` | `QuadFX4.trigger` override, `devices/fx4_quadem.py` |
| reading is ~1e-12 of what it should be | units are A not pA — Stage 0.4 |
| mean equals the *previous* point | `CallbacksBlock` is not `Yes`; `fx4_scaler_mode` |
| four or eight traces on a tune plot | `select_fx4_plot`, `utils/fx4_channels.py` |
| autoscale never converges | `min_fraction`/`max_fraction`, or `seq01:channel` on the wrong detector |
| `FX4RangeConflictError` | two autoranged channels on one box — correct behaviour; split the call |
| fly scan short by a few points | Stage 7 — use `NumAveraged` to tell dropped from merged |
| fly-scan means look biased | `RingOverflows` non-zero; raise VPR |
| USAXS scan ranged for the transmitted beam | a `seq01:channel` restore was missed; `restore_upd_channel` |
| SAXS/WAXS `I0_cts_gated` is zero | `start_gated_I0`/`finish_gated_I0`; check `fx42` actually triggered |

---

## Results — fill in as you go

| stage | result | notes |
|---|---|---|
| 0 bench checks | | |
| 1 session starts | | |
| 2 single count | | |
| 3 autoscale / dark | | |
| 4 tune axes | | |
| 5 transmission | | |
| 6 step USAXS | | |
| 7 PSO / VPR | chosen VPR = | |
| 8 fly scan | | |
| 9 SAXS / WAXS | | |
| 10 SRM validation | | |

**Also do once things work:** regenerate the queueserver's device list —
`src/usaxs/qserver/existing_plans_and_devices.yaml` — and commit it.
