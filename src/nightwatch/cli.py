"""Command-line entry point for Night Watch AI.

Usage:
    python -m nightwatch.cli demo [--patients N] [--hours H]
    python -m nightwatch.cli calibrate --csv path/to/human_vital_signs_dataset_2024.csv
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Must run before importing nightwatch.summarize, which reads
# NIGHTWATCH_MODEL from the environment at import time.
load_dotenv()

from nightwatch import data as nwdata
from nightwatch import scoring
from nightwatch.summarize import DEFAULT_MODEL, build_patient_context, summarize_patient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINES_PATH = PROJECT_ROOT / "data" / "processed" / "elderly_baselines.json"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _load_active_baselines():
    calibrated = nwdata.load_baselines(BASELINES_PATH)
    if calibrated:
        return calibrated["vitals"]
    return nwdata.DEFAULT_ELDERLY_BASELINES["vitals"]


def run_demo(num_patients: int, hours: float, model: str):
    population_baseline = _load_active_baselines()

    patients, vitals_df = nwdata.generate_synthetic_night(num_patients=num_patients, hours=hours)
    print(f"Model: {model}")
    print(f"Generated {len(vitals_df)} readings across {len(patients)} patients "
          f"over a {hours:.0f}-hour shift.\n")

    report_lines = [
        f"# Night Watch AI — Shift Summary",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · Model: {model}",
        "",
        "> AI-generated decision-support summary. Not a diagnosis. Verify any "
        "flagged patient in person before acting.",
        "",
    ]

    for patient in patients:
        patient_df = vitals_df[vitals_df["patient_id"] == patient.patient_id].sort_values("timestamp")
        latest = patient_df.iloc[-1]
        history_before_latest = patient_df.iloc[:-1]

        vital_score = scoring.score_vitals(latest.to_dict())

        baseline = scoring.personal_baseline(history_before_latest)
        used_population_fallback = baseline is None
        baseline = baseline or population_baseline
        flags = scoring.trend_flags(latest.to_dict(), baseline)

        context = build_patient_context(
            patient={
                "patient_id": patient.patient_id,
                "name": patient.name,
                "age": patient.age,
                "room": patient.room,
            },
            reading=latest.to_dict(),
            vital_score=vital_score,
            trend_flags=flags,
            readings_this_shift=len(patient_df),
        )
        if used_population_fallback:
            context["personal_trend_flags_note"] = (
                "Not enough readings yet this shift for a personal baseline; "
                "compared against elderly population norms instead."
            )

        result = summarize_patient(context, model=model)

        header = f"## Room {patient.room} — {patient.name} (age {patient.age}) — {vital_score.risk_band.upper()}"
        print(header)
        print(result.text)
        print(
            f"[tokens: {result.input_tokens} in / {result.output_tokens} out / "
            f"{result.cache_read_tokens} cached]\n"
        )

        report_lines += [header, "", result.text, ""]

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"shift_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report written to {out_path}")


def run_calibrate(csv_path: str):
    df = nwdata.load_kaggle_csv(csv_path)
    baselines = nwdata.compute_population_baselines(df, min_age=65)
    nwdata.save_baselines(baselines, BASELINES_PATH)
    print(f"Calibrated from {baselines['source_rows']} elderly (65+) rows in {csv_path}")
    print(f"Saved to {BASELINES_PATH}")
    for vital, stats in baselines["vitals"].items():
        print(f"  {vital}: mean={stats['mean']:.2f} std={stats['std']:.2f}")


def main():
    parser = argparse.ArgumentParser(prog="nightwatch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="Run a synthetic overnight shift demo")
    demo_parser.add_argument("--patients", type=int, default=5)
    demo_parser.add_argument("--hours", type=float, default=9.0)  # 11pm - 8am
    demo_parser.add_argument("--model", type=str, default=None, help="Defaults to DEFAULT_MODEL (Ollama)")

    calibrate_parser = subparsers.add_parser(
        "calibrate", help="Compute elderly population baselines from a real Kaggle CSV"
    )
    calibrate_parser.add_argument("--csv", type=str, required=True)

    args = parser.parse_args()

    if args.command == "demo":
        model = args.model or DEFAULT_MODEL
        run_demo(num_patients=args.patients, hours=args.hours, model=model)
    elif args.command == "calibrate":
        run_calibrate(args.csv)


if __name__ == "__main__":
    main()
