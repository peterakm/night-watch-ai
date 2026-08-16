import type { AlertNotification } from "../types";
import { RiskBadge } from "./RiskBadge";

export function ToastStack({
  toasts,
  onDismiss,
  onSelectPatient,
}: {
  toasts: AlertNotification[];
  onDismiss: (id: string) => void;
  onSelectPatient: (patientId: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack" role="region" aria-label="New alerts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.risk_band}`}>
          <button
            type="button"
            className="toast__main"
            onClick={() => {
              onSelectPatient(t.patient_id);
              onDismiss(t.id);
            }}
          >
            <div className="toast__top">
              <span className="toast__patient">
                {t.patient_name} &middot; Room {t.room}
              </span>
              <RiskBadge band={t.risk_band} />
            </div>
            <p className="toast__message">{t.message}</p>
          </button>
          <button
            type="button"
            className="toast__dismiss"
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  );
}
