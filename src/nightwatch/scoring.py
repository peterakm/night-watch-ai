"""Rule-based deterioration scoring for overnight vitals.

Implements a *lite* adaptation of NEWS2 (the UK National Early Warning
Score 2), the standard clinical early-warning score used to flag patient
deterioration from routine vital signs. This adaptation:

  - Omits the AVPU/consciousness parameter and the "on supplemental
    oxygen" SpO2 scale, since neither is available from passive vital-sign
    monitors. Every reading is scored as if the patient is alert and on
    room air; a human should confirm both if the score triggers a review.
  - Adds a personal-trend layer on top of NEWS2's absolute thresholds:
    for night-shift monitoring, a patient sliding away from *their own*
    overnight baseline is often the earliest signal, well before any
    single reading crosses an absolute threshold.

This is a decision-support aid, not a diagnostic tool. All "high" or
"medium" results should prompt a human check, not replace one.

Reference: Royal College of Physicians, National Early Warning Score
(NEWS) 2 (2017).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TREND_Z_THRESHOLD = 2.0  # standard deviations from personal baseline


def _rr_score(rr: float):
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _spo2_score(spo2: float):
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _sbp_score(sbp: float):
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def _hr_score(hr: float):
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def _temp_score(temp_c: float):
    if temp_c <= 35.0:
        return 3
    if temp_c <= 36.0:
        return 1
    if temp_c <= 38.0:
        return 0
    if temp_c <= 39.0:
        return 1
    return 2


_SCORERS = {
    "respiratory_rate": _rr_score,
    "spo2": _spo2_score,
    "systolic_bp": _sbp_score,
    "heart_rate": _hr_score,
    "temp_c": _temp_score,
}

_LABELS = {
    "respiratory_rate": "Respiratory rate",
    "spo2": "Oxygen saturation",
    "systolic_bp": "Systolic blood pressure",
    "heart_rate": "Heart rate",
    "temp_c": "Temperature",
}


@dataclass
class VitalScore:
    subscores: dict[str, int]
    total: int
    risk_band: str  # "low" | "low-medium" | "medium" | "high"
    flags: list[str] = field(default_factory=list)


def score_vitals(reading: dict):
    """Score a single vitals reading (dict with heart_rate, respiratory_rate,
    spo2, temp_c, systolic_bp[, diastolic_bp]) using the NEWS2-lite rules."""
    subscores = {}
    flags = []
    for key, scorer in _SCORERS.items():
        value = reading.get(key)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        s = scorer(value)
        subscores[key] = s
        if s >= 2:
            flags.append(f"{_LABELS[key]} {value:.1f} is abnormal (subscore {s})")

    total = sum(subscores.values())
    any_red = any(s == 3 for s in subscores.values())  # NEWS2: any single "red" parameter

    if total >= 7:
        risk_band = "high"
    elif total >= 5:
        risk_band = "medium"
    elif any_red:
        risk_band = "low-medium"
    else:
        risk_band = "low"

    return VitalScore(subscores=subscores, total=total, risk_band=risk_band, flags=flags)


def personal_baseline(history: pd.DataFrame, min_readings: int = 3):
    """Compute a per-vital mean/std from a patient's own earlier readings
    this shift. Returns None if there isn't enough history yet."""
    if len(history) < min_readings:
        return None
    baseline = {}
    for key in _SCORERS:
        if key in history.columns:
            series = history[key].dropna()
            if len(series) >= min_readings:
                std = float(series.std())
                baseline[key] = {"mean": float(series.mean()), "std": std if std > 1e-6 else 1e-6}
    return baseline or None


def trend_flags(reading: dict, baseline: dict):
    """Compare a reading against a baseline (personal or population) and
    report vitals that have drifted more than TREND_Z_THRESHOLD std devs."""
    flags = []
    for key, stats in baseline.items():
        value = reading.get(key)
        if value is None:
            continue
        z = (value - stats["mean"]) / stats["std"]
        if abs(z) >= TREND_Z_THRESHOLD:
            direction = "above" if z > 0 else "below"
            flags.append(
                f"{_LABELS.get(key, key)} is {abs(z):.1f} SD {direction} this patient's baseline "
                f"({value:.1f} vs. baseline {stats['mean']:.1f})"
            )
    return flags
