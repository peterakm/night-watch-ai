"""Turns structured vitals + rule-engine output into doctor-facing text using
an LLM — either a full night-shift summary (used by the CLI) or a short,
urgent one-line alert (used by the dashboard's live notification system).

The LLM's job is narrowly scoped either way: turn already-computed structured
findings into text a physician can read in a few seconds. It does not compute
risk scores itself and is instructed not to introduce clinical claims beyond
what the structured input contains — the rule engine (scoring.py) is the
source of truth for the numbers; the model's job is presentation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

PROVIDER = "ollama"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("NIGHTWATCH_MODEL", "qwen2.5:7b")

SUMMARY_SYSTEM_PROMPT = """\
You are Night Watch AI, a clinical decision-support assistant that helps a \
physician who is covering an elderly-care ward overnight with limited \
nursing staff available for in-person rounds.

You will receive structured JSON for one patient: identifying info, the \
latest vital-sign reading, a rule-based early-warning score (an adaptation \
of NEWS2) with its risk band, any abnormal-parameter flags, and any flags \
showing the patient has drifted from their own overnight baseline.

Write a short summary (3-5 sentences) for the physician that:
- Leads with the risk band and the single most important finding.
- States the specific abnormal numbers, not just that something is "off".
- Distinguishes an acute abnormal reading from a slower drift/trend, if both are present.
- Ends with a concrete, proportionate recommendation (e.g. "no action needed, \
  recheck at next round" vs. "recommend an in-person check now").

Rules:
- Only use the facts given in the input JSON. Do not invent vitals, history, \
  diagnoses, or medications that are not present in the data.
- Do not offer a diagnosis. You are summarizing monitoring data, not \
  interpreting a clinical picture.
- If the risk band is "low" and there are no trend flags, say so briefly and \
  plainly rather than padding the summary.
- Write for a physician who is short on time in the middle of the night: no \
  preamble, no headers, plain prose.
"""

ALERT_SYSTEM_PROMPT = """\
You are Night Watch AI's alerting system for an elderly-care ward overnight, \
with limited nursing staff available for in-person rounds. A rule-based \
early-warning engine has just detected that a patient's risk band got WORSE. \
The physician can already see the raw vital-sign numbers on their screen — \
your only job is to say, in one urgent sentence, WHY this patient needs a \
check now, not to restate every number.

You will receive structured JSON: identifying info, the patient's previous \
risk band and their new (worse) one, the latest vitals, the specific \
abnormal-parameter flags that triggered this level, and any trend flags.

Write exactly ONE sentence, under 20 words, that:
- Names the single most clinically significant finding driving the escalation \
  (e.g. "breathing distress with falling oxygen", not a list of numbers).
- Ends with a clear instruction to check the patient now.

Rules:
- Only use facts given in the input JSON. Never invent a diagnosis, vitals, \
  or history not present in the data.
- No preamble, no greeting, no "Alert:" prefix, no markdown — just the one \
  sentence, as if paging the on-call physician.
"""


@dataclass
class SummaryResult:
    patient_id: str
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


def build_patient_context(
    patient: dict,
    reading: dict,
    vital_score,
    trend_flags: list[str],
    readings_this_shift: int,
    previous_risk_band: str | None = None,
):
    """Assemble the structured JSON payload sent to the model for one patient.

    previous_risk_band is set when this context is being built for an alert
    (a risk-band escalation), so the model can see what changed.
    """
    context = {
        "patient_id": patient["patient_id"],
        "name": patient["name"],
        "age": patient["age"],
        "room": patient["room"],
        "reading_time": str(reading["timestamp"]),
        "latest_vitals": {
            "heart_rate_bpm": round(reading.get("heart_rate", float("nan")), 1),
            "respiratory_rate_bpm": round(reading.get("respiratory_rate", float("nan")), 1),
            "spo2_pct": round(reading.get("spo2", float("nan")), 1),
            "temp_c": round(reading.get("temp_c", float("nan")), 1),
            "systolic_bp_mmhg": round(reading.get("systolic_bp", float("nan")), 1),
            "diastolic_bp_mmhg": round(reading.get("diastolic_bp", float("nan")), 1),
        },
        "early_warning_score": {
            "system": "NEWS2-lite (consciousness and supplemental-O2 scale not assessed)",
            "total_score": vital_score.total,
            "risk_band": vital_score.risk_band,
            "abnormal_parameter_flags": vital_score.flags,
        },
        "personal_trend_flags": trend_flags,
        "readings_recorded_this_shift": readings_this_shift,
    }
    if previous_risk_band is not None:
        context["previous_risk_band"] = previous_risk_band
    return context


def _call_ollama(system_prompt: str, context: dict, model: str):
    import httpx

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, indent=2)},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    try:
        resp = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120.0)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_HOST}. Is `ollama serve` running? "
            f"(pull the model first with `ollama pull {model}`)"
        ) from e
    data = resp.json()

    return SummaryResult(
        patient_id=context["patient_id"],
        text=data["message"]["content"].strip(),
        model=data.get("model", model),
        input_tokens=data.get("prompt_eval_count", 0),
        output_tokens=data.get("eval_count", 0),
        cache_read_tokens=0,
    )


def summarize_patient(context: dict, model: str = DEFAULT_MODEL):
    """Turn one patient's structured context into a full night-shift summary
    (3-5 sentences). Used by the CLI's `demo` command. Calls a locally
    running Ollama server — free, no API key required.
    """
    return _call_ollama(SUMMARY_SYSTEM_PROMPT, context, model)


def generate_alert(context: dict, model: str = DEFAULT_MODEL):
    """Turn a risk-band escalation into a single urgent alert sentence for
    the dashboard's live notification system. context should include
    "previous_risk_band" (see build_patient_context) so the model can
    reference what changed.
    """
    return _call_ollama(ALERT_SYSTEM_PROMPT, context, model)
