import type { Patient } from "../types";
import { RiskBadge } from "./RiskBadge";
import { StatTile } from "./StatTile";

const RISK_ORDER = { high: 0, medium: 1, "low-medium": 2, low: 3 };

export function PatientDetail({ patient }: { patient: Patient }) {
  const ews = patient.early_warning_score;
  const v = patient.latest_vitals;
  const abnormal = new Set(
    Object.entries(ews.subscores)
      .filter(([, score]) => score >= 2)
      .map(([key]) => key),
  );
  const recovering = RISK_ORDER[patient.sustained_risk_band] < RISK_ORDER[ews.risk_band];

  return (
    <div className="detail">
      <div className="detail__header">
        <div>
          <h2>{patient.name}</h2>
          <div className="detail__meta">
            Room {patient.room} &middot; Age {patient.age} &middot; {patient.readings_this_shift}{" "}
            readings this shift
          </div>
        </div>
        <div className="detail__risk">
          <RiskBadge band={patient.sustained_risk_band} />
          {recovering && (
            <span className="muted muted--small">this reading looks better &mdash; still watching</span>
          )}
        </div>
      </div>

      <div className="stat-grid">
        <StatTile
          label="Heart rate"
          value={v.heart_rate_bpm}
          unit=" bpm"
          abnormal={abnormal.has("heart_rate")}
        />
        <StatTile
          label="Respiratory rate"
          value={v.respiratory_rate_bpm}
          unit=" /min"
          abnormal={abnormal.has("respiratory_rate")}
        />
        <StatTile label="SpO2" value={v.spo2_pct} unit="%" abnormal={abnormal.has("spo2")} />
        <StatTile
          label="Temperature"
          value={v.temp_c}
          unit="&deg;C"
          abnormal={abnormal.has("temp_c")}
        />
        <StatTile
          label="Systolic BP"
          value={v.systolic_bp_mmhg}
          unit=" mmHg"
          abnormal={abnormal.has("systolic_bp")}
        />
        <StatTile label="Diastolic BP" value={v.diastolic_bp_mmhg} unit=" mmHg" />
      </div>

      <section className="detail__section">
        <h3>Why this risk level</h3>
        {ews.abnormal_parameter_flags.length > 0 ? (
          <ul className="flag-list flag-list--acute">
            {ews.abnormal_parameter_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nothing abnormal on this reading.</p>
        )}
      </section>

      <section className="detail__section">
        <h3>Change from earlier tonight</h3>
        {patient.trend_flags.length > 0 ? (
          <ul className="flag-list flag-list--trend">
            {patient.trend_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No significant drift from baseline.</p>
        )}
        {patient.used_population_baseline_fallback && (
          <p className="muted muted--small">
            Compared against elderly population norms &mdash; not enough readings yet this shift
            for a personal baseline.
          </p>
        )}
      </section>

      <p className="disclaimer">
        Decision support, not a diagnosis. This ward's live alerts (see the panel) tell you when
        to check someone &mdash; verify in person before acting on a medium or high risk band.
      </p>
    </div>
  );
}
