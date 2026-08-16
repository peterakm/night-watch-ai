"""Data loading and synthetic generation for elderly overnight vital-sign monitoring.

Real-data source: the "Human Vital Sign Dataset" on Kaggle
(https://www.kaggle.com/datasets/nasirayub2/human-vital-sign-dataset, CC0).
It is not elderly- or night-specific, but it is CC0, has 200,000 rows spanning
ages 18-90, and its documented "High Risk" criteria are ordinary vital-sign
danger zones — useful both as a realistic population sample (filtered to 65+)
and as a source of per-vital baselines. See README.md for download steps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Standardized column names used throughout the rest of the app.
VITAL_COLUMNS = [
    "heart_rate",
    "respiratory_rate",
    "spo2",
    "temp_c",
    "systolic_bp",
    "diastolic_bp",
]

_KAGGLE_COLUMN_MAP = {
    "Patient ID": "patient_id",
    "Heart Rate": "heart_rate",
    "Respiratory Rate": "respiratory_rate",
    "Timestamp": "timestamp",
    "Body Temperature": "temp_c",
    "Oxygen Saturation": "spo2",
    "Systolic Blood Pressure": "systolic_bp",
    "Diastolic Blood Pressure": "diastolic_bp",
    "Age": "age",
    "Gender": "gender",
    "Weight (kg)": "weight_kg",
    "Height (m)": "height_m",
    "Risk Category": "risk_category",
}


def load_kaggle_csv(path: str | Path):
    """Load the Kaggle Human Vital Sign Dataset CSV and standardize column names."""
    df = pd.read_csv(path)
    rename = {k: v for k, v in _KAGGLE_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def elderly_subset(df: pd.DataFrame, min_age: int = 65):
    """Filter a loaded dataset down to patients age >= min_age."""
    if "age" not in df.columns:
        raise ValueError("Dataset has no 'age' column to filter on.")
    return df[df["age"] >= min_age].copy()


def compute_population_baselines(df: pd.DataFrame, min_age: int = 65):
    """Compute per-vital mean/std from the elderly subset of a real dataset.

    Used as a fallback baseline for patients who don't yet have enough of
    their own overnight readings to establish a personal trend.
    """
    subset = elderly_subset(df, min_age=min_age)
    baselines: dict = {"source_rows": int(len(subset)), "min_age": min_age, "vitals": {}}
    for col in VITAL_COLUMNS:
        if col in subset.columns:
            series = subset[col].dropna()
            baselines["vitals"][col] = {
                "mean": float(series.mean()),
                "std": float(series.std()) if len(series) > 1 else 0.0,
            }
    return baselines


def save_baselines(baselines: dict, path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(baselines, indent=2))


def load_baselines(path: str | Path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


# Clinically-plausible defaults for elderly (65+) patients at rest, used when
# no calibrated baseline file is available. Ranges informed by standard adult
# vital-sign reference ranges (as also encoded in the Kaggle dataset's own
# "High Risk" thresholds), not from any single patient population.
DEFAULT_ELDERLY_BASELINES = {
    "vitals": {
        "heart_rate": {"mean": 72.0, "std": 9.0},
        "respiratory_rate": {"mean": 16.0, "std": 2.5},
        "spo2": {"mean": 97.0, "std": 1.5},
        "temp_c": {"mean": 36.6, "std": 0.4},
        "systolic_bp": {"mean": 128.0, "std": 15.0},
        "diastolic_bp": {"mean": 78.0, "std": 8.0},
    }
}


@dataclass
class SyntheticPatient:
    patient_id: str
    name: str
    age: int
    room: str
    deteriorating: bool = False


def _sample_normal_vitals(rng: np.random.Generator):
    b = DEFAULT_ELDERLY_BASELINES["vitals"]
    return {
        "heart_rate": float(rng.normal(b["heart_rate"]["mean"], b["heart_rate"]["std"])),
        "respiratory_rate": float(rng.normal(b["respiratory_rate"]["mean"], b["respiratory_rate"]["std"])),
        "spo2": float(np.clip(rng.normal(b["spo2"]["mean"], b["spo2"]["std"]), 85, 100)),
        "temp_c": float(rng.normal(b["temp_c"]["mean"], b["temp_c"]["std"])),
        "systolic_bp": float(rng.normal(b["systolic_bp"]["mean"], b["systolic_bp"]["std"])),
        "diastolic_bp": float(rng.normal(b["diastolic_bp"]["mean"], b["diastolic_bp"]["std"])),
    }


DEFAULT_INTERVAL_MINUTES = 20

# For the dashboard's open-ended live mode there's no known shift length to
# scale deterioration onset/ramp against (unlike the CLI's fixed-hours
# demo), so these are fixed step counts instead: ~2h in, at 20-min
# intervals, ramping to full severity over the next ~5h and then plateauing
# rather than continuing to worsen forever.
DETERIORATION_ONSET_STEPS = 6
DETERIORATION_RAMP_STEPS = 15


def start_synthetic_ward(
    num_patients: int = 6,
    deteriorating_fraction: float = 0.15,
    seed: int | None = None,
):
    """Set up a new synthetic ward for open-ended live monitoring — there's
    no fixed shift length here. Call next_reading() once per patient per
    tick to grow each patient's vitals history incrementally for as long as
    monitoring stays on.

    A share of patients (~15% by default, always at least one) are marked
    to deteriorate; see next_reading(). seed=None draws a fresh random ward
    every call.
    """
    rng = np.random.default_rng(seed)
    num_deteriorating = max(1, round(num_patients * deteriorating_fraction))
    deteriorating_indices = set(
        rng.choice(num_patients, size=min(num_deteriorating, num_patients), replace=False).tolist()
    )
    first_names = ["Eleanor", "Harold", "Margaret", "Walter", "Ruth", "Frank", "Doris", "Arthur"]
    patients = [
        SyntheticPatient(
            patient_id=f"P{i+1:03d}",
            name=f"{first_names[i % len(first_names)]} {chr(65 + i % 26)}.",
            age=int(rng.integers(67, 92)),
            room=f"{200 + i}",
            deteriorating=(i in deteriorating_indices),
        )
        for i in range(num_patients)
    ]
    return patients, rng


def next_reading(
    patient: SyntheticPatient,
    rng: np.random.Generator,
    step: int,
    timestamp: datetime,
    onset_steps: int = DETERIORATION_ONSET_STEPS,
    ramp_steps: int = DETERIORATION_RAMP_STEPS,
):
    """Generate one new reading for one patient at the given step. Everyone
    draws from a healthy normal distribution, which essentially never
    crosses the NEWS2-lite "high" threshold by chance alone; patients
    marked deteriorating additionally ramp toward respiratory distress +
    falling oxygenation + tachycardia starting at onset_steps, reaching
    full severity after ramp_steps more and then holding there.
    """
    vitals = _sample_normal_vitals(rng)
    if patient.deteriorating and step >= onset_steps:
        progress = min(1.0, (step - onset_steps) / ramp_steps)
        vitals["respiratory_rate"] += 10 * progress
        vitals["spo2"] -= 8 * progress
        vitals["heart_rate"] += 20 * progress
        vitals["systolic_bp"] -= 10 * progress
        vitals["spo2"] = float(np.clip(vitals["spo2"], 82, 100))
    return {
        "patient_id": patient.patient_id,
        "name": patient.name,
        "age": patient.age,
        "room": patient.room,
        "timestamp": timestamp,
        **vitals,
    }


def generate_synthetic_night(
    num_patients: int = 5,
    hours: float = 9.0,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    start_time: datetime | None = None,
    deteriorating_fraction: float = 0.15,
    seed: int | None = None,
):
    """Generate a complete, fixed-length synthetic overnight vitals time
    series in one call — used by the CLI, which just wants a whole night to
    score and summarize, not live ticking. (The dashboard uses
    start_synthetic_ward() + next_reading() instead, incrementally, since
    it has no fixed shift length — see nightwatch.api.)

    seed=None (the default) draws a fresh random ward every call. Pass an
    explicit seed for a reproducible one (e.g. in tests).
    """
    patients, rng = start_synthetic_ward(num_patients, deteriorating_fraction, seed)
    # Night shift: 11pm to 8am by default.
    start_time = start_time or datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)

    # +1 because the first reading is AT start_time (step 0), not one
    # interval after it — N readings span N-1 intervals, not N. Without the
    # +1, a 9-hour shift's last reading lands 20 minutes short (7:40am
    # instead of 8am for an 11pm start).
    num_steps = int((hours * 60) // interval_minutes) + 1
    onset = min(DETERIORATION_ONSET_STEPS, max(1, num_steps // 3))

    rows = [
        next_reading(
            patient,
            rng,
            step,
            start_time + timedelta(minutes=step * interval_minutes),
            onset_steps=onset,
        )
        for patient in patients
        for step in range(num_steps)
    ]
    return patients, pd.DataFrame(rows)
