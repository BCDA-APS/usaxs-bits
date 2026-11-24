# Fly scan: distributing counting time along Q (`pm1:TimeMode = Array`)

Status: **planning, nothing changed** (2026-11-24).  For discussion with the
usxLAX / usxAERO IOC maintainer.

Goal: spend less fly-scan time near Q = 0, where the intensity is very high, and
more at high Q, where it is weak, **without** changing the Q sampling (waypoint
and PSO pulse positions) that the current step law gets right.

Short answer: the Automation1 profile-move driver already supports a
per-segment time array (`usxAERO:pm1:Times`, selected by `pm1:TimeMode =
Array`).  We only need to *compute* that array.  Phase 0 can be tried from the
console with no IOC change.  Phase 1 is one new aSub routine in usxLAX, five
small PVs, and one extra link in `buildTraj`.

---

## 1. How the fly scan is timed today

All of this lives in the usxLAX IOC
(`/net/s12dserv/xorApps/epics/synApps_6_2_1/ioc/usxLAX/`), except the profile
move itself, which is in usxAERO (`motorAutomation1`).

| What | Where | Live value (2026-11-24) |
|---|---|---|
| AR **waypoints**, 200 of them | aSub `usxLAX:USAXStraj:calc` (`USAXSscan.c`) → `usxAERO:pm1:M6Positions` | `FS_NumberOfPoints = 200`, `MinStepTraj = 2.5e-5` |
| AX, DX waypoints | `calcAXTraj` / `calcDXTraj` in `USAXSfly.db`, from AR | — |
| **PSO pulse positions**, 8000 | aSub `usxLAX:USAXSPSO:calc` (same `USAXSscan.c`) → `pm1:PulsePositions` | `PulseMode = Array`, `MinStep = 2.4e-5` |
| **Time per segment** | `fanScanTime`: `FixedTime = FS_ScanTime / FS_NumberOfPoints` | `TimeMode = Fixed`, `FixedTime = 0.45 s` |
| Step law (both arrays) | `step = factor·|AR − ARcenter|^UATerm + MinStep` | `UATerm = 0.5`, `StartOffset = −0.0003`, `Finish = 0.3`, 8 keV |

Every one of the 199 waypoint segments takes 0.45 s.  AR speed is therefore
proportional to the local waypoint step: 0.0006 deg/s at the rocking-curve
peak, 0.097 deg/s at Q = 0.3.

### Where the time actually goes

The pulses follow the same step law as the waypoints, so **each pulse interval
(each FX4 point) lasts about the same time, ~10.5 ms**.  It is ~25 ms only very
close to the peak.  The low-Q region does not get more time *per point*; it
gets more points per unit Q.

What sets the noise of the reduced data is the time inside each **Matilda
bin**.  Matilda keeps Q < 2e-4 as measured and rebins Q > 2e-4 onto 200
log-spaced points (`rebin_QRSdata`).  Per bin, today:

| Q | peak region (Q < 2e-4, total) | 2e-4 | 1e-3 | 1e-2 | 0.1 | 0.29 |
|---|---|---|---|---|---|---|
| time per bin, Fixed mode | 4.3 s | 42 ms | 87 ms | 289 ms | 944 ms | 1578 ms |

Time per bin already rises roughly as **Q^0.5**, the exponent that `UATerm =
0.5` imposes.  The intensity falls as Q^-3 to Q^-4, so the weighting is much
too weak.  It cannot be changed today without also changing the Q resolution,
because one parameter controls both.

### Why the pulse array is not the lever

In `Ext. trig.` mode (since 2026-11-17) each PSO edge closes one FX4 point and
opens the next, with no dead time.  The noise in a Q bin depends only on how
long AR spends crossing that bin.  How many pulses fall inside it makes no
difference.  The pulse array sets the raw sampling grid (resolution near the
peak); the **AR velocity profile** sets the statistics.  The velocity profile
comes from the segment times.

---

## 2. The proposal

Keep `M6Positions` and `PulsePositions` exactly as they are.  Switch
`pm1:TimeMode` to `Array` and give each waypoint segment its own time, so that:

* **time per unit ln(Q) ∝ Q^p** (p = 1.5 is the suggested start);
* **every pulse interval lasts at least `min_dwell`** (3–5 ms).  This protects
  the peak and the low-Q region.  Without it a pure power law starves them
  (0.2 s for the whole peak, sub-millisecond points);
* AR never exceeds `ar_vmax`, and no segment is more than `max_ratio` (1.3)
  times longer than its neighbour, for smooth `MovePt` motion;
* the times add up to `FS_ScanTime`, so the busy-record timeout, progress
  reporting and scan duration all stay as they are.

### What the driver does with `Times` (checked in the source)

`motorAutomation1/automation1App/src/Automation1MotorController.cpp`, `buildProfile()`:

* With `TimeMode = Array` the base class leaves `profileTimes_` as written to
  `pm1:Times`.  The driver turns the profile into an AeroScript loop of
  `MovePt($axes, $waypoints[$index], $rglobal[$timeOffset+$index])`: one time
  per segment, with velocities interpolated by the controller ("3-position /
  1-velocity").  Supported as is.
* **Off-by-one in the driver's indexing** (raise with the maintainer):
  * The motion uses `profileTimes_[i]` for the segment **ending** at waypoint
    i (i = 1 … N−1).  `Times[0]` is never a segment time.
  * But the ramp-in velocity uses `Times[0]` for segment 0→1.
  * The ramp-out velocity uses `Times[N−2]` for the last segment.
  * `totalTime`, which sizes the 1 kHz data collection, sums
    `Times[0 … N−2]`.

  In Fixed mode none of this matters.  In Array mode, the layout that is
  correct for the motion today is

      Times = [t0, t0, t1, t2, …, t(N−2)]       (N values)

  where `t_k` is the time of segment k → k+1.  That keeps every segment and
  the ramp-in right.  What remains wrong is small:
  * the ramp-out velocity uses t(N−3) instead of t(N−2), a ≤ 1 % difference
    at the end of the scan;
  * the driver's data-collection window comes out ~1 s short (88.9 s instead
    of 90 s).  That window only fills the profile readback arrays, which
    nothing in Bluesky or Matilda reads.

  If the maintainer makes the driver consistent (motion using
  `profileTimes_[i-1]`), the layout becomes simply `Times[k] = t_k`.  The code
  below has the layout in one place.
* PSO in `Array` + `Absolute` mode fires at the absolute `PulsePositions`, so
  pulse positions are independent of time.  As expected, changing the times
  does not move the pulses.

---

## 3. The algorithm, step by step

Inputs:
* `a[0…N−1]`: the waypoint array (`M6Positions`);
* `pulses[0…M−1]`: the pulse positions (`PulsePositions`);
* `ARcenter` and energy;
* `T = FS_ScanTime`;
* the parameters `p`, `min_dwell`, `q_floor`, `ar_vmax`, `max_ratio`.

1. **Q of every waypoint.**  `Q(a) = 4π/λ · sin((ARcenter − a)/2)`,
   λ = 12.4/E.  This is the same convention and constant as `USAXSscan.c`.
   Q is signed, because the scan starts on the far side of the peak
   (`StartOffset < 0`), so a segment that crosses Q = 0 still gets its true
   length.
2. **Power-law weight per segment** k (a_k → a_{k+1}):
   `w_k = max(|Q_mid|, q_floor)^(p−1) · |ΔQ_k|`.  This is a discrete
   ∫ Q^p d(ln Q), so time ∝ w gives time per ln Q ∝ Q^p.  The `q_floor`
   (1e-4) keeps the weight finite at Q = 0.
3. **Pulses per segment** `n_k`: count the PSO positions inside
   [a_k, a_{k+1}).  Both arrays are monotonic, so a single pass does it.
4. **Floor per segment**: `floor_k = max(min_dwell · n_k, |Δa_k| / ar_vmax, 1 ms)`.
5. **Combine**: `t_k(A) = max(floor_k, A · w_k)`.  Then apply a raise-only
   ratio limiter: one forward and one backward pass, each setting
   `t_k ≥ t_{k±1}/max_ratio`.
6. **Solve for A**: bisect on A until Σ t_k(A) = T.  Σ t_k(A) is continuous
   and never decreases as A grows, so the bisection always converges.
7. **Fallback**: if the floors alone already exceed T (e.g. a very short scan
   with a large `min_dwell`), use `t_k = T/(N−1)`.  That is exactly Fixed
   mode, and it is flagged with `status = 1`.
8. **Layout**: `Times = [t0, t0, t1, …, t(N−2)]` (see §2).

Each segment gets whichever is larger: its minimum allowance or its share of
the remaining time under the power law.  With p = 1.5 and a 5 ms floor, the
floor wins everywhere below Q ≈ 0.05, so there `min_dwell` alone sets the
time.  Above that, the remaining time is shared ∝ Q^p.  **`min_dwell` sets the
low-Q time; `p` sets the shape at the high-Q end.**

### What the array looks like (live arrays, p = 1.5, min_dwell = 5 ms)

```
  k   AR_k       ΔAR        Q_mid    pulses  floor_k  A·w_k   t_k [s]   (Fixed: 0.452)
  0   8.847208  -1.41e-03  2.50e-04   28     0.1400   0.0012  0.1400
  1   8.845794  -1.16e-03  1.59e-04   25     0.1250   0.0008  0.1250
  2   8.844635  -8.96e-04  8.63e-05   22     0.1100   0.0005  0.1100
  3   8.843739  -6.17e-04  3.27e-05   18     0.0900   0.0003  0.0900
  4   8.843122  -2.90e-04  6.54e-07   10     0.0500   0.0002  0.0692  <- raised by ratio limit
  5   8.842832  -2.73e-04  1.93e-05    9     0.0450   0.0001  0.0533  <- raised by ratio limit
  6   8.842558  -4.56e-04  4.51e-05   13     0.0650   0.0002  0.0650
 40   8.705358  -7.94e-03  1.00e-02   40     0.2000   0.0412  0.2000  <- floor still wins
100   7.829604  -2.15e-02  7.25e-02   43     0.2150   0.2999  0.2999  <- power law wins
150   6.477205  -3.28e-02  1.69e-01   44     0.2200   0.6984  0.6984
198   4.645432  -4.37e-02  2.98e-01   44     0.2200   1.2371  1.2371

pm1:Times (200 values) = [0.14, 0.14, 0.125, 0.11, 0.09, … , 1.2116, 1.2243, 1.2371]
sum of segment times = 90.000 s
```

### Expected result (live arrays, 90 s scan)

Time per Matilda log bin:

| Setting | peak (Q<2e-4) | 2e-4 | 1e-3 | 1e-2 | 0.1 | 0.29 | shortest pulse | AR max speed |
|---|---|---|---|---|---|---|---|---|
| Fixed (today) | 4.3 s | 42 ms | 87 | 289 | 944 | 1578 ms | 10.3 ms | 0.097 deg/s |
| Array p=1.0, 5 ms floor | 0.9 s | 10 ms | 30 | 125 | 1108 | 3091 ms | 4.5 ms | 0.049 |
| **Array p=1.5, 5 ms floor** | 0.9 s | 10 ms | 30 | 125 | 915 | **4259 ms** | 4.5 ms | 0.085 |
| Array p=2.0, 3 ms floor | 0.5 s | 6 ms | 18 | 75 | 751 | **5832 ms** | 2.7 ms | 0.145 |

* **Gain**: the top half-decade gets 2.7–3.7× more time, so the noise there is
  1.6–1.9× lower.  Alternatively, keep today's high-Q quality and shorten
  `FS_ScanTime`.
* **Cost**: Q < 0.01, where the signal is orders of magnitude higher, gets 2–4×
  less time.
* **Limits**: AR stays far below its VMAX (20 deg/s); DX is slower than today
  at high Q.
* "Shortest pulse" is a single interval.  The *mean* per segment is exactly
  `min_dwell`; an interval that straddles a segment boundary can be ~10 %
  shorter.

---

## 4. Code: Python version (Phase 0 prototype, console only)

Pure numpy core plus console helpers.  Tested read-only against the live
arrays on 2026-11-24.  It agrees with the C version below to 5e-12 s.

```python
"""Per-segment times for the USAXS fly-scan profile move (pm1:TimeMode = Array).

Pure numpy core (``compute_segment_times``) plus console helpers that read the
live arrays and write ``usxAERO:pm1:Times`` (``apply_time_array``,
``restore_fixed_time``).
"""

from dataclasses import dataclass

import numpy as np

HC_KEV_A = 12.4  # same constant as USAXSscan.c, so Q here matches the generator


@dataclass
class SegmentTimes:
    """Result of :func:`compute_segment_times`."""

    seg_times: np.ndarray  # (N-1,) time of segment k: waypoint k -> k+1, s
    pm1_times: np.ndarray  # (N,)  array to write to usxAERO:pm1:Times
    pulses_per_segment: np.ndarray  # (N-1,)
    q_mid: np.ndarray  # (N-1,) |Q| at segment midpoint, 1/A
    scale: float  # A in  t_k = max(floor_k, A * w_k)
    status: int  # 0 ok, 1 floors alone exceed total_time -> Fixed fallback
    min_pulse_dwell: float  # shortest pulse interval, s
    max_adjacent_ratio: float  # max t_k / t_(k-1) either way
    driver_total_time: float  # what the current driver will sum, s


def q_of_ar(ar, ar_center, energy_kev):
    """Signed Q (1/A) of analyzer angle *ar*; positive on the scan side."""
    lam = HC_KEV_A / energy_kev
    return 4 * np.pi / lam * np.sin(np.radians(ar_center - np.asarray(ar)) / 2)


def pulses_per_segment(waypoints, pulses):
    """Count the PSO positions that fall in each waypoint segment.

    Segment k is [waypoints[k], waypoints[k+1]), oriented in the scan
    direction.  Pulses outside the trajectory are not counted.
    """
    sgn = 1.0 if waypoints[-1] >= waypoints[0] else -1.0
    w = sgn * np.asarray(waypoints, dtype=float)
    p = sgn * np.asarray(pulses, dtype=float)
    p = p[(p >= w[0]) & (p < w[-1])]
    # index of the segment each pulse lands in
    k = np.searchsorted(w, p, side="right") - 1
    return np.bincount(k, minlength=len(w) - 1)[: len(w) - 1]


def limit_ratio(t, max_ratio):
    """Lengthen segments until no neighbour is more than *max_ratio* longer.

    One forward and one backward pass are enough for a raise-only limiter.
    """
    t = np.array(t, dtype=float)
    for k in range(1, len(t)):
        t[k] = max(t[k], t[k - 1] / max_ratio)
    for k in range(len(t) - 2, -1, -1):
        t[k] = max(t[k], t[k + 1] / max_ratio)
    return t


def compute_segment_times(
    waypoints,
    pulses,
    ar_center,
    energy_kev,
    total_time,
    exponent=1.5,
    min_dwell=0.005,
    q_floor=1e-4,
    ar_vmax=1.0,
    max_ratio=1.3,
    min_segment_time=0.001,
):
    """Distribute *total_time* over the waypoint segments.

    Time per unit ln(Q) is made proportional to Q**exponent, subject to two
    floors per segment: every pulse interval lasts at least *min_dwell*, and
    AR never moves faster than *ar_vmax* (deg/s)::

        w_k     = max(|Q_mid,k|, q_floor)**(exponent-1) * |dQ_k|
        floor_k = max(min_dwell * n_pulses_k, |dAR_k| / ar_vmax, min_segment_time)
        t_k     = max(floor_k, A * w_k)
        t       = limit(t, max_ratio)         # raise-only: t_k >= t_(k+-1)/max_ratio
        A chosen so that sum(t_k) = total_time

    The limiter only ever lengthens a segment, so no floor is violated, and the
    total stays monotonic in A, which is what lets a bisection find A.

    ``exponent = 0`` gives equal time per log-Q bin, ``exponent = 1`` equal
    time per unit Q (constant Q speed), and ``exponent ~ 0.5`` roughly what
    Fixed mode gives today with UATerm = 0.5.
    """
    a = np.asarray(waypoints, dtype=float)
    n_seg = len(a) - 1
    if n_seg < 2:
        raise ValueError("need at least 3 waypoints")

    q = q_of_ar(a, ar_center, energy_kev)
    q_mid = np.abs(q_of_ar(0.5 * (a[1:] + a[:-1]), ar_center, energy_kev))
    dq = np.abs(np.diff(q))  # signed Q, so a segment across Q=0 is right
    w = np.maximum(q_mid, q_floor) ** (exponent - 1.0) * dq

    n_p = pulses_per_segment(a, pulses)
    floor = np.maximum.reduce(
        [
            min_dwell * n_p,
            np.abs(np.diff(a)) / ar_vmax,
            np.full(n_seg, min_segment_time),
        ]
    )

    def times(scale):
        return limit_ratio(np.maximum(floor, scale * w), max_ratio)

    def total(scale):
        return times(scale).sum()

    status = 0
    if total(0.0) >= total_time or w.sum() <= 0:
        # Infeasible: fall back to exactly what Fixed mode would do.
        status = 1
        scale = 0.0
        t = np.full(n_seg, total_time / n_seg)
    else:
        # total(scale) is continuous and non-decreasing: bisect on it.
        lo, hi = 0.0, total_time / w[w > 0].min()  # total(hi) >= total_time
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if total(mid) < total_time:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-12 * hi:
                break
        scale = hi
        t = times(scale)
        t *= total_time / t.sum()  # remove the last 1e-12 of bisection error

    # The current Automation1 driver uses Times[i] for the segment ENDING at
    # waypoint i (i >= 1), but Times[0] for the ramp-in velocity of segment
    # 0->1.  So: Times = [t_0, t_0, t_1, ..., t_(N-2)].
    pm1 = np.concatenate([[t[0]], t])

    # diagnostics
    tw = np.concatenate([[0.0], np.cumsum(t)])
    sgn = 1.0 if a[-1] >= a[0] else -1.0
    p = np.asarray(pulses, dtype=float)
    p = p[(sgn * p >= sgn * a[0]) & (sgn * p <= sgn * a[-1])]
    tp = np.interp(sgn * p, sgn * a, tw)
    min_pulse = float(np.diff(tp).min()) if len(tp) > 1 else float("nan")
    ratio = np.maximum(t[1:] / t[:-1], t[:-1] / t[1:]).max()

    return SegmentTimes(
        seg_times=t,
        pm1_times=pm1,
        pulses_per_segment=n_p,
        q_mid=q_mid,
        scale=float(scale),
        status=status,
        min_pulse_dwell=min_pulse,
        max_adjacent_ratio=float(ratio),
        driver_total_time=float(pm1[: len(a) - 1].sum()),
    )


# ---------------------------------------------------------------------------
# Console helpers for the Phase 0 prototype (no IOC change).
# ---------------------------------------------------------------------------
PV = {
    "waypoints": "usxAERO:pm1:M6Positions",
    "pulses": "usxAERO:pm1:PulsePositions",
    "n_points": "usxAERO:pm1:NumPoints",
    "n_pulses": "usxAERO:pm1:NumPulses",
    "times": "usxAERO:pm1:Times",
    "time_mode": "usxAERO:pm1:TimeMode",
    "ar_center": "usxLAX:USAXS:ARcenter",
    "energy": "12ida2:EnCalc",
    "scan_time": "usxLAX:USAXS:FS_ScanTime",
}


def read_inputs():
    """Read the live trajectory inputs; raises if any PV is unreachable."""
    from epics import caget

    v = {k: caget(pv, timeout=5) for k, pv in PV.items() if k != "times"}
    missing = [k for k, x in v.items() if x is None]
    if missing:
        raise RuntimeError(f"unreadable PVs: {[PV[k] for k in missing]}")
    n, m = int(v["n_points"]), int(v["n_pulses"])
    return dict(
        waypoints=np.asarray(v["waypoints"])[:n],
        pulses=np.asarray(v["pulses"])[:m],
        ar_center=float(v["ar_center"]),
        energy_kev=float(v["energy"]),
        total_time=float(v["scan_time"]),
    )


def summarize(r, edges=(2e-4, 1e-3, 1e-2, 0.1, 0.3)):
    """Print the distribution in a few Q bands."""
    print(
        f"status={r.status} scale={r.scale:.4g} sum={r.seg_times.sum():.2f}s "
        f"driver_total={r.driver_total_time:.2f}s "
        f"min pulse={1e3 * r.min_pulse_dwell:.2f}ms "
        f"max ratio={r.max_adjacent_ratio:.2f}"
    )
    lo = 0.0
    for hi in edges:
        m = (r.q_mid >= lo) & (r.q_mid < hi)
        print(
            f"  Q {lo:7.1e}-{hi:7.1e}: {m.sum():3d} segs "
            f"{r.pulses_per_segment[m].sum():5d} pulses {r.seg_times[m].sum():6.2f} s"
        )
        lo = hi


def apply_time_array(dry_run=True, **params):
    """Compute times from the live arrays and (unless dry_run) arm Array mode.

    Must be re-run after anything that regenerates M6Positions: a tune that
    moves ARcenter, an energy change, Finish, UATerm, StartOffset, NumPoints.
    """
    from epics import caput

    inp = read_inputs()
    r = compute_segment_times(**inp, **params)
    summarize(r)
    if r.status != 0:
        print("floors exceed FS_ScanTime -- NOT writing; staying in Fixed mode")
        return r
    if not dry_run:
        caput(PV["times"], r.pm1_times, wait=True, timeout=10)
        caput(PV["time_mode"], "Array", wait=True, timeout=10)
        print("pm1:Times written, pm1:TimeMode = Array")
    return r


def restore_fixed_time():
    """Rollback: back to equal time per segment (today's behaviour)."""
    from epics import caput

    caput(PV["time_mode"], "Fixed", wait=True, timeout=10)
    print("pm1:TimeMode = Fixed")
```

Console use:

```python
r = apply_time_array()                                   # dry run: prints, writes nothing
r = apply_time_array(dry_run=False, exponent=1.5, min_dwell=0.005)
RE(Flyscan(...))                                         # no tune in between!
restore_fixed_time()                                     # rollback
```

---

## 5. Code: IOC version (Phase 1, for the maintainer)

### 5.1 `usxLAXApp/src/USAXSscanTimes.c`

The core is plain C, so it can be unit-tested without EPICS (compile with
`-DUSAXS_SCAN_TIMES_STANDALONE`).  It was compiled with
`gcc -Wall -Wextra` and checked against the Python on the live arrays for four
settings, including the fallback.  The aSub wrapper passes `gcc -fsyntax-only`
against base-7.0.8 headers.

```c
/* USAXSscanTimes.c -- per-segment times for the USAXS fly-scan profile move
 *
 * aSub support for usxLAX.  Writes usxAERO:pm1:Times so that, with
 * pm1:TimeMode = Array, time per unit ln(Q) goes as Q^exponent instead of
 * being fixed by the waypoint spacing.  Waypoint and PSO pulse POSITIONS are
 * untouched; only how long each waypoint segment takes changes.
 *
 * For segment k (waypoint k -> k+1), k = 0 .. N-2:
 *
 *   w_k     = max(|Q_mid,k|, qFloor)^(exponent-1) * |dQ_k|
 *   floor_k = max(minDwell * nPulses_k, |dAR_k| / arVmax, MIN_SEGMENT_TIME)
 *   t_k     = max(floor_k, A * w_k), then raise-only ratio limit
 *   A chosen by bisection so that sum(t_k) = totalTime
 *
 * If the floors alone exceed totalTime, every t_k = totalTime/(N-1), which is
 * exactly what TimeMode = Fixed would have done, and status = 1.
 *
 * Inputs                                   Outputs
 *   A  ARcenter, deg            DOUBLE       VALA pm1:Times (N used)  DOUBLE[NOVA]
 *   B  energy, keV              DOUBLE       VALB status 0 ok/1 fallback/-1 bad
 *   C  total time, s            DOUBLE       VALC scale A             DOUBLE
 *   D  exponent                 DOUBLE       VALD shortest mean dwell/pulse, s
 *   E  min dwell per pulse, s   DOUBLE       VALE largest adjacent ratio
 *   F  Q floor, 1/A             DOUBLE       VALF sum of segment times, s
 *   G  AR max speed, deg/s      DOUBLE
 *   H  max adjacent ratio       DOUBLE
 *   I  NumPoints                LONG
 *   J  NumPulses                LONG
 *   K  M6Positions              DOUBLE[NOK]
 *   L  PulsePositions           DOUBLE[NOL]
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#define PI 3.14159265358979323846
#define HC_KEV_A 12.4          /* same constant as USAXSscan.c */
#define MIN_SEGMENT_TIME 0.001 /* s; never hand MovePt a zero time */

static double qOfAr(double ar, double center, double lambda) {
	/* signed Q; same angle convention as USAXSscan.c */
	return 4.0 * PI / lambda * sin((center - ar) * PI / 360.0);
}

/* Raise-only limiter: afterwards no neighbour is more than maxRatio longer. */
static void limitRatio(double *t, int n, double maxRatio) {
	int k;
	for (k = 1; k < n; k++)
		if (t[k] < t[k-1] / maxRatio) t[k] = t[k-1] / maxRatio;
	for (k = n - 2; k >= 0; k--)
		if (t[k] < t[k+1] / maxRatio) t[k] = t[k+1] / maxRatio;
}

/* t[k] = limitRatio(max(floor[k], scale*w[k])); returns the sum. */
static double timesFor(double scale, const double *w, const double *floorT,
		double *t, int nSeg, double maxRatio) {
	int k;
	double sum = 0.0;
	for (k = 0; k < nSeg; k++) {
		double tw = scale * w[k];
		t[k] = (tw > floorT[k]) ? tw : floorT[k];
	}
	limitRatio(t, nSeg, maxRatio);
	for (k = 0; k < nSeg; k++) sum += t[k];
	return sum;
}

/* Core calculation, free of EPICS so it can be unit-tested with plain gcc.
 *
 * segT   (out) nPts-1 segment times
 * pm1T   (out) nPts values for pm1:Times, in the current driver's layout
 * returns status: 0 ok, 1 fallback to fixed, -1 bad input
 */
int usaxsSegmentTimes(const double *way, int nPts, const double *pulses,
		int nPulses, double center, double energy, double totalTime,
		double exponent, double minDwell, double qFloor, double arVmax,
		double maxRatio, double *segT, double *pm1T, double *pScale,
		double *pMinDwell, double *pMaxRatio, double *pSum) {
	int nSeg = nPts - 1, k, i, iter, status = 0;
	double lambda, dir, scale = 0.0, sum, lo, hi, wmin;
	double *w, *floorT;
	int *nP;

	*pScale = 0.0; *pMinDwell = 0.0; *pMaxRatio = 0.0; *pSum = 0.0;
	if (nSeg < 2 || energy <= 0.0 || totalTime <= 0.0 || arVmax <= 0.0
			|| maxRatio < 1.0)
		return -1;

	w = calloc(nSeg, sizeof(double));
	floorT = calloc(nSeg, sizeof(double));
	nP = calloc(nSeg, sizeof(int));
	if (!w || !floorT || !nP) { free(w); free(floorT); free(nP); return -1; }

	lambda = HC_KEV_A / energy;
	dir = (way[nPts-1] >= way[0]) ? 1.0 : -1.0;

	/* pulses per segment, pulses outside the trajectory ignored.  Both
	 * arrays are monotonic in the scan direction: one merge pass. */
	k = 0;
	for (i = 0; i < nPulses; i++) {
		double p = dir * pulses[i];
		if (p < dir * way[0] || p >= dir * way[nPts-1]) continue;
		while (k < nSeg - 1 && p >= dir * way[k+1]) k++;
		nP[k]++;
	}

	/* power-law weight and floors */
	wmin = 0.0;
	for (k = 0; k < nSeg; k++) {
		double qa = qOfAr(way[k], center, lambda);
		double qb = qOfAr(way[k+1], center, lambda);
		double qm = fabs(qOfAr(0.5 * (way[k] + way[k+1]), center, lambda));
		double f1 = minDwell * nP[k];
		double f2 = fabs(way[k+1] - way[k]) / arVmax;
		if (qm < qFloor) qm = qFloor;
		w[k] = pow(qm, exponent - 1.0) * fabs(qb - qa);
		floorT[k] = MIN_SEGMENT_TIME;
		if (f1 > floorT[k]) floorT[k] = f1;
		if (f2 > floorT[k]) floorT[k] = f2;
		if (w[k] > 0.0 && (wmin == 0.0 || w[k] < wmin)) wmin = w[k];
	}

	if (wmin == 0.0
			|| timesFor(0.0, w, floorT, segT, nSeg, maxRatio) >= totalTime) {
		status = 1;
		for (k = 0; k < nSeg; k++) segT[k] = totalTime / nSeg;
	} else {
		/* sum is continuous and non-decreasing in scale: bisect */
		lo = 0.0;
		hi = totalTime / wmin;  /* every t_k >= hi*w_k -> sum >= totalTime */
		for (iter = 0; iter < 200; iter++) {
			double mid = 0.5 * (lo + hi);
			if (timesFor(mid, w, floorT, segT, nSeg, maxRatio) < totalTime)
				lo = mid;
			else
				hi = mid;
			if (hi - lo <= 1e-12 * hi) break;
		}
		scale = hi;
		sum = timesFor(scale, w, floorT, segT, nSeg, maxRatio);
		for (k = 0; k < nSeg; k++) segT[k] *= totalTime / sum;
	}

	/* diagnostics */
	sum = 0.0;
	*pMinDwell = -1.0;
	for (k = 0; k < nSeg; k++) {
		sum += segT[k];
		if (nP[k] > 0) {
			double d = segT[k] / nP[k];
			if (*pMinDwell < 0.0 || d < *pMinDwell) *pMinDwell = d;
		}
		if (k > 0) {
			double r = segT[k] / segT[k-1];
			if (r < 1.0) r = 1.0 / r;
			if (r > *pMaxRatio) *pMaxRatio = r;
		}
	}
	*pScale = scale;
	*pSum = sum;

	/* Current Automation1 driver: Times[i] is the segment ENDING at
	 * waypoint i (i >= 1); Times[0] only sets the ramp-in velocity of
	 * segment 0->1.  Hence Times = [t0, t0, t1, ..., t(N-2)].  If the
	 * driver's indexing is made consistent, this becomes pm1T[k] = segT[k]. */
	pm1T[0] = segT[0];
	for (k = 1; k < nPts; k++) pm1T[k] = segT[k-1];

	free(w); free(floorT); free(nP);
	return status;
}

#ifndef USAXS_SCAN_TIMES_STANDALONE
/* ---------------- aSub wrapper ---------------- */
#include <dbDefs.h>
#include <aSubRecord.h>
#include <registryFunction.h>
#include <epicsExport.h>

static long USAXSscanTimes(aSubRecord *prec) {
	double center    = *(double *)prec->a;
	double energy    = *(double *)prec->b;
	double totalTime = *(double *)prec->c;
	double exponent  = *(double *)prec->d;
	double minDwell  = *(double *)prec->e;
	double qFloor    = *(double *)prec->f;
	double arVmax    = *(double *)prec->g;
	double maxRatio  = *(double *)prec->h;
	epicsInt32 nPts    = *(epicsInt32 *)prec->i;
	epicsInt32 nPulses = *(epicsInt32 *)prec->j;
	double *way    = (double *)prec->k;
	double *pulses = (double *)prec->l;
	double *pm1T   = (double *)prec->vala;
	double *segT;
	int status;

	if (nPts > (epicsInt32)prec->nok || nPts > (epicsInt32)prec->nova
			|| nPulses > (epicsInt32)prec->nol || nPts < 3) {
		*(epicsInt32 *)prec->valb = -1;
		return -1;  /* non-zero: aSub does not write its outputs */
	}
	segT = calloc(nPts, sizeof(double));
	if (!segT) return -1;

	status = usaxsSegmentTimes(way, nPts, pulses, nPulses, center, energy,
			totalTime, exponent, minDwell, qFloor, arVmax, maxRatio, segT,
			pm1T, (double *)prec->valc, (double *)prec->vald,
			(double *)prec->vale, (double *)prec->valf);
	free(segT);

	*(epicsInt32 *)prec->valb = status;
	if (status < 0) return -1;
	prec->neva = nPts;  /* write exactly NumPoints elements to pm1:Times */
	return 0;
}

static registryFunctionRef USAXSscanTimesRef[] = {
	{"USAXSscanTimes", (REGISTRYFUNCTION)USAXSscanTimes},
};

static void USAXSscanTimesRegister(void) {
	registryFunctionRefAdd(USAXSscanTimesRef, NELEMENTS(USAXSscanTimesRef));
}

epicsExportRegistrar(USAXSscanTimesRegister);
#endif
```

### 5.2 Build: `usxLAXApp/src/USAXSscan.dbd` and `Makefile`

Add to `USAXSscan.dbd`, next to the existing `registrar(USAXSscanRegister)`:

```
registrar(USAXSscanTimesRegister)
```

And in `usxLAXApp/src/Makefile`, next to line 352 (`$(PROD_NAME)_SRCS += USAXSscan.c`):

```make
  $(PROD_NAME)_SRCS  += USAXSscanTimes.c
```

### 5.3 Parameters: `usxLAXApp/Db/USAXSterms.db`

Next to the other `FS_` records:

```
grecord(ao, "usxLAX:USAXS:FS_TimeExponent") {
    field(DESC, "fly time per lnQ ~ Q^p")
    field(VAL,  "1.5")
    field(PREC, "2")
}
grecord(ao, "usxLAX:USAXS:FS_MinDwell") {
    field(DESC, "min time per PSO interval")
    field(VAL,  "0.005")
    field(EGU,  "s")
    field(PREC, "4")
}
grecord(ao, "usxLAX:USAXS:FS_QFloor") {
    field(DESC, "Q below which weight is flat")
    field(VAL,  "1e-4")
    field(EGU,  "1/A")
    field(PREC, "6")
}
grecord(ao, "usxLAX:USAXS:FS_ARVmax") {
    field(DESC, "AR speed cap for time array")
    field(VAL,  "1.0")
    field(EGU,  "deg/s")
    field(PREC, "3")
}
grecord(ao, "usxLAX:USAXS:FS_TimeMaxRatio") {
    field(DESC, "max adjacent segment-time ratio")
    field(VAL,  "1.3")
    field(PREC, "2")
}
```

Add their `.VAL` to `iocBoot/iocusxLAX/auto_settings.req`, as for
`FS_ScanTime`.

### 5.4 The aSub record: `usxLAXApp/Db/USAXSfly.db`

`ENERGY` must be added to the `USAXSfly.db` macro string in `USAXS.cmd`
(`...,ENERGY=12ida2:EnCalc`), the same PV the trajectory generators use.

```
# per-segment times for pm1:TimeMode = Array; processed by buildTraj
record(aSub, "$(P)$(Q)calcTimes") {
	field(DESC, "fly-scan segment times")
	field(SNAM, "USAXSscanTimes")
	field(PREC, "5")
	field(FTA, "DOUBLE")  field(INPA, "$(P)USAXS:ARcenter NPP")
	field(FTB, "DOUBLE")  field(INPB, "$(ENERGY) NPP")
	field(FTC, "DOUBLE")  field(INPC, "$(P)USAXS:FS_ScanTime NPP")
	field(FTD, "DOUBLE")  field(INPD, "$(P)USAXS:FS_TimeExponent NPP")
	field(FTE, "DOUBLE")  field(INPE, "$(P)USAXS:FS_MinDwell NPP")
	field(FTF, "DOUBLE")  field(INPF, "$(P)USAXS:FS_QFloor NPP")
	field(FTG, "DOUBLE")  field(INPG, "$(P)USAXS:FS_ARVmax NPP")
	field(FTH, "DOUBLE")  field(INPH, "$(P)USAXS:FS_TimeMaxRatio NPP")
	field(FTI, "LONG")    field(INPI, "$(PA)pm1:NumPoints")
	field(FTJ, "LONG")    field(INPJ, "$(PA)pm1:NumPulses")
	field(FTK, "DOUBLE")  field(NOK, "$(MAXPTS)")    field(INPK, "$(PA)pm1:M6Positions")
	field(FTL, "DOUBLE")  field(NOL, "$(MAXPULSES)") field(INPL, "$(PA)pm1:PulsePositions")
	field(FTVA, "DOUBLE") field(NOVA, "$(MAXPTS)")   field(OUTA, "$(PA)pm1:Times CA")
	field(FTVB, "LONG")
	field(FTVC, "DOUBLE")
	field(FTVD, "DOUBLE")
	field(FTVE, "DOUBLE")
	field(FTVF, "DOUBLE")
}
```

`VALB…VALF` (status, scale, shortest mean dwell, largest ratio, sum) are
readable directly as `usxLAX:USAXSfly:calcTimes.VALB` etc. for diagnostics and
for the HDF5 file.

### 5.5 When it runs: `buildTraj`

Compute the times **inside every scan's build**, from the arrays that are
about to be built, never on a CP chain.  That way they cannot go stale after a
tune moves `ARcenter`, and a scan replayed after a suspension rebuilds them
too.

```
record(sseq, "$(P)$(Q)buildTraj") {
	field(SDIS, "$(P)$(Q)Start")
	field(DISV, "0")
	field(PREC, "5")

	# calc Npulses and write to trajectory database and MCS
	field(LNK1, "$(P)$(Q)calcNpulses.PROC CA")
	field(WAIT1, "Wait")

	# NEW: segment times -> pm1:Times (ignored by the driver in Fixed mode)
	field(LNK2, "$(P)$(Q)calcTimes.PROC CA")
	field(WAIT2, "Wait")

	# build trajectory
	field(DLY3, "0.2")
	field(STR3, "Busy")
	field(LNK3, "$(PA)pm1:Build CA")
	field(WAIT3, "Wait")
}
```

`WAIT2` waits for `calcTimes` to process, but not for its `OUTA` CA put to
reach usxAERO.  Both puts travel on the same CA circuit and should arrive in
order; `DLY3` is a cheap safety margin.  The maintainer may prefer another way
to guarantee the order.

In Fixed mode the driver ignores `Times`, so running this every scan is
harmless.  **Rollback is `pm1:TimeMode = Fixed`** and nothing else.

---

## 6. Phases and tests

**Phase 0 — console prototype, no IOC change.**  Use the Python in §4.
* Re-run `apply_time_array` before **every** test scan.  `M6Positions` is
  regenerated whenever `ARcenter`, energy, `Finish`, `UATerm`, `StartOffset`
  or `NumPoints` changes, and a tune between computing and flying leaves
  stale times.  The motion would still be valid, but with the wrong
  distribution.
* Tests, with `restore_fixed_time()` at the end:
  1. `pm1:Build` succeeds and `pm1:ExecuteStatus = Success` with Array mode.
  2. Scan duration ≈ `FS_ScanTime`, and the FX4 point count equals the
     pulse count.
  3. Blank and glassy-carbon (or another standard): Fixed vs. p = 1.5 /
     5 ms, same `FS_ScanTime`.  Compare reduced noise against Q and the
     absolute level, and look at the peak region and any range-change
     artefacts.
  4. Repeat at p = 2 / 3 ms to choose the defaults.

**Phase 1 — IOC** (§5).  Run the same tests with the IOC computing the times.

**Phase 2 — Bluesky and data files.**
* Add `pm1:TimeMode`, `pm1:Times`, the five `FS_` parameters and
  `calcTimes.VALB` to `ADconfigs/Flyscan_config/saveFlyData.xml`, so every
  file records the time distribution it was taken with.  Today only
  `FixedTime` is recorded.
* `Flyscan` should **write `pm1:TimeMode` explicitly on every scan**, from a
  soft setting on `usaxs_flyscan`, rather than trusting whatever state was
  autosaved.  This is the same lesson as `seq01:dir`.  Check whether
  `pm1:TimeMode` is in usxAERO's autosave.
* Matilda: no change expected.  The error model already uses the measured
  per-point `channel_time` (`fx4support.current_sigma`), and within one log
  bin the dwell changes slowly, so the plain mean in `rebin_log_data` is
  adequate.  Still to confirm: blank subtraction does not assume the sample
  and blank had the same time distribution.

---

## 7. Risks and open questions

1. **FX4 autoranging through the peak, the main risk.**  AR crosses the
   rocking-curve peak 4–8× faster than today, so a range change spans more
   points.  Before choosing `min_dwell`, measure how long a range switch takes
   to settle and how many points it corrupts in a fly scan (`Both` policy).
   If it bites, raise `min_dwell` only near the peak (e.g. a second floor for
   |Q| < 3e-4).  That is a small extension of step 4.
2. **Driver indexing (§2).**  Ask the maintainer to confirm the reading of
   `buildProfile()` and decide whether to fix it upstream in
   `motorAutomation1`.  If it is fixed, the last loop of the C and the
   `np.concatenate` in the Python change together.
3. **Ordering of the `OUTA` CA put before `pm1:Build`** (§5.5).
4. **`FS_ScanTime` must remain the true scan duration**, because the Bluesky
   busy timeout is `scan_time + timeout_s`.  The algorithm guarantees
   Σ t_k = `FS_ScanTime`.
5. **Choosing p and `min_dwell`.**  The right exponent depends on where the
   sample's signal meets the background.  Later we could derive the weight
   from a measured profile (the blank, or a quick first scan) instead of a
   power law.  The algorithm stays the same; only `w_k` changes.

## 8. Side findings in the IOC (independent of this plan)

* `fanScanTime` sets `FixedTime = FS_ScanTime / FS_NumberOfPoints`, but there
  are `NumPoints − 1` segments, so a "90 s" scan takes 89.55 s.
* `uascanFindFactor` (`USAXSscan.c`) calls `uascanTestSeries(start, finish,
  numPts, factor, center, …)` with the arguments in the wrong order on its
  first call.  It is harmless, because the search recovers, but worth fixing
  while the file is open.
* `arCalcSpeed` / `axCalcSpeed` / `dxCalcSpeed` and `*plotXAxis` assume equal
  time per segment.  They are diagnostics only, but read wrong in Array mode.
  They could use `pm1:Times`.
* Struck-era records (`calcNpulses*` → `3820:NuseAll`, `resetGainRecs`,
  `evalAR`) still run in every `scanSseq`.  They are unrelated to this plan
  and harmless.
