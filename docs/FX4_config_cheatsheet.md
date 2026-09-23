# FX4 quadEM — Configuration Cheat Sheet

Two operating configurations for the USAXS FX4 softIOC, switchable per bluesky plan.
Prefix here is **`usxFX4:FX4:`** (substitute if different). Companion reference:
`FX4_PSO_flyscan_setup.md` (full explanations; section numbers cited as §n).

> **Golden rules that apply to BOTH configs**
> - `ValuesPerRead` sets everything: `SampleTime = ValuesPerRead × 10 µs`, streamed rate = 100 kHz / VPR.
> - **Don't use VPR = 1** (overloads the link, drops samples/pulses — §10). Use **10–50**.
> - Enable the 4 current stats plugins or the Mean/TS PVs never update:
>   `caput usxFX4:FX4:Current{1,2,3,4}:EnableCallbacks Enable`
> - Keep the integration window an **integer number of mains cycles** (× 16.667 ms @ 60 Hz)
>   so 60 Hz pickup averages out (§12). 0.1/1/2/3 s are all integer cycles — good.
> - Samples per reading must stay **≤ RING_SIZE** (default 10000) or the average is biased (§7).

---

## CONFIG 1 — "Scaler mode": fixed-time counting (tuning, transmission, step USAXS)

Behaves like a counter: on each trigger it integrates for a fixed time and exposes the
average current per channel. Use for bluesky step plans (tuning ~0.1 s, transmission 1–3 s).

**How it works:** `AcquireMode = Single` + `TriggerMode = Free run`. Each `Acquire = 1`
integrates for `AveragingTime`, then `Acquire` returns to 0 (busy) and
`Current[1-4]:MeanValue_RBV` updates. bluesky triggers `Acquire`, waits on the busy record,
reads the Mean PVs.

### One-time setup

```bash
caput usxFX4:FX4:TriggerMode  "Free run"      # 0
caput usxFX4:FX4:AcquireMode  Single          # 2
caput usxFX4:FX4:ValuesPerRead 50             # 2 kHz; keeps ≤5 s counts within RING_SIZE
# stats plugins must be enabled AND block so Acquire stays busy until the mean is ready:
for ch in 1 2 3 4; do
  caput usxFX4:FX4:Current${ch}:EnableCallbacks Enable
  caput usxFX4:FX4:Current${ch}:CallbacksBlock  Yes
done
```

### Per-plan: set the count time

```bash
caput usxFX4:FX4:AveragingTime 0.1     # tuning
# caput usxFX4:FX4:AveragingTime 1.0   # transmission (1–3 s)
```

### Per-point (what the plan does at each step)

```bash
caput -w 10 usxFX4:FX4:Acquire 1       # -w waits for the busy record to finish
# then read the detector channel(s):
caget usxFX4:FX4:Current1:MeanValue_RBV      # e.g. I0
caget usxFX4:FX4:Current2:MeanValue_RBV      # e.g. I  (transmission = I/I0)
```

### Count-time → samples (must stay ≤ RING_SIZE = 10000)

`samples = count_time × 100000 / ValuesPerRead`

| Count time | VPR = 10 | **VPR = 50** | VPR = 100 |
|-----------|----------|--------------|-----------|
| 0.1 s | 1 000 | **200** | 100 |
| 1 s | 10 000 (at limit) | **2 000** | 1 000 |
| 3 s | 30 000 ❌ overflow | **6 000** ✅ | 3 000 |

→ **VPR = 50 covers 0.1–5 s** within the default 10000 ring. If you must use VPR = 10 for
long counts, raise `RING_SIZE` in `FX4.cmd` instead (§7).

**Readback choice:** `MeanValue_RBV` = average current over the count (what you normally
want; transmission = ratio of two Means). If you want a true scaler-like **integral**
(charge/counts ∝ mean × time), read `Current[1-4]:TSTotal` / `Total_RBV` instead.

**bluesky/ophyd:** this maps onto the standard ophyd `QuadEM` pattern — `stage()` sets
AcquireMode/AveragingTime, `trigger()` writes `Acquire` and waits on the busy record,
`read()` returns the `MeanValue_RBV` channels.

---

## CONFIG 2 — "Flyscan mode": PSO-gated, one average per pulse (800–8000 pts)

Each PSO strobe closes one exposure; the driver emits the average current over that interval
and appends it to a time-series array. Collect the arrays after the scan.

**How it works:** `TriggerMode = Ext. bulb` + `TriggerPolarity = Negative` (our idle-low /
strobe-high signal, §2). `AveragingTime` is IGNORED in bulb mode — the gate defines the
window. Each pulse = one point in the per-channel stats time series.

### One-time setup

```bash
caput usxFX4:FX4:TriggerMode     "Ext. bulb"   # 3
caput usxFX4:FX4:TriggerPolarity Negative       # 1  (low interval = exposure; §2)
caput usxFX4:FX4:AcquireMode     Continuous     # 0  (TS fixed-length stops collection)
caput usxFX4:FX4:ValuesPerRead   10             # 10 kHz; ~500 samples per 0.05 s interval
for ch in 1 2 3 4; do
  caput usxFX4:FX4:Current${ch}:EnableCallbacks Enable
done
```

Make sure `RING_SIZE` ≥ (longest interval × 100000 / VPR) so long exposures aren't clipped
(watch `usxFX4:FX4:RingOverflows`, §7).

### Per-scan: arm the time series, then acquire

```bash
# size + mode the per-channel time series (do all 4 channels):
for ch in 1 2 3 4; do
  caput usxFX4:FX4:Current${ch}:TSNumPoints   8000           # ≥ number of PSO pulses
  caput usxFX4:FX4:Current${ch}:TSAcquireMode "Fixed length" # stop at NumPoints
  caput usxFX4:FX4:Current${ch}:TSControl     "Erase/Start"  # arm (value 0)
done
caput usxFX4:FX4:Acquire 1        # start the electrometer, then run the motion/PSO
```

### After the scan: read the arrays

```bash
caget usxFX4:FX4:Current1:TSCurrentPoint       # how many pulses were captured
caget -# 8000 usxFX4:FX4:Current1:TSMeanValue  # per-pulse mean current  (your data)
caget -# 8000 usxFX4:FX4:Current1:TSSigma      # per-pulse std of samples (see below)
caget -# 8000 usxFX4:FX4:Current1:TSTotal      # per-pulse integral (scaler-like)
```

### Your questions, answered

- **Standard deviation as an array — yes.** It's the companion of your `TSMeanValue`:
  **`…:Current<n>:TSSigma`** (same prefix, `MeanValue`→`Sigma`). One value per pulse.
  ⚠️ **`TSSigma` is the standard deviation of the samples *within* each exposure** (signal
  spread during the count), **not** the standard error of the mean. If you want the
  uncertainty of each per-pulse mean, use **σ_mean = TSSigma / √N**, where
  `N = NumAveraged` for that pulse (≈ `TSTotal / TSMeanValue`). See §12.
- Also available per pulse (same prefix): `TSMinValue`, `TSMaxValue`, `TSTotal` (integral),
  `TSNet`. Control PVs: `TSControl` (Erase/Start · Start · Stop · Read), `TSNumPoints`,
  `TSCurrentPoint`, `TSAcquiring`, `TSAcquireMode`.

> **Exact PV name caveat:** depending on the ADCore version the stats-TS arrays are either
> `…:Current1:TSMeanValue` or `…:Current1:TS:TSMeanValue`. You already know your working
> `TSMeanValue` string — **the σ array is that exact same string with `MeanValue`→`Sigma`.**
> To list what your IOC actually has: `dbl "usxFX4:FX4:Current1:*" | grep -i ts`
> (or `caget usxFX4:FX4:Current1:TSMeanValue.NELM` to confirm length).

---

## CONFIG 2 add-on — Per-pulse exposure-time proxy (bulb-mode tuning diagnostic) ⭐

Purpose: **not for data reduction** (mean-diode / mean-I0 is the science) — this is a
**tuning health check**. Each bulb exposure = the stage's position-to-position interval, so
wildly oscillating per-pulse times flag poor stage tuning → retune.

**The proxy:** `exposure_time[i] = NumAveraged[i] × SampleTime`, where
`SampleTime = ValuesPerRead × 10 µs`. It's derived from the FX4's **hardware-timestamped**
gate edges (via the streamed sample count), so it's cleaner than any EPICS wall-clock time —
and it's a per-pulse *duration*, exactly what you want.

### ⚠️ `NumAveraged` is a live SCALAR, not a ready-made array

`NumAveraged_RBV` updates once per pulse (great for live monitoring) but there is **no
`TSNumAveraged` array PV**. To get it as an array aligned to your `TSMeanValue` points,
**derive it** from two arrays you already collect (because `Mean = Total / N`):

```
N[i]              = TSTotal[i] / TSMeanValue[i]           # exact sample count per pulse
exposure_time[i]  = N[i] × SampleTime                     # seconds, per pulse
```

Use the **I0 channel** for this (always well-illuminated → mean safely non-zero, division
robust). Units/scale cancel in the ratio, so it's independent of `CurrentScale`.

### Live tuning check (zero setup)

```bash
camonitor usxFX4:FX4:NumAveraged_RBV       # one value per pulse; × SampleTime = seconds
```

Tight cluster → well tuned; scattered/oscillating counts → retune. Quick metric: track the
spread (min/max or std/mean) across the train; a rising coefficient of variation = retune flag.

### Post-scan array (per-pulse duration vs. point number)

```python
# after a flyscan, using the collected arrays (I0 = the well-lit channel):
import numpy as np
sample_time = vpr * 10e-6                    # ValuesPerRead × 10 µs
N   = TSTotal_I0 / TSMeanValue_I0            # exact samples per pulse (array)
dt  = N * sample_time                        # per-pulse exposure time [s] (array)
cov = dt.std() / dt.mean()                   # tuning-jitter metric; watch this per scan
```

Resolution = one `SampleTime` (100 µs at VPR=10 → ~0.2 % on a 50 ms interval; plenty).
For finer resolution lower VPR, but respect the throughput limit (§10).

> If your ADCore build happens to expose a per-point `TSTimestamp` array
> (`dbl "usxFX4:FX4:Current1:*" | grep -i timestamp`), `diff(TSTimestamp)` gives pulse
> *spacing* directly — but it carries driver/software latency, so the `N×SampleTime` proxy
> above (hardware-edge-derived) is the more trustworthy jitter indicator.

---

## Q3 — the "Time" PV (`usxFX4:FX4:FX4_TS` / TS time axis): can it give per-pulse length?

**No — not directly.** The time-series "time axis" is a **synthetic, uniform** axis:
`index × TimePerPoint`, with `TimePerPoint` hard-linked to `SampleTime_RBV`. It assumes every
point spans the same wall-clock time. In **bulb mode the exposures are NOT uniform in time**,
so that axis does **not** represent per-pulse length. (`FX4_TS` isn't a standard quadEM
record name; on your IOC it's almost certainly this TS time axis or a beamline-local record —
confirm with `caget usxFX4:FX4:FX4_TS.NELM` and `.EGU`.) Use the `N×SampleTime` proxy above
instead.

---

## Switch-between-configs quick reference

| PV | Config 1 (scaler) | Config 2 (flyscan) |
|----|-------------------|--------------------|
| `TriggerMode` | `Free run` (0) | `Ext. bulb` (3) |
| `TriggerPolarity` | n/a | `Negative` (1) |
| `AcquireMode` | `Single` (2) | `Continuous` (0) |
| `AveragingTime` | count time (0.1 / 1–3 s) | *ignored* |
| `ValuesPerRead` | 50 | 10 |
| `Current*:CallbacksBlock` | `Yes` | `No` (default) |
| Per-cycle action | trigger `Acquire`, read `…:MeanValue_RBV` | arm `…:TSControl`, `Acquire 1`, read `…:TSMeanValue`/`TSSigma` |
| Data PV(s) | `Current[1-4]:MeanValue_RBV` (scalar) | `Current[1-4]:TSMeanValue` (+`TSSigma`,`TSTotal`) arrays |
| Exposure-time diagnostic | n/a (fixed time) | `NumAveraged_RBV` live; `(TSTotal/TSMeanValue)×SampleTime` array |

Common to both: `Current[1-4]:EnableCallbacks Enable`; VPR ≠ 1; window = integer × 16.667 ms;
samples/reading ≤ RING_SIZE.
