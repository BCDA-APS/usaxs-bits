# FX4 digital-input (gate) timing — narrow external trigger pulses are missed

**Status:** open — two separate issues, two owners:
(1) **missed pulses** → device firmware → Pyramid Technical Consultants (§9A);
(2) **per-interval sample-count corruption** → likely `drvFX4` driver → softIOC
developer / quadEM maintainer (§9B). See the analysis in §5.2–5.3.
**Site:** Advanced Photon Source, beamline 12-ID-E (USAXS instrument), Argonne National Laboratory.
**Date of measurements:** 2026-09-27.
**Workaround in place:** widen the external trigger pulse to 1200 µs (see §8).

This document is self-contained. It describes an externally-gated measurement
with an FX4 quad electrometer in which short trigger pulses are detected only
part of the time, quantifies the effect, states what has been excluded, and ends
with the specific questions we would like answered (§9). Nothing here depends on
knowledge of the beamline.

---

## 1. Summary

The FX4 is used in externally-gated ("Ext. bulb") mode. Each measurement
interval is delimited by a TTL pulse on digital input **D1**. With a 4000-pulse
train, the number of intervals the FX4 actually reports rises **linearly with
the trigger pulse width** and only reaches the full 4000 once the pulse is about
**1 ms** wide:

> captured ≈ 4000 × (pulse_width / 1000 µs), saturating at ~1 ms

This is consistent with the digital input being **sampled and reported at
roughly 1 kHz**, so that a pulse narrower than the reporting period is seen only
with probability ≈ (pulse width)/(1 ms).

That rate is ~10× slower than the analogue sample rate the same device is
streaming at the time (10 kHz at `ValuesPerRead = 10`), and ~100× slower than
the 100 kHz ADC conversion rate. We would like to know whether this is expected,
whether it is configurable, and whether an edge-latching mode exists.

---

## 2. Hardware and firmware

| Item | Value |
|---|---|
| Device | Pyramid Technical Consultants **FX4** quad electrometer (×2) |
| Model string (`Model`) | `FX4` |
| Firmware (`Firmware`) | `26.06.181604` (identical on both units) |
| IP addresses | 10.54.122.170, 10.54.122.171 |
| Control software | EPICS `quadEM` module, `drvFX4` driver (WebSocket + MessagePack) |

Both units are driven identically and both show the effect independently.

### Trigger signal path

- Source: **Pulse Research Lab PRL-414B**, 1:4 fan-out, 50 Ω back-terminated TTL
  line driver, ~2 ns edges. One output per FX4.
- Cable terminated with a **50 Ω feed-through at the D1 end**, giving a measured
  **2.5 V** logic HIGH — within the 3.3 V input spec and above threshold.
  (Unterminated this driver produces 4.4–5 V, which would over-drive the input.)
- Connection: rear-panel DB9 expansion connector, **pin 1 = D1**, pin 9 = ground.
- D1 configured in the web GUI as **GP Input**, pull mode **Pull Down**,
  de-bounce **Off**.
- The signal **idles LOW and strobes HIGH**. The measurement intervals are
  therefore the LOW periods *between* strobes; the HIGH strobe is the delimiter
  and is dead time.

The EPICS driver subscribes to the digital input by its raw path,
`/fx4/gpio_0/22/readback/value`, which the web GUI confirms is **D1** on this
hardware. That path is hard-coded in `drvFX4.h`.

### Acquisition settings during the measurements

| Setting | Value |
|---|---|
| `TriggerMode` | `Ext. bulb` (3) — level-gated; window defined by the gate, `AveragingTime` ignored |
| `TriggerPolarity` | `Negative` (1) — integrate while LOW, emit on the rising edge |
| `AcquireMode` | `Continuous` |
| `ValuesPerRead` | **10** → `SampleTime` = 100 µs, streamed rate 10 kHz/channel |
| ring buffer (`drvFX4Configure`) | 100000 samples (= 10 s at the above rate) |

### Trigger source

An Aerotech Automation1 controller generating **position-synchronised output
(PSO)** pulses from encoder distance. The relevant controller commands:

```
PsoWaveformConfigureMode(axis, PsoWaveformMode.Pulse)
PsoWaveformConfigurePulseFixedTotalTime(axis, <period>)   ; µs
PsoWaveformConfigurePulseFixedOnTime(axis,   <width>)     ; µs  <-- varied below
PsoWaveformConfigurePulseFixedCount(axis, 1)              ; one pulse per event
PsoDistanceConfigureAllowedEventDirection(axis, <dir>)    ; direction-gated
```

`FixedCount = 1` means exactly one pulse per position event, so the pulse
**width** is varied independently of the pulse **spacing**.

---

## 3. What we expect

Per the quadEM documentation and the `drvFX4` source, in `Ext. bulb` mode the
driver integrates the analogue samples that fall inside the active gate level and
emits one averaged reading per gate closure. The driver receives the gate as a
**separate subscription** delivering `[value, timestamp_ns]` pairs, and inserts
each one into a time-ordered event list alongside the ADC samples
(`drvFX4.cpp`, `gateEvent`). Nothing in the driver subsamples the gate or ties it
to `ValuesPerRead`.

We therefore expected the detectable pulse width to be limited by the FX4's own
digital-input timing, and — given a 100 kHz ADC and µs-scale de-bounce options —
expected pulses of tens of microseconds to be reliably detected.

---

## 4. Measurement

A fixed 4000-pulse train was emitted over a ~90 s sweep (mean interval 22.5 ms;
the intervals are not uniform, as the pulses are generated from encoder position
on a non-constant-velocity motion). Only the PSO pulse **width** was changed
between runs. Captured intervals were read from the driver's own counter.

| Trigger pulse width (µs) | Intervals captured (of 4000) | Fraction |
|---|---|---|
| 400 | 1600 | 0.40 |
| 600 | 2400 | 0.60 |
| 800 | 3200 | 0.80 |
| 1000 | 3800 | 0.95 |
| 1200 | 4000 | 1.00 |

An earlier run with a considerably narrower pulse gave 889 of 4000 (0.22).

Two further observations:

- **The two FX4 units capture different totals** from the *same* fan-out of the
  *same* pulse train (e.g. 889 and 887 in one run) until the pulse is wide
  enough, after which both reach 4000. The units therefore miss *different*
  pulses, indicating independent sampling rather than a common upstream loss.
- The relationship is linear in width with no threshold-like knee below
  saturation.

---

## 5. Interpretation

`captured/total ≈ width / 1000 µs` is what results if the input is **sampled
periodically at ~1 kHz** and only its sampled state is reported: a pulse of
width *w* covers a sampling instant with probability *w*/*T* for *w* < *T*, and
always for *w* ≥ *T*. The measured saturation at 1000–1200 µs gives *T* ≈ 1 ms.

The inferred ~1 kHz is **not** the ADC rate (100 kHz), **not** the streamed
sample rate (10 kHz at `ValuesPerRead = 10`), and **not** the ~1 µs de-bounce
granularity described for the digital inputs. It has not been measured directly
at the device — it is inferred from the capture statistics above, which is
precisely why we are asking.

### 5.1 Secondary effect: lost intervals also corrupt the integration window

A missed transition does not only cost one interval. Because the driver tracks
the gate **level** from the events it receives, and skips analogue samples while
it believes the gate is at the inactive level, a lost transition also causes
samples to be discarded from intervals that *are* reported.

This was visible in the data. In the 889/4000 run, the reported number of
averaged samples per interval was ~180 where the measured interval spacing
implied ~960. Both the interval count (22%) and the sample count (19%) were
depressed by the same factor.

**Correction (see §5.3):** this is probably *not* one cause with two symptoms.
Periodic sampling alone predicts the *opposite* sample-count symptom — it
explains the lost intervals, but not the lost samples.

### 5.2 Protocol behaviour confirmed from the IGX Programmer Manual (v6, §3.3.2)

The FX4 runs Pyramid's IGX framework; the WebSocket protocol is documented there.

- **Subscribe flag = buffered vs. unbuffered.** "Buffered data will include all
  the data in an array since the last get event, while unbuffered data will only
  contain the latest data point." `drvFX4` subscribes the gate with `true`
  (buffered), so it is **not** losing pulses by reading only the latest value.
- **Change-only reporting.** With the default `always_update = false`, "the
  protocol only sends new data if the data has changed."
- Consequence: the gate readback (`/fx4/gpio_0/22/readback/value`) is a generic
  GPIO IO whose value is recorded by the IGX IO layer at its own internal rate.
  If a pulse rises and falls **between two IO samples**, the recorded value never
  changes and the pulse is **never present in the transmitted data at all**. This
  reproduces the linear capture ≈ width/T law with T ≈ 1 ms, and explains why the
  two units miss *different* pulses (independent sampling phase).
- Neither the IGX manual nor the FX4 datasheet / user / programmer manuals state
  the GPIO sampling rate, a way to configure it, or an edge-latch mode. The
  ~1 µs de-bounce setting is a delay, not the sampling period.

**Conclusion for issue (1):** the pulse loss is upstream of the WebSocket, in the
device's GPIO sampling. It cannot be fixed by any documented device setting, and
the softIOC cannot recover a transition the device never transmits → Pyramid.

### 5.3 The sample-count depression points to a second, asymmetric loss (driver)

If a pulse is missed entirely (both edges between IO samples), the driver never
leaves the integrating (LOW) state, so consecutive intervals **merge** and each
reported interval should contain **more** samples — roughly 1/0.22 ≈ 4.5 intervals'
worth, i.e. close to the ~960 implied by the spacing. The observed ~180 is instead
≈ **one** interval's worth (22.5 ms × 10 kHz ≈ 225, less strobe dead time).

So during the missed stretches the driver believed the gate was **HIGH
(inactive)** and discarded samples: it processed a rising transition but not the
matching falling one. Symmetric periodic sampling cannot produce this (a sampled
HIGH is always followed by a sampled LOW one period later), so a second,
asymmetric loss mechanism is involved.

**Candidate in `drvFX4.cpp` (`onMessageEvent`):** gate events are collected into a
local event list, then

```cpp
if (adcCache_[0].empty()) goto done;
```

discards **all gate events** in any update message that carries no new ADC
samples. If a HIGH is processed but its LOW arrives in such a message, the driver
stays "HIGH", skipping samples until the next processed LOW. Related weaknesses:

- `triggerCallbacks()` is called on every HIGH event without checking that the
  level actually changed.
- `GATE_PATH` is hard-coded in `drvFX4.h`, so an alternative (faster / latched)
  input cannot be used without recompiling.

Fixing these would not recover pulses the device never sends, but a missed pulse
would then degrade gracefully (two intervals merge, samples kept) instead of
silently discarding data from intervals that are reported. *(Caveat: this
reasoning assumes the ~960 figure is the wall-clock span between reported
intervals × 10 kHz; to be confirmed by the driver-bypass test in §7.)*

### 5.4 Knock-on effect on timing precision

If the digital-input timestamps are the times of periodic IO samples rather than
true edge times (Q4, §9A), interval boundaries carry up to ~1 ms of error. The
per-pulse exposure-time proxy used for stage-tuning diagnostics
(`N × SampleTime`, with `N = TSTotal/TSMeanValue`) then has an effective
resolution of ~1 ms, not 100 µs — still adequate to flag badly oscillating
intervals on 22.5 ms spacing, but it should be stated.

---

## 6. What has been excluded

| Candidate | Why excluded |
|---|---|
| Signal level / termination | 2.5 V into 50 Ω at D1, verified on a scope; within spec and above threshold |
| Ringing / reflections | line is 50 Ω terminated at the receiving end |
| Missing PSO pulses | controller emits exactly the programmed count; output is direction-gated so encoder dither cannot add or drop pulses; changing *only* the pulse width changes the captured count |
| WebSocket / link bandwidth | `RingOverflows` = 0 throughout; widening the pulse alone restored full capture with **no** change to `ValuesPerRead` or data rate |
| Ring-buffer overflow | ring is 100000 samples = 10 s at this rate; longest interval is far below that; overflow counter stayed 0 |
| EPICS record or array limits | array sizes and record limits verified to exceed the point count |
| Driver-side edge resolution | `drvFX4` handles the gate as an independent, buffered, timestamped subscription and does not subsample it. The **interval-count loss** is therefore upstream of the driver, in what the device transmits. **Qualification:** the driver *can* discard gate events that arrive in an update with no ADC samples (§5.3) — a plausible cause of the sample-count depression, not yet excluded |
| Polarity misconfiguration | `Negative` is correct for an idle-low/strobe-high signal; with `Positive` essentially nothing is captured, as expected |

---

## 7. Tests not yet performed

### 7.1 Driver-bypass test (do first — separates device from driver)

Run Pyramid's own WebSocket example (`fx4_ws_mpack_collector.py`, FX4 product
page downloads) with a **buffered** subscription to
`/fx4/gpio_0/22/readback/value` (plus one ADC channel) during a 4000-pulse train
at 400 µs width, and log every update message. Then:

- **Count HIGH values received.** ≈1600 → device-side loss confirmed (§9A).
  ≈4000 → the device sends them and the driver is losing them (§9B).
- **Inspect gate timestamp spacing.** Values quantised to a ~1 ms grid →
  periodic sampling; answers Q1 and Q4 of §9A empirically.
- **Check HIGH/LOW pairing.** Every HIGH followed by a LOW? Tests §5.3.
- **Count update messages that contain gate values but no ADC samples.** Non-zero
  → the `adcCache_[0].empty()` discard in §5.3 is being exercised.

### 7.2 Width scan vs. `ValuesPerRead`

**Repeat the width scan at several `ValuesPerRead` values** (e.g. 10, 20, 50, 100).

- If the width needed for full capture stays ~1 ms → the digital-input sampling
  is fixed and independent of the analogue streaming rate.
- If it scales with `SampleTime` → the gate is being reported on the analogue
  sample cadence, and raising `ValuesPerRead` makes the problem worse.

This distinction determines whether `ValuesPerRead` can be raised freely for
other reasons.

---

## 8. Current workaround and its cost

Trigger pulse width set to **1200 µs**, which gives 4000/4000 on both units.

Against a 22.5 ms mean interval that is ~5% dead time, and proportionally more
on the shortest intervals of the sweep. Because the recorded quantity is the
**mean current** over each interval, dead time does not bias the result — it
reduces the fraction of the motion actually integrated. The true per-interval
duration is recovered and recorded for every point, so the loss is measured
rather than assumed.

The workaround is acceptable but not free, and it sets a floor on how finely the
sweep can be divided.

Margin note: capture requires width ≥ the device's GPIO sampling period. If that
period jitters under CPU load (QNX scheduling), 1200 µs may be marginal; use
**~1500 µs** if occasional misses reappear.

---

## 9. Open questions

### 9A. For Pyramid Technical Consultants (device firmware — missed pulses)

1. **At what rate does the FX4 sample its digital inputs (D1–D4 /
   `gpio_0/22`), and at what rate does it publish changes over the WebSocket
   streaming interface?** Is ~1 kHz the expected figure for firmware
   26.06.181604?
2. **Is that rate configurable**, and is it independent of `ValuesPerRead` /
   the analogue sample rate?
3. **Is there an edge-capture or latch mode** for the digital inputs — so that a
   pulse shorter than the reporting period sets a flag that survives until the
   next report, instead of being missed?
4. **Do the timestamps** delivered with digital-input values represent the true
   edge time, or the time of the periodic sample? (The driver treats them as
   edge times and uses them to define integration boundaries; if they are sample
   times, the interval boundaries carry up to one sampling period of error.)
5. **Does the de-bounce setting affect the sampling or reporting rate?** It is
   currently Off. Would a different setting help or hurt?
6. **Do the fiber-optic receiver inputs** have different (faster) timing
   behaviour than the DB9 digital inputs? If so, can the streaming gate source be
   routed to a fiber receiver instead of `gpio_0/22`?
7. Is there a recommended **minimum external gate pulse width** for `Ext. bulb`
   mode that we should be designing to?
8. The datasheet lists D1 as also usable as **Encoder A** (QEP; the user manual
   says it can act as a general-purpose counter), and the programmer manual's
   digital mode list includes **`capture`** and **`pru_input`**. On the AM335x
   these are hardware edge-counting / edge-timestamping resources that cannot
   miss a pulse. **Can D1 in capture, encoder/counter, or PRU mode be subscribed
   as a buffered WebSocket IO with hardware timestamps?** If so, what are the IO
   paths, and does the plain `gpio_0/22/readback` still reflect the pin in that
   mode?
9. What is the **internal update period of the `gpio_0` readback IO**, and does
   it **jitter under CPU load**?
10. Does the dose-controller **"Process Input"** path run at a faster cadence
    than a GP Input, and can its state be streamed with timestamps?

### 9B. For the softIOC developer / quadEM maintainer (`drvFX4` — sample-count corruption)

1. In `drvFX4::onMessageEvent`, `if (adcCache_[0].empty()) goto done;` discards
   gate events that arrive in an update without ADC samples. **Can gate events be
   retained** (e.g. kept in a persistent queue and merged with the next ADC
   batch by timestamp) instead of dropped? (§5.3)
2. **Should `triggerCallbacks()` fire only on a genuine level change** (edge),
   rather than on every received HIGH/LOW value?
3. **Can `GATE_PATH` become a `drvFX4Configure` argument** (or a PV), so a faster
   or hardware-latched input can be used if Pyramid provides one (§9A Q8)?
4. Would it be feasible to **detect missed pulses** — e.g. by also subscribing a
   hardware pulse counter on the gate input (if available) and flagging when
   counter increments exceed processed gate edges?
5. Is the gate timestamp base guaranteed to be the same as the ADC timestamp
   base? Any offset would misassign samples at interval boundaries.

---

## 10. How to reproduce

1. Configure D1 as GP Input, pull-down, de-bounce off. Terminate the source in
   50 Ω at D1.
2. Set `TriggerMode = Ext. bulb`, `TriggerPolarity = Negative`,
   `AcquireMode = Continuous`, `ValuesPerRead = 10`.
3. Enable the per-channel statistics plugin and arm its time series for more
   points than the pulse train contains.
4. Apply a train of *N* pulses (idle low, strobe high) at a spacing well above
   the pulse width — tens of milliseconds is ample.
5. Read back the number of intervals recorded, and the per-interval sample
   count.
6. Repeat, changing **only** the pulse width.

Expected if the device behaves as we assume: the count equals *N* for any pulse
width above a few sample periods. Observed: the count is proportional to the
pulse width until ~1 ms.

---

## 11. References

- quadEM driver source — [`quadEMApp/FX4Src/`](https://github.com/epics-modules/quadEM/tree/master/quadEMApp/FX4Src)
  (`drvFX4.cpp`, `drvFX4.h`; gate handling and `gateEvent` insertion)
- quadEM [Acquisition Modes](https://epics-modules.github.io/quadEM/tetramm_modes.html)
- IGX [Programmer Manual v6](https://assets.ctfassets.net/5vxgrhuzunkj/ZN4PsfvM1osKKWNGUQYdp/4b895f3e8421139b33b13d0c541c2d3e/IGX_-_Programmer_Manual%C3%82__v6_.pdf)
  (§3.3.2 JSON message protocol: buffered vs. unbuffered subscribe, `always_update`)
- FX4 product page (downloads incl. WebSocket example `fx4_ws_mpack_collector.py`) —
  <https://ptcusa.com/products/fx4>
- FX4 [Datasheet](https://assets.ctfassets.net/5vxgrhuzunkj/3XaO452MOazhFKPj7BvBCv/5d98bb8c411d783f2cce02f793d6eafd/FX4_DS_250331.pdf)
  · [Programmer Manual v3](https://assets.ctfassets.net/5vxgrhuzunkj/4apUnt4g5Y2yKq9b2zt2YE/08f56643a7f14970570e1195649b8da3/FX4_Programmer_Manual__v3_.pdf)
  · [User Manual v1](https://assets.ctfassets.net/5vxgrhuzunkj/2ubABwl3gdzxIIgVgQVgjT/2f06a817d70e59fd5275f8f51a71b804/FX4_User_Manual__v1_.pdf)
- Trigger source — [PRL-414B datasheet](https://www.aps.anl.gov/files/APS-Uploads/DET/Detector-Pool/Electronics/PulseResearchLab_Electronics/PRL_TTL_LineDriver_414B.pdf)
- Local companion document: `FX4_PSO_flyscan_setup.md` (full site configuration)
