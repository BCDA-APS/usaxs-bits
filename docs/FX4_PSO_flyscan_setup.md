# FX4 Electrometer — Position-Triggered (PSO) Fly-Scan Setup

Notes on configuring a **Pyramid Technical Consultants FX4** quad electrometer
(via the EPICS [`epics-modules/quadEM`](https://github.com/epics-modules/quadEM) module)
to record the **average signal over each exposure of a fly-scan**, where exposures are
bounded by Aerotech **PSO** (Position Synchronized Output) pulses arriving at irregular
time intervals (≤ 8000 per scan). Also covers step-scan (fixed-time) use and measurement
uncertainty.

> **TL;DR** — The FX4 ADC cannot be hardware-triggered, but the quadEM driver does the
> gating in software from the FX4's timestamped digital-input stream. Feed the PSO gate
> into FX4 digital input **D1** (= `gpio_0/22`, **50 Ω-terminated**), set D1 to **GP Input**,
> run in **Ext. bulb** trigger mode with **TriggerPolarity = Negative** (our signal idles
> low, strobes high), and watch the per-exposure averages with `camonitor`.
> Use **ValuesPerRead ≈ 10–50**, *not* 1 (see §10 — low VPR overloads the link and drops pulses).

---

## 1. Key concept — the FX4 can't be triggered, but quadEM gates in software

- The FX4 digitizes all 4 channels **continuously at 100 kHz** and cannot gate/trigger
  its own ADC acquisition.
- **However**, the quadEM `drvFX4` driver connects to the FX4 over **WebSocket** and
  subscribes to the 4 ADC channels **plus one digital-input ("gate") signal**. Every ADC
  sample and every gate transition carries a **precise hardware timestamp**.
- The driver performs the triggering/gating/averaging **in software on the IOC** using
  those timestamps. Because the bin edges come from the FX4's hardware clock (not IOC
  scheduling), there is **no software-latency jitter** on the exposure boundaries.
- **Consequence:** No extra "PSO → EPICS" conversion hardware or custom IOC binning is
  needed. Just get the PSO gate into the correct FX4 digital input.

---

## 2. Trigger mode — use "Ext. bulb"

`Ext. bulb` = level-sensitive gate. Samples are integrated **while the gate is at the
active level**; on the closing edge the plugins are called and the **average over all
samples in the exposure** is emitted. This is the correct choice for a fly-scan where
intensity varies *during* the count and exposures have different durations.

Confirmed from the driver source (`drvFX4.cpp`): in bulb mode `NumAverage` is forced to
**0** and **`AveragingTime` is ignored** — the averaging window is defined purely by the
gate.

### ⚠️ TriggerPolarity = logic sense, NOT voltage sign

"Polarity" here selects **which logic level is the active/integrating level and which edge
reads out** — it has nothing to do with the voltage going below ground. The signal stays a
normal 0 V → +2.5 V TTL.

| TriggerPolarity | Active (integrating) level | Reads out on | Exposure = |
|-----------------|----------------------------|--------------|------------|
| **Positive** | HIGH | falling edge | the HIGH period |
| **Negative** | LOW  | rising edge  | the LOW period |

**For this system → use `Negative`.** Our PRL/PSO signal **idles LOW (~0 V) and strobes
HIGH** at each position, so the measurement windows (the intervals *between* position
pulses) are the **LOW** periods:

- **Negative** integrates the LOW intervals and emits one average on each **rising edge**
  (each PSO strobe) → exactly one value per position crossing. ✅
- **Positive** would integrate only the brief HIGH strobe (a few µs, often < 1 sample) →
  captures essentially nothing → "doesn't work at all." (This is expected, not a fault.)

Each average therefore covers from the end of one strobe to the start (rising edge) of the
next; the short HIGH strobe is dead time. *(If you ever wanted the HIGH level to be the
exposure, invert the signal to idle-high and use Positive — not needed here.)*

### Trigger-mode menu values (from `FX4.template`)

| Menu label   | Value |
|--------------|-------|
| Free run     | 0     |
| Ext. trig.   | 2     |
| **Ext. bulb**| **3** |
| Ext. gate    | 4     |

The `Ext. bulb` choice only appears in the `TriggerMode` menu when the IOC has loaded
`FX4.template`. If your MEDM/Phoebus screen doesn't show it, you're on a generic/TetrAMM
screen — set the PV directly instead:

```bash
caput QE1:FX4:TriggerMode 3          # or: caput QE1:FX4:TriggerMode "Ext. bulb"
caput QE1:FX4:TriggerPolarity 1      # 0=Positive, 1=Negative
caget -d 31 QE1:FX4:TriggerMode      # prints the enum strings to confirm
```

(`QE1:FX4:` is the stock example prefix from `FX4.cmd` — substitute yours,
e.g. `usxFX4:FX4:`.)

---

## 3. Where the PSO signal physically connects

The FX4 digital inputs are **not BNC**. They are:

- **D1–D4**: four **3.3 V logic** lines on the rear-panel **DB9 (female) expansion connector**.
  DB9 pinout: `1=D1, 2=D2, 3=D3, 4=D4, 5=+5 V out, 6=I²C SCL, 7=I²C SDA, 8=+3.3 V out, 9=GND, shell=GND`.
- **Fiber-optic receivers**: three ST-bayonet receivers (HFBR-2515).

### ⚠️ The input is hard-coded in the driver

`drvFX4.h` fixes the gate signal to:

```
GATE_PATH = "/fx4/gpio_0/22/readback/value"
```

Only the physical connector that maps to **`gpio_0/22`** will work (without recompiling).
The manuals expose friendly aliases (`/fx4/digital_expansion/d1…d4`, `/fx4/fr1…fr3`) but
**do not publish the raw `gpio_0/22` mapping**, so it was identified via the web GUI.

> **✅ CONFIRMED (this device, IP 10.54.122.170):** In the web UI, **D1** shows as
> `http://10.54.122.170/io/fx4/gpio_0/22/readback/value.json` — i.e. **D1 = `gpio_0/22`**,
> which is exactly the driver's hard-coded gate.
> **→ Wire the PSO gate to D1 (DB9 pin 1), ground on pin 9.**

How it was found (for reference / other devices): in the FX4 web GUI, right-click a
digital's readback field → **"Copy HTTP URL"**, and match the one whose path is
`.../fx4/gpio_0/22/...`.

### ⚡ Signal levels & 50 Ω termination (PRL-414B → D1) — IMPORTANT

Source here is a **Pulse Research Lab PRL-414B** 1:4 **50 Ω back-terminated** TTL line
driver (2 ns edges). Its output HIGH depends entirely on the load:

| Load at D1 | Output HIGH (VoH) | Verdict for 3.3 V D1 |
|-----------|-------------------|----------------------|
| **50 Ω terminated** | **2.2–2.5 V** (VoH1) | ✅ valid HIGH (> ~2.0 V threshold), safely < 3.3 V |
| **Unterminated / high-Z** | **4.4–5 V** (VoH2) | ❌ over-drives a 3.3 V, non-5 V-tolerant input |

D1 is a **high-impedance 3.3 V CMOS GPIO**, so a *direct* connection puts you in the
4.4–5 V row → over the pin's absolute max (clamps through ESD diodes → possible damage +
erratic behavior) **and** the unterminated fast-edge line **rings/reflects → double or
missed triggering**.

**Fix — put a BNC 50 Ω feed-through terminator at the D1 end** (right where the cable meets
the BNC→DB9 adapter; signal to pin 1, ground to pin 9). This simultaneously drops the level
to the safe **2.2–2.5 V** spec and **matches the line**, killing reflections/ringing.

Checks: with a scope confirm HIGH ≈ 2.5 V at D1 (VoH1 min 2.2 V vs ~2.0 V threshold is only
~0.2 V margin; typ 2.5 V is fine). The weak D1 pull-down (kΩ) is negligible vs 50 Ω. The
**-C003** PRL variant delivers 5 V into 50 Ω if more margin is ever needed.

### Wiring cautions (general)

- **DB9 route (D1):** D1–D4 are **3.3 V logic**, **not 5 V tolerant**. Never feed the
  unterminated ~5 V PRL output (or any 5 V TTL) straight in — terminate/level-shift first.
- **Fiber route:** would use Pyramid's **TF15** or **X224** BNC-TTL→fiber converter into a
  fiber receiver — but the driver gate is D1, so the fiber receivers are **not** the gate
  input here.

---

## 4. FX4-side configuration — D1 mode

In the web GUI Digital IO screen, set **D1's mode = GP Input**, then set the options below.

**GP Input vs Process Input** — use **GP Input**:

- **GP Input** (general-purpose input): D1 is a plain digital input, and its electrical
  state is exposed directly as `/fx4/gpio_0/22/readback/value` — exactly the PV the
  `drvFX4` driver subscribes to for the gate. **This is what you want.**
- **Process Input**: binds D1 into the FX4's **process-control / dose-controller**
  subsystem and assigns it a named "process signal." Meant for dosimetry/interlock logic,
  not for reporting the raw pin state. Don't use it here.

Recommended D1 options:

- **Pull mode → Pull Down** — idle/disconnected input reads low (clean gate-low baseline).
- **De-bounce → Off** — de-bounce adds ~1 µs delay before the state is reported. Since the
  gate edges are hardware-timestamped to define exposure boundaries, leaving de-bounce off
  preserves timing fidelity. Enable only if you see spurious edges from a noisy signal.

Set `TriggerPolarity = Negative` to match our idle-low / strobe-high signal (see §2). The
driver auto-subscribes to D1 once acquisition starts.

> Note: the FX4 web GUI's own "Start Trigger" feature is a *current-threshold* trigger and
> is **unrelated** to the digital-input gating used here — don't confuse the two.

---

## 5. How the controls work — the pipeline model (READ THIS FIRST)

Everything on the Quad Electrometer screen makes sense once you see the data pipeline:

```
FX4 ADC (fixed 100 kHz per channel)
   │   ── averages ValuesPerRead conversions ON THE DEVICE ──
   ▼
Streamed samples, one every  SampleTime = ValuesPerRead × 10 µs
(streamed rate = 100 kHz / ValuesPerRead, over WebSocket, hardware-timestamped)
   │
   ▼
Driver ring buffer  (size = RING_SIZE, §7)
   │   ── accumulate until one "reading" is complete, then NDArray callback ──
   │      how many samples per reading = decided by the trigger/averaging mode
   ▼
NDPluginStats  →  Current[1-4]:MeanValue_RBV   ← the number you actually record
```

Two independent things hang off the stream:

- **Main acquisition/averaging path** (ring buffer → callback → stats) — *your data*.
- **Parallel "fast averaging" path** (`...Ave` PVs) — smoothed live readbacks for the GUI
  only; **does not affect acquired data**.

### Field-by-field glossary

**Sampling rate**

- **Values per reading (`ValuesPerRead`)** — # of the 100 kHz ADC conversions the FX4
  averages into each streamed sample. Sets `SampleTime = ValuesPerRead × 10 µs` and the
  **streamed data rate = 100 kHz / ValuesPerRead**. Master knob for granularity *and* data
  volume. VPR=1 → 10 µs @ 100 kHz (firehose); VPR=10 → 100 µs @ 10 kHz. **See §10.**
- **`SampleTime_RBV`** — readback of the above; the unit everything else is measured in.

**Main averaging / acquisition**

- **Averaging time (`AveragingTime`)** — time window accumulated into **one** averaged
  reading, in the modes that use it. `#To average = round(AveragingTime / SampleTime)`.
  Free-run → new reading every AveragingTime; Ext. trig → samples taken per trigger.
  **Ext. bulb → IGNORED** (window = the gate). *(So the 0.01 s I set in bulb mode did
  nothing — that was my misunderstanding.)*
- **#To average (`NumAverage_RBV`)** — the *intended* sample count = round(AveragingTime/
  SampleTime). **Forced to 0 in bulb mode** ("not fixed — set by the gate").
- **#Averaged (`NumAveraged_RBV`)** — the *actual* sample count in the last reading.
  Free-run = NumAverage; bulb/gated = varies per gate width (your per-exposure sample
  count). Capped at RING_SIZE (§7).
- **Acquire mode (`AcquireMode`)** — *Continuous* (free-run until stopped), *Multiple*
  (take NumAcquire readings then auto-stop), *Single* (= Multiple w/ NumAcquire=1; use for
  step scans).
- **Acquire (`Acquire`)** — start/stop (busy record). In Single mode the scan record pushes
  this at each point and waits.
- **#Acquisitions (`NumAcquire`)** — in Multiple mode, # readings before auto-stop.
- **#Acquisitions done (`NumAcquired`)** — counter since Acquire→1.
- **Read data button (`ReadData`)** — only when AveragingTime=0 (manual mode): flushes the
  ring buffer into one reading (everything since the last flush). The "read on demand" hook
  for externally-paced scans.

**Fast averaging (live-display path — ignore for data collection)**

- **Fast averaging time (`FastAveragingTime`)** — # of recent samples to average for the
  smoothed `Current[1-4]Ave` readbacks: `#To avg fast = round(FastAveragingTime/SampleTime)`.
- **#To average fast (`NumFastAverage`)** — the resulting count.
- **Fast averaging scan (`FastAverageScan.SCAN`)** — how *often* those smoothed readbacks
  update (".1 second", "1 second", …). Purely a display cadence.
- These feed a meter/monitor (and the legacy feedback path); they do **not** touch acquired means.

**Others**

- **Range** — gain/sensitivity (100 nA…10 mA, slow/fast).
- **Geometry** — only defines how the 4 diodes combine into SumX/Y, DiffX/Y, Position X/Y
  for a quadrant/beam-position detector. **No effect on raw Current1–4.** Irrelevant when
  using a single channel or only individual currents. ✅ (your instinct was right)

---

## 6. Monitoring for a quick test — `camonitor`

The per-exposure average lands on the **NDPluginStats mean** PVs, updating **once per gate**.

**First enable the stats plugins** (they boot disabled):

```bash
caput QE1:FX4:Current1:EnableCallbacks Enable
caput QE1:FX4:Current2:EnableCallbacks Enable
caput QE1:FX4:Current3:EnableCallbacks Enable
caput QE1:FX4:Current4:EnableCallbacks Enable
```

**Test sequence (bulb / PSO):**

```bash
caput QE1:FX4:TriggerMode "Ext. bulb"
caput QE1:FX4:TriggerPolarity Negative  # idle-low / strobe-high signal
caput QE1:FX4:AcquireMode Continuous
caput QE1:FX4:ValuesPerRead 10          # 100 kHz / 10 = 10 kHz — NOT 1 (see §10)
caput QE1:FX4:Acquire 1

camonitor QE1:FX4:Current1:MeanValue_RBV QE1:FX4:Current2:MeanValue_RBV \
          QE1:FX4:Current3:MeanValue_RBV QE1:FX4:Current4:MeanValue_RBV \
          QE1:FX4:NumAveraged_RBV
```

- Each PSO strobe prints one line per PV: `PVname  date  time  value`.
- **`NumAveraged_RBV`** is the key sanity check — samples per exposure; should track your
  varying interval lengths and confirm gating is real.
- Inspectable table (any text/spreadsheet tool): `camonitor … > bulbtest.dat`.

---

## 7. Maximum averaged samples per exposure — the ring buffer (`RING_SIZE`)

**Symptom:** `NumAveraged_RBV` pegs at **10000** on longer exposures.

That 10000 is the **ring buffer size**, not an averaging setting — hitting it means samples
are **dropped**, so those long-exposure averages are **biased** (only the tail counted).

**What controls it:** the `ringBufferSize` argument to `drvFX4Configure` in `FX4.cmd`:

```
epicsEnvSet("RING_SIZE", "10000")
drvFX4Configure("$(PORT)", "$(IP)", $(RING_SIZE))
```

In bulb mode the driver averages everything in the ring buffer at the closing edge, so
`NumAveraged_RBV ≤ RING_SIZE`. Overflow discards the **oldest** samples and increments
`QE1:FX4:RingOverflows`.

> **Check `QE1:FX4:RingOverflows`** — non-zero ⇒ samples dropped, mean biased.

**Samples per exposure** = `exposure_time / SampleTime`, `SampleTime = ValuesPerRead × 10 µs`.
At VPR=5 → 20 kHz → 10000 samples = **0.5 s**; longer exposures peg.

**Fixes (combine):** (1) increase `RING_SIZE` above worst-case
(`longest_exposure × 100000 / ValuesPerRead`) + margin, restart IOC (memory is not a
concern); (2) increase `ValuesPerRead` to lower the sample count. Confirm `RingOverflows`
stays 0 afterward.

---

## 8. Minimum strobe/gap width — resolving separate exposures

**Symptom:** looks like **missed PSO pulses** — consecutive exposures merging into one.

The gate state is resolved at the **FX4 sample cadence** (`SampleTime = ValuesPerRead ×
10 µs`). To register two separate bulb events the driver must *see* both edges of the
delimiter in the streamed samples; if the delimiter is shorter than the sampling resolves,
neighboring samples read the same level and two exposures fuse.

**With `TriggerPolarity = Negative` (our case) the delimiter is the HIGH strobe** (the low
interval is the exposure). So the **PSO HIGH pulse width** must clear the cadence:

- Absolute floor ≥ 1 sample period; **safe ≥ 3–5 sample periods**.
- At VPR=5 (50 µs/sample): floor ≈ 50 µs, safe strobe ≈ **200–300 µs**.
- (With Positive polarity the roles swap → the LOW gap must clear the cadence.)

> **Two competing effects — see §10.** Shorter SampleTime (low VPR) resolves *narrower*
> delimiters, BUT low VPR also raises the data rate and can drop samples/edges. Pick VPR to
> satisfy both: fine enough to resolve the delimiter, coarse enough not to overload the link.

Confirm merging vs. dropping: a merged exposure shows ~2× the normal `NumAveraged_RBV` and
fewer events than pulses. Enable `asynSetTraceMask("FX4",0,0x9)` to log gate events.

---

## 9. Networking — split subnet requires a Gateway on the FX4

Device and ioc must be on the sam subnet, then it works fine.

---

## 10. ValuesPerRead: throughput vs. resolution — why LOW VPR *drops* pulses ⭐

**Observed:** 2000-pulse train, fastest interval ~0.05 s.
- `ValuesPerRead = 1` → only **1156** pulses captured (~42% missed).
- `ValuesPerRead = 10` → **all 2000** captured, nothing else changed.

**Why (counter-intuitive):** this is a **data-throughput** effect, opposite in direction to
the edge-resolution rule of §8.

- The FX4 streams **every** sample over WebSocket continuously, regardless of gating.
  At **VPR=1** that's **100 kHz × 4 channels** (+ gate) — the raw firehose. The driver
  drains it in a poll loop, msgpack-decoding everything. When the sustained rate exceeds
  what the FX4 → WebSocket → driver pipeline can carry, **samples are dropped in transit —
  including gate transitions.** A lost edge = a lost exposure. 1156/2000 ≈ 58% survived.
- At **VPR=10** the streamed rate is **10× lower (10 kHz)**; the pipeline keeps up, no
  drops, all 2000 edges survive.

So here **higher ValuesPerRead is more reliable** — the bottleneck is bandwidth, not time
resolution.

| Lower ValuesPerRead | Higher ValuesPerRead |
|---|---|
| finer edge/time resolution (shorter SampleTime) | coarser time resolution |
| **much higher data rate → dropped samples/edges** | **low data rate → reliable** |

**Practical rule:** pick the **largest** ValuesPerRead whose SampleTime still finely
oversamples your signal. For 0.05 s minimum intervals, VPR=10 (100 µs → ~500 samples per
shortest interval) or even VPR=50 (2 kHz → ~100 samples) is plenty and rock-solid.
**Avoid VPR=1** unless you truly need 10 µs granularity and have verified the link sustains it.

**Confirm the mechanism:** at VPR=1, enable `asynSetTraceMask("FX4",0,0x9)` → expect the
driver's *"not synchronized / different number of samples per channel"* warnings (its symptom
of torn/dropped stream data); also watch `RingOverflows`.

---

## 11. Step-scan — fixed-time exposures

Fixed dwell per point leaves bulb mode behind. Two standard patterns (quadEM scanning docs):

1. **Free-run + read on the fly (simplest, fastest):** `AcquireMode=Continuous`,
   `TriggerMode=Free run`, set `AveragingTime` slightly less than the per-point dwell, and
   read `Current[1-4]:MeanValue_RBV` as the detector at each step. The quadEM never stops;
   each point picks up the most recent AveragingTime average. Tiny asynchrony vs. motor
   settle, usually negligible.

2. **Single-acquire per point (clean, position-guaranteed):** `AcquireMode=Single`,
   `AveragingTime = exposure`. The scan record triggers the **Acquire** PV at each settled
   position; the FX4 integrates exactly `NumAverage_RBV = AveragingTime/SampleTime` samples,
   then MeanValue updates. Guarantees you only count at the target position. **Requires the
   stats plugins to have `CallbacksBlock=Yes`** so Acquire stays "busy" until the mean is
   computed.

For well-defined fixed exposures use **#2**. Set `AveragingTime` = exposure; choose
`ValuesPerRead` so SampleTime is well under the exposure (hundreds–thousands of samples per
point) but high enough to respect the §10 throughput limit (VPR≈10 is a good default).
**Line-noise tip (see §12):** make `AveragingTime` an integer number of mains cycles
(multiples of 16.667 ms @ 60 Hz) so 60 Hz pickup averages out.

---

## 12. Measurement uncertainty — photocurrent → photon flux 🎯

Two distinct questions, and they must be separated (conflating them is what breeds fudge
factors):
(a) **How well does the FX4 measure the current?** — usually the *small* term.
(b) **How well does that current give photon flux?** — the detector physics; usually
**dominant**, and where the old "kludge formula" really lives.

### Measurement model (write it down → propagation falls out)

Semiconductor detector (photodiode/diamond), monochromatic beam:

```
I = Φ · (E / w) · e · η(E)        ⇒        Φ = I · w / (E · e · η(E))
```

- Φ = photon flux (ph/s), I = photocurrent, E = photon energy, e = elementary charge
- w = mean energy per e–h pair: Si ≈ 3.66 eV, diamond ≈ 13 eV, Ge ≈ 2.96 eV
- η(E) = fraction of incident photons depositing energy in the active volume
  = (1 − e^(−μ_active·t_active)) × (window/dead-layer transmission)
- Ion chamber: same shape with W_gas (≈ 30–35 eV) and the gas absorbed fraction.

Everything is a product/quotient of first powers ⇒ **relative** uncertainties add in
quadrature:

```
(u_Φ/Φ)² = (u_I/I)² + (u_w/w)² + (c_E · u_E/E)² + (u_η/η)²
```

(c_E = sensitivity of η to E; large near an absorption edge.)

### Part 1 — FX4 current, u_I/I (GUM Type A = statistical, Type B = systematic)

| Contribution | Type | How to get it |
|---|---|---|
| Gain / scale accuracy per range | B | FX4 factory **calibration data** shipped with unit; verify vs. calibrated source (Keithley 6221) |
| Linearity within/across ranges | B | inject known currents; check range-overlap agreement |
| Zero offset / dark / leakage | B | measure beam-off, subtract (`CurrentOffset`); residual scatter = uncertainty (dominates at low I) |
| Random noise | A | datasheet **rms-noise-vs-averaging-time table per range**, or live `Current:Sigma_RBV`/√N |
| Bandwidth / settling vs. signal | B | range-dependent (100 nA range = only 1 kHz!); a too-slow range biases a fast fly-scan average |
| Temperature drift (gain & offset) | B | run 15–25 °C (datasheet); bound from drift over a run |
| Bias-voltage stability | B | affects collection efficiency for biased detectors |

Net: a well-set-up FX4 reading is typically **~0.1–1 %** (scale is factory-calibrated,
sub-%; noise is what your averaging controls).

### Part 2 — current → flux (usually dominant)

- **η(E) — the big one.** Needs active thickness + attenuation μ(E) from **NIST XCOM /
  FFAST**. Few-% in general, **much worse near absorption edges** and for thin diodes at
  high E (small η → large relative error). Dead layers / windows add more.
- **Energy, bandwidth, and HARMONICS.** Monochromator harmonic contamination (esp. 3rd)
  is a classic silent systematic — can be several %.
- **w (or W_gas):** known < 1 %, weak E-dependence — small term.
- **Charge-collection efficiency / recombination** (bias- & flux-dependent), geometry,
  fluorescence/photoelectron escape.

### Part 3 — fundamental floor

Photon shot noise: relative uncertainty = 1/√(Φτ) for Φ photons in time τ. Tiny at
synchrotron flux, but it's the floor to compare electronic noise against.

### ⚠️ Two subtleties that bite (and tie to our setup)

1. **Averaging reduces noise as 1/√N only for WHITE noise.** The quadEM streaming-doc FFT
   was dominated by **60 Hz + harmonics** (mains pickup), which is *not* white. Make the
   integration window (bulb exposure or step `AveragingTime`) an **integer number of mains
   cycles — multiples of 16.667 ms @ 60 Hz** — or the 60 Hz residual dominates repeatability
   and no amount of N helps. (Likely a big part of what the old empirical formula absorbed.)
2. **Empirical repeatability > per-sample σ.** Honest Type A = repeat the *same*
   measurement M times, take the std of the means. Captures slow drift + correlated noise
   that `Sigma_RBV/√N` misses.

### ✅ Practical recommendation — collapse the physics into one traceable factor

Cross-calibrate the working detector against a **calibrated reference photodiode**
(PTB/NIST-traceable) at the **actual operating energy**. That yields one measured factor
`F` [ph/s per amp] whose single uncertainty already contains w, η, geometry, and (if done
at the working energy) harmonic effects:

```
Φ = F · I_FX4 ,     (u_Φ/Φ)² = (u_F/F)² + (u_I/I)²_FX4
```

Now the budget is just "calibration factor" ⊕ "FX4 reading" — both quantifiable and
re-checkable. Report expanded uncertainty **U = k·u_c, k = 2 (~95 %)**.

### Reframing the old kludge

The "semi-random formula backed by repeated measurements" is an empirical calibration that
lumps Type A repeatability with an unseparated systematic. It "mostly matches" because the
repeatability part is genuinely good. The upgrade: (a) separate statistical from
systematic, (b) get `F` from a traceable reference, (c) fix the 60 Hz averaging-window
issue, (d) write the budget down so the number is defensible rather than folklore.

**Rough priority (where the uncertainty actually lives):**
harmonics + η(E) near edges ≫ detector calibration ≈ energy ≫ FX4 scale > FX4 noise
(if line-locked) ≫ shot noise.

---

## Quick reference — key PVs (stock prefix `QE1:FX4:`, ours `usxFX4:FX4:`)

| PV | Purpose |
|----|---------|
| `TriggerMode` | 0=Free run, 2=Ext. trig., **3=Ext. bulb**, 4=Ext. gate |
| `TriggerPolarity` | **Logic sense, not voltage.** Positive = integrate while HIGH (read out on falling); **Negative = integrate while LOW (read out on rising) ← ours** |
| `AcquireMode` | Continuous / Multiple / Single (Single for step scans) |
| `Acquire` | Start(1)/Stop(0); per-point trigger in Single mode |
| `NumAcquire` / `NumAcquired` | Multiple-mode target count / completed count |
| `ValuesPerRead` | On-device pre-averaging. `SampleTime = VPR×10 µs`; rate = 100 kHz/VPR. **Use ~10–50, not 1** |
| `AveragingTime` | Window per reading (free-run/Ext.trig). **Ignored in Ext. bulb.** Set = integer × 16.667 ms to null 60 Hz |
| `NumAverage_RBV` | Intended #samples/reading = round(AvgTime/SampleTime); **0 in bulb** |
| `NumAveraged_RBV` | Actual #samples in last reading (per-exposure count; caps at RING_SIZE) |
| `ReadData` | Manual flush of ring buffer (when AveragingTime=0) |
| `Current[1-4]:Sigma_RBV` | Per-reading std of samples → Type A noise input (u ≈ Sigma/√N, white-noise only) |
| `FastAveragingTime` / `NumFastAverage` | # samples for smoothed `…Ave` display readbacks |
| `FastAverageScan.SCAN` | Update cadence of the `…Ave` display readbacks |
| `RingOverflows` | Non-zero ⇒ ring buffer overflowed, samples dropped, mean biased |
| `Current[1-4]:MeanValue_RBV` | **Per-exposure / per-point average current** (NDPluginStats) |
| `Current[1-4]Ave` | Smoothed live readback (fast-averaging path; not the acquired data) |
| `Current[1-4]:EnableCallbacks` | Must be Enable for the mean PVs to update |
| `Geometry` | Diode→Sum/Diff/Position mapping only; no effect on raw currents |

**Startup / hardware facts (this device):**

- Driver gate signal (hard-coded): `/fx4/gpio_0/22/readback/value` = **D1** (DB9 pin 1, GND pin 9)
- **Signal source: PRL-414B (50 Ω TTL line driver) → must 50 Ω-terminate at D1** (else ~5 V + ringing)
- Polarity: **Negative** (idle low, strobe high; low interval = exposure)
- **ValuesPerRead ≈ 10–50** — low VPR (esp. 1) overloads the link and drops pulses (§10)
- `RING_SIZE` (max samples averaged per exposure) set in `FX4.cmd` via `drvFX4Configure`
- Device IP `10.54.122.170` — **Gateway `10.54.122.1`** required for split-subnet access
- `SampleTime = ValuesPerRead × 10 µs`; sets samples/exposure, min resolvable delimiter, and data rate
- FX4: 4 parallel I-V converters+ADCs, 6 ranges 0.02 nA–10 mA, ships with per-unit calibration data;
  per-range rms-noise-vs-averaging table is in the datasheet/cal sheet (pull the actual numbers there)

---

## Sources

- quadEM driver source — [`quadEMApp/FX4Src/`](https://github.com/epics-modules/quadEM/tree/master/quadEMApp/FX4Src) (`drvFX4.cpp`, `drvFX4.h`)
- quadEM database — [`FX4.template`](https://github.com/epics-modules/quadEM/blob/master/quadEMApp/Db/FX4.template), [`quadEM.template`](https://github.com/epics-modules/quadEM/blob/master/quadEMApp/Db/quadEM.template)
- quadEM docs — [Acquisition Modes](https://epics-modules.github.io/quadEM/tetramm_modes.html), [Scanning](https://epics-modules.github.io/quadEM/tetramm_scanning.html), [Streaming to disk](https://epics-modules.github.io/quadEM/streaming.html), [Setup](https://epics-modules.github.io/quadEM/setup.html)
- FX4 [Datasheet](https://assets.ctfassets.net/5vxgrhuzunkj/3XaO452MOazhFKPj7BvBCv/5d98bb8c411d783f2cce02f793d6eafd/FX4_DS_250331.pdf) · [Programmer Manual v3](https://assets.ctfassets.net/5vxgrhuzunkj/4apUnt4g5Y2yKq9b2zt2YE/08f56643a7f14970570e1195649b8da3/FX4_Programmer_Manual__v3_.pdf) · [User Manual v1](https://assets.ctfassets.net/5vxgrhuzunkj/2ubABwl3gdzxIIgVgQVgjT/2f06a817d70e59fd5275f8f51a71b804/FX4_User_Manual__v1_.pdf) · [product page](https://ptcusa.com/products/fx4)
- Signal source — [PRL-414B datasheet (APS mirror)](https://www.aps.anl.gov/files/APS-Uploads/DET/Detector-Pool/Electronics/PulseResearchLab_Electronics/PRL_TTL_LineDriver_414B.pdf) · [PRL-414B product page](https://www.pulseresearchlab.com/products/prl-414b)
- Metrology — GUM (JCGM 100:2008, *Guide to the Expression of Uncertainty in Measurement*); attenuation data: NIST [XCOM](https://physics.nist.gov/PhysRefData/Xcom/html/xcom1.html) / FFAST
