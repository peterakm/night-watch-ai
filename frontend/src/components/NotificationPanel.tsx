import type { AlertNotification, RiskBand } from "../types";
import { RiskBadge } from "./RiskBadge";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function NotifItem({
  n,
  onSelectPatient,
  onMarkChecking,
  onMarkChecked,
}: {
  n: AlertNotification;
  onSelectPatient: (patientId: string) => void;
  onMarkChecking: (id: string) => void;
  onMarkChecked: (id: string) => void;
}) {
  return (
    <li
      className={`notif-item notif-item--${n.risk_band}${n.status === "checked" ? " notif-item--checked" : ""}`}
    >
      <button type="button" className="notif-item__main" onClick={() => onSelectPatient(n.patient_id)}>
        <div className="notif-item__top">
          <span className="notif-item__patient">
            {n.patient_name} &middot; Room {n.room}
          </span>
          <RiskBadge band={n.risk_band} />
        </div>
        <p className="notif-item__message">{n.message}</p>
        <div className="notif-item__meta">
          {timeAgo(n.created_at)}
          {n.status === "checking" && <span className="notif-item__tag">On my way</span>}
          {n.status === "checked" && <span className="notif-item__tag notif-item__tag--done">Checked</span>}
        </div>
      </button>

      {n.status === "new" && (
        <button
          type="button"
          className="notif-item__action"
          onClick={() => onMarkChecking(n.id)}
          title="I'm going to check on this patient"
        >
          Checking
        </button>
      )}
      {n.status === "checking" && (
        <button
          type="button"
          className="notif-item__action notif-item__action--done"
          onClick={() => onMarkChecked(n.id)}
          title="I've checked on this patient"
        >
          Checked
        </button>
      )}
    </li>
  );
}

function NotifColumn({
  title,
  badgeBand,
  showBadge,
  notifications,
  emptyText,
  ...itemProps
}: {
  title: string;
  badgeBand: RiskBand;
  showBadge: boolean;
  notifications: AlertNotification[];
  emptyText: string;
  onSelectPatient: (patientId: string) => void;
  onMarkChecking: (id: string) => void;
  onMarkChecked: (id: string) => void;
}) {
  const openCount = notifications.filter((n) => n.status !== "checked").length;

  return (
    <div className="notif-column">
      <div className="notif-column__head">
        <h3>{title}</h3>
        {showBadge && openCount > 0 && (
          <span className={`notif-column__count notif-column__count--${badgeBand}`}>{openCount}</span>
        )}
      </div>
      {notifications.length === 0 ? (
        <p className="muted notif-panel__empty">{emptyText}</p>
      ) : (
        <ul className="notif-list">
          {notifications.map((n) => (
            <NotifItem key={n.id} n={n} {...itemProps} />
          ))}
        </ul>
      )}
    </div>
  );
}

const NON_HIGH_ORDER: Partial<Record<RiskBand, number>> = { medium: 0, "low-medium": 1 };

export function NotificationPanel({
  notifications,
  viewingHighRiskPatient,
  onSelectPatient,
  onMarkChecking,
  onMarkChecked,
  onClearAll,
}: {
  notifications: AlertNotification[];
  viewingHighRiskPatient: boolean;
  onSelectPatient: (patientId: string) => void;
  onMarkChecking: (id: string) => void;
  onMarkChecked: (id: string) => void;
  onClearAll: () => void;
}) {
  const highAlerts = notifications.filter((n) => n.risk_band === "high");
  const otherAlerts = notifications
    .filter((n) => n.risk_band !== "high")
    .sort((a, b) => (NON_HIGH_ORDER[a.risk_band] ?? 9) - (NON_HIGH_ORDER[b.risk_band] ?? 9));

  const itemProps = { onSelectPatient, onMarkChecking, onMarkChecked };

  return (
    <div className="notif-panel">
      <div className="notif-panel__head">
        <h2>Alerts</h2>
        {notifications.length > 0 && (
          <button type="button" className="btn btn--ghost" onClick={onClearAll}>
            Clear all
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <p className="muted notif-panel__empty">
          No alerts yet. You&rsquo;ll be notified the moment a patient&rsquo;s risk level rises.
        </p>
      ) : (
        <div className="notif-columns">
          <NotifColumn
            title="High — go now"
            badgeBand="high"
            showBadge={!viewingHighRiskPatient}
            notifications={highAlerts}
            emptyText="No high-risk alerts."
            {...itemProps}
          />
          <NotifColumn
            title="Medium & Low-Medium"
            badgeBand="medium"
            showBadge
            notifications={otherAlerts}
            emptyText="Nothing else needs a look."
            {...itemProps}
          />
        </div>
      )}
    </div>
  );
}
