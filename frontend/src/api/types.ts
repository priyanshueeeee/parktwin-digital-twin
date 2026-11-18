export interface SpeechFeatures {
  jitter_percent: number;
  jitter_abs: number;
  jitter_rap: number;
  jitter_ppq5: number;
  jitter_ddp: number;
  shimmer: number;
  shimmer_db: number;
  shimmer_apq3: number;
  shimmer_apq5: number;
  shimmer_apq11: number;
  shimmer_dda: number;
  nhr: number;
  hnr: number;
  rpde: number;
  dfa: number;
  ppe: number;
}

export type SpeechFeatureKey = keyof SpeechFeatures;
export type PartialSpeechFeatures = { [K in SpeechFeatureKey]: number | null };

export interface FieldValidationError {
  name: string;
  reason: string;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  fields: FieldValidationError[];
}

export interface ApiErrorEnvelope {
  request_id: string;
  schema_version: string;
  error: ApiErrorDetail;
}

export interface ApiEnvelope<T> {
  request_id: string;
  schema_version: string;
  data: T;
  warnings: string[];
}

export interface ModelMetadata {
  model_version: string;
  feature_version: string;
  assumptions_version: string;
  adapter_type: 'mock' | 'real';
  artifact_checksum: string;
}

export interface TwinRecord {
  id: string;
  external_reference: string;
  status: 'active' | 'insufficient_data' | 'paused' | 'archived';
  version: number;
  latest_state_id: string | null;
  data_quality_summary: Record<string, unknown>;
  schema_version: string;
  created_at: string;
  updated_at: string;
}

export interface TwinListItem extends TwinRecord {
  observation_count: number;
  last_observed_at: string | null;
  is_stale: boolean;
  latest_total_updrs: number | null;
  latest_motor_updrs: number | null;
  slope_status: 'computed' | 'insufficient_data';
  slope_total_per_30_days: number | null;
}

export interface TwinListData {
  twins: TwinListItem[];
  count: number;
  disclaimer: string;
}

export interface TrajectoryPoint {
  observation_id?: string | null;
  timestamp: string;
  day_offset?: number;
  source_type: 'observed' | 'estimated' | 'simulated';
  total_updrs: number | null;
  motor_updrs: number | null;
  total_updrs_ci_low?: number | null;
  total_updrs_ci_high?: number | null;
  motor_updrs_ci_low?: number | null;
  motor_updrs_ci_high?: number | null;
  scenario_id?: string | null;
  hypothetical?: boolean;
  quality_flags?: string[];
}

export interface SlopeSummary {
  status: 'computed' | 'insufficient_data';
  method: string;
  window_description: string;
  units: string;
  total_updrs_per_30_days: number | null;
  motor_updrs_per_30_days: number | null;
  total_updrs_per_day: number | null;
  motor_updrs_per_day: number | null;
  observation_count_used: number;
  time_span_days: number;
}

export interface DataCoverage {
  total_observations: number;
  estimated_observations: number;
  observed_updrs_count: number;
  first_observed_at: string | null;
  last_observed_at: string | null;
  time_span_days: number;
  is_stale: boolean;
  stale_threshold_days: number;
}

export interface SimulationParameters {
  levodopa_dose_change_mg: number;
  physical_therapy_sessions_per_week: number;
  adherence_ratio: number;
}

export interface SimulationSummary {
  horizon_days: number;
  baseline_end_total_updrs: number;
  scenario_end_total_updrs: number;
  delta_total_updrs: number;
  baseline_end_motor_updrs: number;
  scenario_end_motor_updrs: number;
  delta_motor_updrs: number;
  hypothetical: true;
}

export interface SimulationData {
  scenario_id: string;
  twin_id: string;
  label: string;
  hypothetical: true;
  status: string;
  baseline_twin_version: number;
  parameters: SimulationParameters;
  horizon_days: number;
  step_days: number;
  assumptions_version: string;
  model_version: string;
  baseline_series: TrajectoryPoint[];
  scenario_series: TrajectoryPoint[];
  summary: SimulationSummary;
  created_at: string;
  disclaimer: string;
}

export interface TrajectoryData {
  twin: TwinRecord;
  series_filter: 'all' | 'observed' | 'estimated';
  observed_points: TrajectoryPoint[];
  estimated_points: TrajectoryPoint[];
  scenario: {
    id: string;
    label: string;
    hypothetical: true;
    assumptions_version: string;
    model_version: string;
    baseline_twin_version: number;
    parameters: SimulationParameters;
    horizon_days: number;
    step_days: number;
    baseline_series: TrajectoryPoint[];
    scenario_series: TrajectoryPoint[];
    summary: SimulationSummary;
    created_at: string;
  } | null;
  slope: SlopeSummary;
  coverage: DataCoverage;
  quality_flags: string[];
  model_metadata: ModelMetadata;
  disclaimer: string;
}

export interface TwinCreatePayload {
  external_reference: string;
  observed_at: string;
  features: PartialSpeechFeatures;
  allow_partial: boolean;
  observed_total_updrs: number | null;
  observed_motor_updrs: number | null;
  source?: string;
}

export interface TwinUpdatePayload {
  twin_id: string;
  observed_at: string;
  features: SpeechFeatures;
  observed_total_updrs: number | null;
  observed_motor_updrs: number | null;
  expected_version?: number;
  source?: string;
}

export interface SimulationPayload {
  label: string;
  interventions: SimulationParameters;
  horizon_days: number;
  step_days: number;
  acknowledge_hypothetical: boolean;
}
