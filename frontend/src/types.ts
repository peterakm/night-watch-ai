export type RiskBand = "low" | "low-medium" | "medium" | "high";

export interface LatestVitals {
  heart_rate_bpm: number;
  respiratory_rate_bpm: number;
  spo2_pct: number;
  temp_c: number;
  systolic_bp_mmhg: number;
  diastolic_bp_mmhg: number;
}

export interface VitalsHistoryPoint {
  timestamp: string;
  heart_rate: number;
  respiratory_rate: number;
  spo2: number;
  temp_c: number;
  systolic_bp: number;
  diastolic_bp: number;
}

export interface EarlyWarningScore {
  total_score: number;
  risk_band: RiskBand;
  subscores: Record<string, number>;
  abnormal_parameter_flags: string[];
}

export interface Patient {
  patient_id: string;
  name: string;
  age: number;
  room: string;
  reading_time: string;
  readings_this_shift: number;
  latest_vitals: LatestVitals;
  vitals_history: VitalsHistoryPoint[];
  early_warning_score: EarlyWarningScore;
  sustained_risk_band: RiskBand;
  trend_flags: string[];
  used_population_baseline_fallback: boolean;
}

export interface ShiftInfo {
  generated_at: string;
  start_time: string;
  stopped_at: string | null;
  running: boolean;
  patient_count: number;
  provider: string;
  model: string;
  current_step: number;
  sim_time: string;
}

export type AlertStatus = "new" | "checking" | "checked";

export interface AlertNotification {
  id: string;
  patient_id: string;
  patient_name: string;
  room: string;
  risk_band: RiskBand;
  previous_risk_band: RiskBand;
  message: string;
  created_at: string;
  status: AlertStatus;
}

export interface Config {
  provider: string;
  model: string;
}
