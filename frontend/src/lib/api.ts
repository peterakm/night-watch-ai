import type { AlertNotification, Config, Patient, ShiftInfo } from "../types";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as { detail?: string });
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getConfig: () => request<Config>("/api/config"),
  startShift: (patients: number) =>
    request<ShiftInfo>("/api/shift/start", {
      method: "POST",
      body: JSON.stringify({ patients }),
    }),
  stopShift: () => request<ShiftInfo>("/api/shift/stop", { method: "POST" }),
  getShift: () => request<ShiftInfo>("/api/shift"),
  listPatients: () => request<Patient[]>("/api/patients"),
  getPatient: (id: string) => request<Patient>(`/api/patients/${id}`),
  listNotifications: () => request<AlertNotification[]>("/api/notifications"),
  markChecking: (id: string) =>
    request<AlertNotification>(`/api/notifications/${id}/checking`, { method: "POST" }),
  markChecked: (id: string) =>
    request<AlertNotification>(`/api/notifications/${id}/checked`, { method: "POST" }),
  clearNotifications: () => request<{ cleared: boolean }>("/api/notifications/clear", { method: "POST" }),
};
