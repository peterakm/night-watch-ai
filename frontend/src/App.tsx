import { useCallback, useEffect, useRef, useState } from "react";
import "./theme.css";
import "./App.css";
import { api } from "./lib/api";
import { playAlertChime } from "./lib/audio";
import {
  notificationPermission,
  notificationsSupported,
  requestNotificationPermission,
  showBrowserNotification,
} from "./lib/pushNotify";
import type { AlertNotification, Patient, ShiftInfo } from "./types";
import { PatientCard } from "./components/PatientCard";
import { PatientDetail } from "./components/PatientDetail";
import { NotificationPanel } from "./components/NotificationPanel";
import { ShiftClock } from "./components/ShiftClock";
import { ToastStack } from "./components/Toast";

type Theme = "system" | "light" | "dark";

const POLL_MS = 2500;
const TOAST_LIFETIME_MS = 9000;

function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    if (theme === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }, [theme]);
  return [theme, setTheme];
}

function App() {
  const [theme, setTheme] = useTheme();
  const [shiftInfo, setShiftInfo] = useState<ShiftInfo | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [notifications, setNotifications] = useState<AlertNotification[]>([]);
  const [toasts, setToasts] = useState<AlertNotification[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [togglingShift, setTogglingShift] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [numPatientsText, setNumPatientsText] = useState("6");
  const [notifPermission, setNotifPermission] = useState(notificationPermission());

  const knownNotificationIds = useRef<Set<string>>(new Set());

  const refreshAll = useCallback(async () => {
    try {
      const [shiftRes, patientsRes, notificationsRes] = await Promise.all([
        api.getShift(),
        api.listPatients(),
        api.listNotifications(),
      ]);
      setShiftInfo(shiftRes);
      setPatients(patientsRes);

      const unseen = notificationsRes.filter((n) => !knownNotificationIds.current.has(n.id));
      if (unseen.length > 0 && knownNotificationIds.current.size > 0) {
        // Skip the toast/sound/push burst on the very first load of an
        // already-running shift — only genuinely new alerts should interrupt.
        setToasts((prev) => [...unseen, ...prev]);
        playAlertChime();
        for (const n of unseen) {
          showBrowserNotification(
            `${n.risk_band.toUpperCase()} risk: ${n.patient_name} (Room ${n.room})`,
            n.message,
          );
        }
        for (const n of unseen) {
          setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== n.id));
          }, TOAST_LIFETIME_MS);
        }
      }
      notificationsRes.forEach((n) => knownNotificationIds.current.add(n.id));
      setNotifications(notificationsRes);
    } catch {
      setShiftInfo(null);
      setPatients([]);
    }
  }, []);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, POLL_MS);
    return () => clearInterval(interval);
  }, [refreshAll]);

  const handleStart = async () => {
    const patientsCount = Math.min(200, Math.max(1, parseInt(numPatientsText, 10) || 6));
    setTogglingShift(true);
    setError(null);
    try {
      knownNotificationIds.current = new Set();
      setToasts([]);
      setSelectedId(null);
      await api.startShift(patientsCount);
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start monitoring");
    } finally {
      setTogglingShift(false);
    }
  };

  const handleStop = async () => {
    setTogglingShift(true);
    setError(null);
    try {
      await api.stopShift();
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop monitoring");
    } finally {
      setTogglingShift(false);
    }
  };

  const handleMarkChecking = async (id: string) => {
    try {
      const updated = await api.markChecking(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? updated : n)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update alert");
    }
  };

  const handleMarkChecked = async (id: string) => {
    try {
      const updated = await api.markChecked(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? updated : n)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update alert");
    }
  };

  const handleClearAll = async () => {
    try {
      await api.clearNotifications();
      setNotifications([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear alerts");
    }
  };

  const handleEnableNotifications = async () => {
    const permission = await requestNotificationPermission();
    setNotifPermission(permission);
  };

  const selected = patients.find((p) => p.patient_id === selectedId) ?? null;
  const highRiskCount = patients.filter((p) => p.sustained_risk_band === "high").length;
  const isRunning = shiftInfo?.running ?? false;

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1>Night Watch AI</h1>
          <p className="app__subtitle">
            Live overnight ward monitoring
          </p>
        </div>

        <div className="app__controls">
          {shiftInfo && <ShiftClock shift={shiftInfo} />}

          <label className="control">
            Patients
            <input
              type="text"
              inputMode="numeric"
              value={numPatientsText}
              disabled={isRunning}
              onChange={(e) => setNumPatientsText(e.target.value.replace(/[^0-9]/g, ""))}
            />
          </label>

          {isRunning ? (
            <button type="button" className="btn btn--stop" onClick={handleStop} disabled={togglingShift}>
              {togglingShift ? "Stopping…" : "Stop monitoring"}
            </button>
          ) : (
            <button type="button" className="btn btn--primary" onClick={handleStart} disabled={togglingShift}>
              {togglingShift ? "Starting…" : "Start monitoring"}
            </button>
          )}

          {notificationsSupported() && notifPermission !== "granted" && (
            <button type="button" className="btn" onClick={handleEnableNotifications}>
              Enable desktop alerts
            </button>
          )}

          <select
            className="theme-select"
            value={theme}
            onChange={(e) => setTheme(e.target.value as Theme)}
            aria-label="Theme"
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
      </header>

      {error && <div className="banner banner--error">{error}</div>}

      {!shiftInfo ? (
        <div className="empty-state">
          <p>Monitoring is off. Click &ldquo;Start monitoring&rdquo; to begin.</p>
        </div>
      ) : (
        <div className="layout">
          <aside className="ward-list">
            {!isRunning && (
              <div className="banner banner--stopped">
                Monitoring stopped. Showing the ward as it was when turned off.
              </div>
            )}
            {highRiskCount > 0 && (
              <div className="banner banner--critical">
                {highRiskCount} patient{highRiskCount > 1 ? "s" : ""} at HIGH risk
              </div>
            )}
            {patients.map((p) => (
              <PatientCard
                key={p.patient_id}
                patient={p}
                selected={p.patient_id === selectedId}
                onSelect={() => setSelectedId(p.patient_id)}
              />
            ))}
          </aside>
          <main className="detail-pane">
            {selected ? (
              <PatientDetail patient={selected} />
            ) : (
              <div className="empty-state">Select a patient to see full detail.</div>
            )}
          </main>
          <NotificationPanel
            notifications={notifications}
            viewingHighRiskPatient={selected?.sustained_risk_band === "high"}
            onSelectPatient={setSelectedId}
            onMarkChecking={handleMarkChecking}
            onMarkChecked={handleMarkChecked}
            onClearAll={handleClearAll}
          />
        </div>
      )}

      <ToastStack
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))}
        onSelectPatient={setSelectedId}
      />
    </div>
  );
}

export default App;
