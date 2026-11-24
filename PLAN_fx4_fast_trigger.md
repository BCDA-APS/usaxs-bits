# PLAN — FX4 fast gate input (quadEM R9-8, FX4 firmware ≥ 26.10.151957)

**Status:** 2026-11-17 — bluesky side implemented (mode B, `Ext. trig.`,
Positive, `AcquireMode = Continuous`, i.e. decision 2(a); fly-scan VPR 20;
HDF5 marker, config_version 2.1).  Not yet: deploy `saveFlyData.xml`,
Matilda (§6), beam tests T4–T6.
**T2/T3 results (2026-11-17, both boxes on 26.10.151957, no beam):** 4000 and
8000 pulses of 20 µs at VPR 20 gave exactly 4000/8000 points on both boxes,
Positive and Negative alike.  `channel_time[0]` = 31 ms (first PSO interval),
`channel_time[-1]` = 1.000 s (`AveragingTime` tail).  Bulb file
GC_SRM3600_0003.h5 (2026-11-06): `channel_time[0]` = 0.72 s (pre-sweep
wait).  **So trig point i = bulb point i+1**; Matilda must branch.
`TriggerCount` counts both edges (16000 for 8000 pulses on usxFX42; usxFX4
read 0, unexplained).  `FX4_CPU` ~95 % on both boxes while armed at VPR 20.
The original plan text follows.
**Hardware state on 2026-11-13:** `usxFX42` (I0, I00) runs the new firmware and
the new driver; it works under manual control. **`usxFX4` (UPD, TRD) is still
on the old firmware and old driver.**
**Companion records:** `docs/FX4_PSO_trigger_issue.md`,
`docs/FX4_PSO_trigger_issue_2.md` (the ~1 ms gate floor this release fixes),
`PLAN.md` §5.2 (the VPR=5 / 600 µs test, which this makes obsolete).

---

## 1. What changed, as reported by the driver developer

1. **D1 is now an edge counter, not a polled level.** The driver puts D1 into
   the FX4's `encoder` pin mode. The counter increments on both rising and
   falling edges, so sub-µs pulses register. A short pulse adds 2 between two
   reads. A long pulse adds 1 at each edge.
2. **The firmware streams that counter at the ADC output rate**
   (100 kHz / `ValuesPerRead`). It used to be a separate 1 kHz poll. So the
   gate is now resolved to one sample period: 100 µs at VPR 10, 50 µs at VPR 5.
3. **Triggering is tested to 5 kHz** (VPR 10, two samples per trigger).
4. **New `Ext. Trig.` behaviour:** if the next trigger arrives before
   `AveragingTime` has elapsed, the driver closes the current average and
   starts the next point at once. `AveragingTime` therefore no longer has to be
   set just below the trigger period. The release notes say: *"external
   trigger mode is the same as external bulb mode if the trigger period is
   less than the averaging time."*
5. **Samples per point are no longer constant,** so the developer says to use
   the **Statistics plugin's Mean time series** (`Current<n>:TSMeanValue`), not
   the TimeSeries plugin.
6. New diagnostic records: FX4 CPU %, trigger level, trigger counter. There are
   also new records that write the trigger-input configuration at iocInit.
7. Small fixes: the `AveragingTime` PREC is now 4 (was 2), and the fan-out PREC
   fields are fixed.

---

## 2. What this means for us

### 2.1 The 5 kHz limit was never our constraint. The pulse width was.

A fly scan is ~4000 pulses in ~90 s: a 22.5 ms mean interval, ~44 Hz average.
Even the old ~1 kHz polling was fast enough **in rate**. What hurt was the
consequence of a polled level: a strobe had to be **≥ 1 ms wide** to be seen
reliably. That forced `usxAERO:pm1:PulseLength = 1200 µs`.

In `Ext. bulb` with `TriggerPolarity = Negative` the HIGH strobe is not
integrated, so this cost **~5 % dead time on every point**. It also coupled
the strobe width to `ValuesPerRead` (`min_strobe_width_us`,
`_check_strobe_width`, the whole VPR = 5 test).

**With the new firmware that constraint is gone.** The fly-scan VPR can be
chosen on link load and edge-timing resolution alone.

### 2.2 Two ways to use it

| | **A. Keep `Ext. bulb`, shorten the strobe** | **B. Switch to `Ext. Trig.`** (recommended) |
|---|---|---|
| What defines a point | LOW interval between strobes | rising edge → next rising edge |
| Dead time | strobe width (could be ~10 µs → ~0.05 %) | **none**, by construction |
| `AveragingTime` | ignored | must be **longer than the longest PSO interval** |
| Strobe width | still matters: the driver must recover the *level* from the edge counter | irrelevant, as long as it is narrower than the shortest interval |
| Code change | small: delete the width/VPR coupling | moderate: mode, `AveragingTime`, point-count logic, file marker |
| Index alignment vs. `AR_PulsePositions` | unchanged, *if* bulb behaves as before | **probably shifted by one** (§2.3) |
| Developer's recommended path | not mentioned | yes, documented on the quadEM scanning page |

**Recommendation: B.** It is the mode the developer tests and documents.
Dead time is zero by construction rather than "small". And it does not depend
on how the driver turns an edge counter back into a level, which nobody has
described. A stays available as the fallback if B's alignment turns out to be
awkward.

### 2.3 The scientific risk: point ↔ position alignment

Matilda (`matilda/supportFunctions.py:_importFlyscanFX4`) pairs
`upd_current[i]` with `AR_PulsePositions[i+1]`. It drops the first position as
"one extra leading point", just as it does for the Struck chain. That rule
encodes what a point means in **today's** bulb mode.

What the two modes produce for N strobes, as far as the documentation tells
us (**to be confirmed on hardware; see T3**):

* **Bulb, Negative:** the line idles LOW, so the box may integrate from
  `Acquire = 1` until the first strobe. That would make point 0 a long
  pre-sweep interval covering the busy-record rebuild and the taxi. The LOW
  stretch after the last strobe never closes. Result: N points, the first
  possibly junk.
* **Ext. Trig.:** nothing is recorded before the first edge. Point *i* runs
  from strobe *i* to strobe *i+1*. After the last strobe the final point runs
  until `AveragingTime` expires or `Acquire = 0`. Result: N or N−1 points, the
  **last** being junk.

If that is right, the arrays shift by one index relative to today. Matilda's
`[1:]` would then pair every point with the wrong position: a one-bin shift in
Q across the whole curve. **That is the kind of error that looks fine and is
wrong.** It must be measured, not reasoned about, and the file must say which
mode wrote it (§5.4).

A useful by-product: an existing FX4 fly-scan file already shows how bulb mode
behaves. If `channel_time[0]` is seconds long, point 0 is the pre-sweep junk
interval.

### 2.4 The TimeSeries warning probably does not apply to us

We already harvest **`Current<n>:TSMeanValue`, `TSSigma`, `TSTotal` from
NDStats.** We control them through the Stats plugin's own `TS:` child
(`TS:TSAcquire`, `TS:TSNumPoints`). That is the "Statistics plugin Mean Time
Series" the developer recommends. We do not use the quadEM-level
`$(P)$(R)TS:` NDPluginTimeSeries. **Confirm with the developer** that this is
what he meant, and check on the new IOC that the PV names are unchanged.

Variable samples per point does not affect the data. `TSMeanValue` is a mean
and needs no dwell correction. `channel_time = TSTotal / TSMeanValue ×
SampleTime` becomes a genuine per-point dwell rather than a near-constant.

### 2.5 Both boxes must run the same firmware and mode

UPD/I0 is used **point by point** with no timing correction. That only works
because both boxes see the same strobes and define points identically. If
`usxFX4` stays in bulb on the old firmware while `usxFX42` runs `Ext. Trig.`,
the two series are offset by a point and use different windows. **Mode B
cannot ship until `usxFX4` is upgraded.** The code should refuse to fly in
mixed mode rather than guess (§5.2), in the same spirit as
`determine_in_operation()`.

**Open question for today/Monday:** does the *current* code (bulb, 1200 µs)
still work on the upgraded `usxFX42`? The new driver no longer streams D1's
level, so bulb mode is now derived from the counter. If a fly scan has to run
before `usxFX4` is upgraded, test T1 must pass first. Otherwise roll
`usxFX42` back.

### 2.6 What else benefits, and what does not change

* **Unchanged:** step scans, tunes, transmission, dark currents, monitor mode.
  They all use `Free run` with software triggers (`fx4_scaler_mode`,
  `fx4_monitor_mode`). Also unchanged: autoranging, busy record, suspender and
  abort logic.
* **Becomes possible (not this week):** finer fly-scan division, faster
  sweeps, and dropping the 2.7 % / 5 % dead-time argument from §5.2.
* **Becomes possible (needs a cable, not this week):** a **true hardware-gated
  I0 for SAXS/WAXS** (`PLAN.md` §5.0, today a software-timed stopgap in
  `start_gated_I0`). The detector's "exposing" TTL could drive `usxFX42` D1 in
  `Ext. bulb`, Positive. D1 is currently the PSO fan-out, so this needs either
  a switch or a second input, if the driver supports one. Ask the developer.

---

## 3. Decisions needed (Jan)

1. **Mode A or B?** Recommendation B (§2.2).
2. **How to end the series in mode B:**
   * (a) `AcquireMode = Continuous`, accept N points, mark the last one invalid
     in the writer and in Matilda; or
   * (b) `AcquireMode = Multiple`, `NumAcquire = NumPulses − 1`. The box stops
     itself on the last real interval and there is no junk tail. This is
     cleaner, but an exact pulse count becomes load-bearing.

   Recommendation: (b), **if** T2 shows the pulse count is exact every time;
   otherwise (a).
3. **File marker:** add `flyScan/@fx4_trigger_mode` (and a
   `point_alignment` string) to the fly-scan HDF5. This is additive and old
   files stay readable, but it is a saved-file format change, so it is your
   call. Without it Matilda cannot tell a bulb file from a trig file.
4. **Fly-scan VPR:** keep 10 (proven link load; 100 µs edge resolution against
   a ≥ several-ms interval). Drop the VPR = 5 experiment.

---

## 4. Hardware tests, in order

Record after every fly scan: `TSCurrentPoint` on both boxes,
`usxAERO:pm1:NumPulses`, the **new FX4 trigger counter** on both boxes,
`RingOverflows`, and `channel_time` first/last/min/max from the HDF5.

**T0 — read the new IOC (15 min, usxFX42 now, read-only).** List the new
records: `grep record` in the R9-8 `FX4.template`, or `dbl` on the IOC
console. Note the exact names of the trigger counter, trigger level, CPU % and
the iocInit trigger-config records. Confirm the D1 pin mode reads `encoder`.
Confirm the Stats `TS:` PVs and `Current<n>:TSMeanValue.NELM = 8192` still
exist. Note the firmware version PV, if there is one.

**T1 — does today's code run on the new usxFX42? (1 fly scan).** Use the
unchanged plan: bulb, Negative, 1200 µs. Pass: both boxes report the same
`TSCurrentPoint` = NumPulses, and the UPD/I0 ratio curve looks normal. If it
fails, the decision is to roll back `usxFX42` before any user time.

**T2 — Ext. Trig. on usxFX42 alone, from the console (no plan change).** Use
a short trajectory (a few hundred pulses), then full length.
`TriggerMode = Ext. Trig.`, Polarity Positive, `AveragingTime = 1.0`, VPR 10.
Run it at PulseLength 1200 µs **and** at ~20 µs. A long pulse straddles sample
boundaries (counter +1, +1), a short one usually does not (+2). This checks
that the driver counts *one* trigger per pulse either way. Pass: points = N
(or N−1), trigger counter consistent with N pulses, `channel_time` per point ≈
the PSO interval.

**T3 — alignment (the one that matters).**
1. Take an existing bulb-mode FX4 fly-scan file and look at `channel_time[0]`
   and `channel_time[-1]`. This settles what bulb point 0 is.
2. After `usxFX4` is upgraded: two fly scans of the same sample, one bulb at
   1200 µs, one trig. Cross-correlate `upd_current/I0_current` between them.
   The lag in points (expected 0 or 1) is the index shift Matilda must apply.
   The rocking-curve peak is the sharpest feature and pins it.

**T4 — upgrade usxFX4, then both boxes in Ext. Trig.** Full 4000-pulse scan,
both boxes streaming. Pass: identical point counts on both boxes, zero ring
overflows, CPU % on both boxes recorded (link-load headroom).

**T5 — strobe width down.** At ~10–20 µs, confirm T4 still passes. Then set
it as the Aerotech default. Period first: `caput usxAERO:pm1:PulsePeriod`
before `PulseLength`; the driver forces period = length + 1.

**T6 — validation against the reference standard (`PLAN.md` §6).** Absolute
level and Q position against an archived bulb-mode reduction. A one-bin Q
shift will show here if T3 missed it.

---

## 5. Code changes (bluesky-bits)

### 5.1 Device layer — `src/usaxs/devices/fx4_quadem.py`
* Add the new diagnostics as `kind="config"`/`"omitted"` components:
  trigger counter, trigger level, CPU %, and firmware version if exposed.
  Names come from T0. Use `/Z`-style tolerance (an `EpicsSignalRO` that may be
  disconnected) so a box still on the old IOC does not break device creation.
* Confirm `num_acquire` exists, for decision 2(b).

### 5.2 `src/usaxs/plans/fx4_setup.py`
* `fx4_flyscan_mode(det, num_points, …, trigger_mode=…)`: write
  `"Ext. Trig."`, Polarity `Positive`, and `AveragingTime` = `FLYSCAN_AVERAGING_TIME`
  (new constant, ~1.0 s; must exceed the longest PSO interval and stay under
  `max_count_time(vpr)` = 20 s at VPR 10). Add `AcquireMode`/`NumAcquire` per
  decision 2. Keep the bulb branch selectable for rollback.
* New check `fx4_fast_gate_ready(dets)`: verifies firmware/driver on **every**
  box (the new trigger-counter PV connects; firmware ≥ 26.10.151957). It
  **raises** if the boxes disagree, and never silently mixes modes (§2.5).
* Rewrite the module and constant docstrings that explain the strobe/VPR
  coupling (`DEFAULT_FLYSCAN_VPR`).

### 5.3 `src/usaxs/plans/fly_scan_plan.py`
* Module docstring: "The FX4 cannot be hardware-triggered… bulb…" is now wrong.
* Replace `_check_strobe_width` with: strobe narrower than the shortest
  interval (trivial), and after the scan a warning if
  `max(channel_time) ≥ 0.9 × AveragingTime`. That would mean an interval was
  truncated, i.e. dead time crept back in and bin centres moved.
* Point accounting: `expected_pulses` becomes `NumPulses − 1` (or N, per
  decision 2). Compare **both** boxes' `TSCurrentPoint` and both trigger
  counters, not just UPD.
* Log the trigger counters and CPU % in the progress reporter, next to
  `NumAveraged` (which now varies per point by design, so it is no longer a
  health signal for merged exposures).
* Check that `bps.mv(det.acquire, 0)` on a box that already stopped itself
  (decision 2b) completes immediately, rather than hanging like the busy
  record (CLAUDE.md, "put_complete" rule).

### 5.4 Fly-scan HDF5 — `ADconfigs/Flyscan_config/saveFlyData.xml`
* Add `fx4_trigger_mode` (`usxFX4:FX4:TriggerMode`), `averaging_time`, both
  trigger counters, and a constant `point_alignment` string, e.g.
  `"rising_edge_i_to_i+1"`. Bump `config_version` 2.0 → 2.1 (decision 3).
* Redeploy to `/share1/AreaDetectorConfig/` (`ADconfigs/README.md`).

### 5.5 `src/usaxs/utils/count_time.py`
* `min_strobe_width_us` / `MIN_STROBE_SAMPLE_PERIODS`: keep them for bulb-mode
  rollback, but say in the docstring that they apply only to firmware older
  than 26.10.151957 and to bulb mode.

### 5.6 Tests (`tests/`)
* Offline: the mode-selection/refuse-mixed logic, the `expected_pulses`
  arithmetic, and the truncated-interval warning, against fake signals, in the
  style of the existing FX4 unit tests.

### 5.7 Queueserver
* Regenerate `src/usaxs/qserver/existing_plans_and_devices.yaml` (new device
  components).

## 6. Matilda changes (`/Users/ilavsky/GitHub/Matilda/matilda`)
* `_importFlyscanFX4`: read `flyScan/@fx4_trigger_mode` / `point_alignment`.
  Absent means today's bulb rule, which keeps old files bit-identical. In trig
  mode, apply the index offset measured in T3 and drop the junk last point if
  present (decision 2a).
* `TimeInSec` from `channel_time` is now a real varying dwell. Check that the
  smoothing code does not assume near-constant values.
* A regression test with one bulb file and one trig file of the same sample:
  reduced curves must overlay in Q.

## 7. Documentation to update with the code
* `CLAUDE.md` "Counting chain" (fly scan is `Ext. Trig.`; same-firmware rule).
* `docs/FX4_PSO_flyscan_setup.md`, `docs/FX4_config_cheatsheet.md`.
* `docs/FX4_PSO_trigger_issue_2.md`: mark resolved by R9-8 / firmware
  26.10.151957.
* `PLAN.md` §0 and §5.2: VPR = 5 test superseded.
* `SKILL.md` only if a user-visible plan signature changes (it should not).

## 8. Rollback
Bulb mode stays in the code behind a parameter, with 1200 µs and VPR 10. The
firmware and IOC can be rolled back per box. The HDF5 marker means files from
either mode reduce correctly.

## 9. Questions for the quadEM developer
1. We use NDStats `TSMeanValue` (via the Stats `TS:` child), not the quadEM
   `TS:` plugin. Is that what you meant, and is it unaffected?
2. In `Ext. Trig.`, does `Acquire = 0` emit the partial last point, or drop it?
3. In `Ext. bulb` on the new firmware, how is the gate *level* derived from
   the edge counter? Is bulb with Negative polarity still supported, and is
   the first LOW interval (before any edge) integrated?
4. For a long pulse (+1 at each edge), does `Ext. Trig.` count one trigger or
   two?
5. Can a second digital input be used as a gate on the same box (for the
   SAXS/WAXS I0 idea in §2.6)?
6. Is R9-8 tagged yet? We want both IOCs built from the same tag.

## 10. Effort estimate
| item | time |
|---|---|
| T0–T2 (usxFX42 only, can start Monday) | ½ day beamline |
| Code §5.1–5.7 (offline) | 1 day |
| usxFX4 upgrade + T3–T5 | ½ day beamline |
| Matilda §6 + T6 | ½–1 day |
