# FX4 digital-input (gate) timing — narrow external trigger pulses are missed

**Status:** open question for the FX4 manual / Pyramid Technical Consultants.
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
depressed by the same factor — one cause, two symptoms.

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
| Driver-side edge resolution | `drvFX4` handles the gate as an independent timestamped subscription; every received gate value becomes an event. The loss is therefore upstream of the driver, in what the device transmits |
| Polarity misconfiguration | `Negative` is correct for an idle-low/strobe-high signal; with `Positive` essentially nothing is captured, as expected |

---

## 7. Test not yet performed

The single most informative follow-up: **repeat the width scan at several
`ValuesPerRead` values** (e.g. 10, 20, 50, 100).

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

---

## 9. Questions for the manufacturer

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
- FX4 [Datasheet](https://assets.ctfassets.net/5vxgrhuzunkj/3XaO452MOazhFKPj7BvBCv/5d98bb8c411d783f2cce02f793d6eafd/FX4_DS_250331.pdf)
  · [Programmer Manual v3](https://assets.ctfassets.net/5vxgrhuzunkj/4apUnt4g5Y2yKq9b2zt2YE/08f56643a7f14970570e1195649b8da3/FX4_Programmer_Manual__v3_.pdf)
  · [User Manual v1](https://assets.ctfassets.net/5vxgrhuzunkj/2ubABwl3gdzxIIgVgQVgjT/2f06a817d70e59fd5275f8f51a71b804/FX4_User_Manual__v1_.pdf)
- Trigger source — [PRL-414B datasheet](https://www.aps.anl.gov/files/APS-Uploads/DET/Detector-Pool/Electronics/PulseResearchLab_Electronics/PRL_TTL_LineDriver_414B.pdf)
- Local companion document: `FX4_PSO_flyscan_setup.md` (full site configuration)
