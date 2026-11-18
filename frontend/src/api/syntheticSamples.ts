import type { PartialSpeechFeatures, SpeechFeatureKey, SpeechFeatures } from './types';

export interface SpeechFeatureDefinition {
  key: SpeechFeatureKey;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
}

export const SPEECH_FEATURE_DEFINITIONS: SpeechFeatureDefinition[] = [
  { key: 'jitter_percent', label: 'Jitter (%)', unit: 'ratio', min: 0, max: 1, step: 0.0001 },
  { key: 'jitter_abs', label: 'Jitter (Abs)', unit: 'sec', min: 0, max: 0.01, step: 0.000001 },
  { key: 'jitter_rap', label: 'Jitter:RAP', unit: 'ratio', min: 0, max: 1, step: 0.0001 },
  { key: 'jitter_ppq5', label: 'Jitter:PPQ5', unit: 'ratio', min: 0, max: 1, step: 0.0001 },
  { key: 'jitter_ddp', label: 'Jitter:DDP', unit: 'ratio', min: 0, max: 3, step: 0.0001 },
  { key: 'shimmer', label: 'Shimmer', unit: 'ratio', min: 0, max: 1, step: 0.001 },
  { key: 'shimmer_db', label: 'Shimmer (dB)', unit: 'dB', min: 0, max: 10, step: 0.01 },
  { key: 'shimmer_apq3', label: 'Shimmer:APQ3', unit: 'ratio', min: 0, max: 1, step: 0.001 },
  { key: 'shimmer_apq5', label: 'Shimmer:APQ5', unit: 'ratio', min: 0, max: 1, step: 0.001 },
  { key: 'shimmer_apq11', label: 'Shimmer:APQ11', unit: 'ratio', min: 0, max: 1, step: 0.001 },
  { key: 'shimmer_dda', label: 'Shimmer:DDA', unit: 'ratio', min: 0, max: 3, step: 0.001 },
  { key: 'nhr', label: 'NHR', unit: 'ratio', min: 0, max: 5, step: 0.001 },
  { key: 'hnr', label: 'HNR', unit: 'dB', min: 0, max: 60, step: 0.1 },
  { key: 'rpde', label: 'RPDE', unit: 'index', min: 0, max: 1, step: 0.01 },
  { key: 'dfa', label: 'DFA', unit: 'exp', min: 0, max: 1.5, step: 0.01 },
  { key: 'ppe', label: 'PPE', unit: 'index', min: 0, max: 2, step: 0.01 },
];

export function buildSyntheticSpeechFeatures(severityStep = 0.4): SpeechFeatures {
  const s = Math.max(-0.4, Math.min(3.0, severityStep));
  return {
    jitter_percent: Number((0.0045 + 0.0022 * s).toFixed(6)),
    jitter_abs: Number((0.000032 + 0.000014 * s).toFixed(6)),
    jitter_rap: Number((0.0023 + 0.0011 * s).toFixed(6)),
    jitter_ppq5: Number((0.0026 + 0.0012 * s).toFixed(6)),
    jitter_ddp: Number((0.0069 + 0.0033 * s).toFixed(6)),
    shimmer: Number((0.028 + 0.014 * s).toFixed(6)),
    shimmer_db: Number((0.27 + 0.12 * s).toFixed(6)),
    shimmer_apq3: Number((0.015 + 0.007 * s).toFixed(6)),
    shimmer_apq5: Number((0.017 + 0.008 * s).toFixed(6)),
    shimmer_apq11: Number((0.022 + 0.01 * s).toFixed(6)),
    shimmer_dda: Number((0.045 + 0.021 * s).toFixed(6)),
    nhr: Number((0.018 + 0.012 * s).toFixed(6)),
    hnr: Number(Math.max(8, 22.8 - 1.7 * s).toFixed(4)),
    rpde: Number(Math.min(0.95, 0.48 + 0.06 * s).toFixed(4)),
    dfa: Number(Math.min(1.2, 0.68 + 0.03 * s).toFixed(4)),
    ppe: Number(Math.min(1.5, 0.19 + 0.05 * s).toFixed(4)),
  };
}

export function buildPartialSpeechFeatures(): PartialSpeechFeatures {
  return {
    jitter_percent: 0.0051,
    jitter_abs: 0.000036,
    jitter_rap: null,
    jitter_ppq5: null,
    jitter_ddp: null,
    shimmer: 0.031,
    shimmer_db: 0.29,
    shimmer_apq3: null,
    shimmer_apq5: null,
    shimmer_apq11: null,
    shimmer_dda: null,
    nhr: 0.02,
    hnr: 21.8,
    rpde: null,
    dfa: null,
    ppe: null,
  };
}
