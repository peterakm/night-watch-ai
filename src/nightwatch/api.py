"""FastAPI backend for the Night Watch AI doctor dashboard.

Wraps the existing data / scoring / summarize modules behind a small REST
API. State is a single in-memory "current shift" — this is a prototype for
one ward on one machine, not a multi-tenant service.

The dashboard is built around live monitoring, not on-demand lookups.
Monitoring is turned ON/OFF, not run for a fixed number of hours: when the
doctor starts it, that moment becomes the shift's start time, and a
background clock generates one new reading per patient every TICK_SECONDS
of real time (compressed — each tick represents DEFAULT_INTERVAL_MINUTES of
simulated time, not real time, so a demo doesn't take 9 real hours to play
out) until the doctor turns it off, at which point the clock freezes and
the shift is done. Whenever a patient's NEWS2-lite risk band gets WORSE,
the backend generates a short, urgent AI alert line and stores it as a
notification — that's the thing the doctor is meant to react to, not a
button they have to remember to click.

Run with: uvicorn nightwatch.api:app --port 8000
(no --reload in normal use — see the README's "running this yourself" notes
on why leftover duplicate processes cause inconsistent state)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from nightwatch import data as nwdata
from nightwatch import scoring
from nightwatch import summarize as nwsummarize
from nightwatch.summarize import build_patient_context, generate_alert

TICK_SECONDS = 5  # real seconds per simulated reading interval
RISK_ORDER = {"low": 0, "low-medium": 1, "medium": 2, "high": 3}
MAX_NOTIFICATIONS = 50
RECOVERY_STEPS_REQUIRED = 3  # consecutive steps below the high-water mark before it's allowed to drop


class _ShiftState:
    """Single in-memory shift. Replaced wholesale by /api/shift/start."""

    def __init__(self):
        self.generated_at: Optional[datetime] = None
        self.start_time: Optional[datetime] = None
        self.stopped_at: Optional[datetime] = None
        self.running: bool = False
        self.current_step: int = 0
        self.patients: list = []
        self.vitals_df: Optional[pd.DataFrame] = None
        self.rng = None
        # last_risk_band is a high-water mark, not the literal current band —
        # it only ever rises immediately, and only falls after
        # RECOVERY_STEPS_REQUIRED consecutive steps below it. That hysteresis
        # is what stops noisy per-step vitals from "flapping" across a NEWS2
        # threshold and re-firing the same escalation every few seconds.
        self.last_risk_band: dict[str, str] = {}
        self.recovery_streak: dict[str, int] = {}
        self.notifications: list[dict] = []

    def is_empty(self):
        return self.generated_at is None


shift = _ShiftState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_clock_loop())
    yield
    task.cancel()


app = FastAPI(title="Night Watch AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartShiftRequest(BaseModel):
    patients: int = 6
    seed: Optional[int] = None


def _require_shift():
    if shift.is_empty():
        raise HTTPException(status_code=404, detail="No shift running yet. POST /api/shift/start first.")


def _patient_by_id(patient_id: str):
    for p in shift.patients:
        if p.patient_id == patient_id:
            return p
    raise HTTPException(status_code=404, detail=f"Unknown patient_id {patient_id!r}")


def _load_population_baseline():
    from pathlib import Path

    baselines_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "elderly_baselines.json"
    calibrated = nwdata.load_baselines(baselines_path)
    if calibrated:
        return calibrated["vitals"]
    return nwdata.DEFAULT_ELDERLY_BASELINES["vitals"]


def _revealed_df(patient_id: str):
    """This patient's readings generated so far. Since vitals_df only ever
    contains what's been generated up to the current tick (there's no
    fixed-length night pre-computed up front), this is just a filter — no
    step-slicing needed."""
    return shift.vitals_df[shift.vitals_df["patient_id"] == patient_id].sort_values("timestamp")


def _patient_state(patient):
    """Compute the current risk score + trend flags for one patient, as of
    the simulated current time. Shared by every read path."""
    revealed = _revealed_df(patient.patient_id)
    latest = revealed.iloc[-1]
    history_before_latest = revealed.iloc[:-1]

    vital_score = scoring.score_vitals(latest.to_dict())

    baseline = scoring.personal_baseline(history_before_latest)
    used_population_fallback = baseline is None
    baseline = baseline or _load_population_baseline()
    trend_flags = scoring.trend_flags(latest.to_dict(), baseline)

    return {
        "patient": patient,
        "revealed": revealed,
        "latest": latest,
        "vital_score": vital_score,
        "trend_flags": trend_flags,
        "used_population_baseline_fallback": used_population_fallback,
    }


def _patient_snapshot(patient):
    state = _patient_state(patient)
    latest = state["latest"]
    revealed = state["revealed"]
    vital_score = state["vital_score"]

    return {
        "patient_id": patient.patient_id,
        "name": patient.name,
        "age": patient.age,
        "room": patient.room,
        "reading_time": latest["timestamp"].isoformat(),
        "readings_this_shift": len(revealed),
        "latest_vitals": {
            "heart_rate_bpm": round(float(latest["heart_rate"]), 1),
            "respiratory_rate_bpm": round(float(latest["respiratory_rate"]), 1),
            "spo2_pct": round(float(latest["spo2"]), 1),
            "temp_c": round(float(latest["temp_c"]), 1),
            "systolic_bp_mmhg": round(float(latest["systolic_bp"]), 1),
            "diastolic_bp_mmhg": round(float(latest["diastolic_bp"]), 1),
        },
        "vitals_history": [
            {
                "timestamp": row["timestamp"].isoformat(),
                "heart_rate": round(float(row["heart_rate"]), 1),
                "respiratory_rate": round(float(row["respiratory_rate"]), 1),
                "spo2": round(float(row["spo2"]), 1),
                "temp_c": round(float(row["temp_c"]), 1),
                "systolic_bp": round(float(row["systolic_bp"]), 1),
                "diastolic_bp": round(float(row["diastolic_bp"]), 1),
            }
            for _, row in revealed.iterrows()
        ],
        "early_warning_score": {
            "total_score": vital_score.total,
            "risk_band": vital_score.risk_band,
            "subscores": vital_score.subscores,
            "abnormal_parameter_flags": vital_score.flags,
        },
        # The badge shown in the UI. A single reading is noisy — a patient
        # with nothing really wrong can briefly cross a threshold by chance
        # and cross back next reading. sustained_risk_band is the same
        # high-water-mark used for alerting (see _check_for_escalations): it
        # only rises immediately but only falls after several consecutive
        # improved readings, so the badge doesn't flicker between colors for
        # noise that was never a real, sustained change.
        "sustained_risk_band": shift.last_risk_band.get(patient.patient_id, vital_score.risk_band),
        "trend_flags": state["trend_flags"],
        "used_population_baseline_fallback": state["used_population_baseline_fallback"],
    }


async def _generate_and_store_alert(patient, state: dict, previous_band: str):
    vital_score = state["vital_score"]
    context = build_patient_context(
        patient={
            "patient_id": patient.patient_id,
            "name": patient.name,
            "age": patient.age,
            "room": patient.room,
        },
        reading=state["latest"].to_dict(),
        vital_score=vital_score,
        trend_flags=state["trend_flags"],
        readings_this_shift=len(state["revealed"]),
        previous_risk_band=previous_band,
    )

    try:
        result = await asyncio.to_thread(generate_alert, context)
        message = result.text
    except Exception:  # noqa: BLE001 - degrade to a rule-engine-only message, never drop the alert
        flags = ", ".join(vital_score.flags) or "overnight trend flagged"
        message = f"{flags}. Check on {patient.name} now."

    shift.notifications.insert(
        0,
        {
            "id": str(uuid4()),
            "patient_id": patient.patient_id,
            "patient_name": patient.name,
            "room": patient.room,
            "risk_band": vital_score.risk_band,
            "previous_risk_band": previous_band,
            "message": message,
            "created_at": datetime.now().isoformat(),
            # "new" -> "checking" (doctor is on their way) -> "checked" (done)
            "status": "new",
        },
    )
    del shift.notifications[MAX_NOTIFICATIONS:]


async def _check_for_escalations():
    for patient in shift.patients:
        state = _patient_state(patient)
        band = state["vital_score"].risk_band
        watermark = shift.last_risk_band.get(patient.patient_id, "low")

        if RISK_ORDER[band] > RISK_ORDER[watermark]:
            # A genuine escalation past the high-water mark: always alert,
            # and re-arm the hysteresis so a single-step wobble back down
            # doesn't itself look like a recovery.
            shift.last_risk_band[patient.patient_id] = band
            shift.recovery_streak[patient.patient_id] = 0
            asyncio.create_task(_generate_and_store_alert(patient, state, watermark))
        elif RISK_ORDER[band] < RISK_ORDER[watermark]:
            streak = shift.recovery_streak.get(patient.patient_id, 0) + 1
            shift.recovery_streak[patient.patient_id] = streak
            if streak >= RECOVERY_STEPS_REQUIRED:
                # Sustained improvement, not noise — allow the mark to drop,
                # so a later re-deterioration counts as new and gets alerted.
                shift.last_risk_band[patient.patient_id] = band
                shift.recovery_streak[patient.patient_id] = 0
        else:
            shift.recovery_streak[patient.patient_id] = 0


def _sim_time_at(step: int):
    return shift.start_time + timedelta(minutes=step * nwdata.DEFAULT_INTERVAL_MINUTES)


async def _clock_loop():
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if shift.is_empty() or not shift.running:
            continue
        shift.current_step += 1
        new_rows = [
            nwdata.next_reading(p, shift.rng, shift.current_step, _sim_time_at(shift.current_step))
            for p in shift.patients
        ]
        shift.vitals_df = pd.concat([shift.vitals_df, pd.DataFrame(new_rows)], ignore_index=True)
        await _check_for_escalations()


@app.get("/api/config")
def get_config():
    return {
        "provider": nwsummarize.PROVIDER,
        "model": nwsummarize.DEFAULT_MODEL,
    }


@app.post("/api/shift/start")
async def start_shift(req: StartShiftRequest):
    patients, rng = nwdata.start_synthetic_ward(num_patients=req.patients, seed=req.seed)
    now = datetime.now()
    shift.generated_at = now
    shift.start_time = now
    shift.stopped_at = None
    shift.running = True
    shift.current_step = 0
    shift.patients = patients
    shift.rng = rng
    shift.last_risk_band = {}
    shift.recovery_streak = {}
    shift.notifications = []

    first_rows = [nwdata.next_reading(p, rng, 0, now) for p in patients]
    shift.vitals_df = pd.DataFrame(first_rows)

    await _check_for_escalations()  # catch anyone already at risk on the first reading
    return get_shift()


@app.post("/api/shift/stop")
def stop_shift():
    """The doctor is turning monitoring off — freeze the clock. History,
    patients, and alerts stay in place for review; nothing is cleared."""
    _require_shift()
    shift.running = False
    shift.stopped_at = datetime.now()
    return get_shift()


@app.get("/api/shift")
def get_shift():
    _require_shift()
    return {
        "generated_at": shift.generated_at.isoformat(),
        "start_time": shift.start_time.isoformat(),
        "stopped_at": shift.stopped_at.isoformat() if shift.stopped_at else None,
        "running": shift.running,
        "patient_count": len(shift.patients),
        "provider": nwsummarize.PROVIDER,
        "model": nwsummarize.DEFAULT_MODEL,
        "current_step": shift.current_step,
        "sim_time": _sim_time_at(shift.current_step).isoformat(),
    }


@app.get("/api/patients")
def list_patients():
    _require_shift()
    snapshots = [_patient_snapshot(p) for p in shift.patients]
    order = {"high": 0, "medium": 1, "low-medium": 2, "low": 3}
    snapshots.sort(key=lambda s: order.get(s["sustained_risk_band"], 9))
    return snapshots


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str):
    _require_shift()
    patient = _patient_by_id(patient_id)
    return _patient_snapshot(patient)


@app.get("/api/notifications")
def list_notifications():
    _require_shift()
    return shift.notifications


def _set_notification_status(notification_id: str, status: str):
    for n in shift.notifications:
        if n["id"] == notification_id:
            n["status"] = status
            return n
    raise HTTPException(status_code=404, detail=f"Unknown notification_id {notification_id!r}")


@app.post("/api/notifications/{notification_id}/checking")
def mark_checking(notification_id: str):
    """The doctor saw the alert and is on their way to the patient."""
    _require_shift()
    return _set_notification_status(notification_id, "checking")


@app.post("/api/notifications/{notification_id}/checked")
def mark_checked(notification_id: str):
    """The doctor has checked on the patient in person."""
    _require_shift()
    return _set_notification_status(notification_id, "checked")


@app.post("/api/notifications/clear")
def clear_notifications():
    _require_shift()
    shift.notifications = []
    return {"cleared": True}
