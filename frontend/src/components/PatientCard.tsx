import type { Patient } from "../types";
import { RiskBadge } from "./RiskBadge";

const RISK_ORDER = { high: 0, medium: 1, "low-medium": 2, low: 3 };

export function PatientCard({
  patient,
  selected,
  onSelect,
}: {
  patient: Patient;
  selected: boolean;
  onSelect: () => void;
}) {
  const ews = patient.early_warning_score;
  const v = patient.latest_vitals;
  const recovering = RISK_ORDER[patient.sustained_risk_band] < RISK_ORDER[ews.risk_band];

  return (
    <button
      type="button"
      className={`patient-card${selected ? " patient-card--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <div className="patient-card__top">
        <div>
          <div className="patient-card__name">{patient.name}</div>
          <div className="patient-card__meta">
            Room {patient.room} &middot; Age {patient.age}
          </div>
        </div>
        <RiskBadge band={patient.sustained_risk_band} />
      </div>
      <div className="patient-card__vitals">
        <span>HR {v.heart_rate_bpm}</span>
        <span>RR {v.respiratory_rate_bpm}</span>
        <span>SpO2 {v.spo2_pct}%</span>
      </div>
      {ews.abnormal_parameter_flags.length > 0 && (
        <div className="patient-card__flag">{ews.abnormal_parameter_flags[0]}</div>
      )}
      {recovering && <div className="patient-card__recovering">Improving this reading</div>}
    </button>
  );
}
