import { useState } from 'react';
import {
  SPEECH_FEATURE_DEFINITIONS,
  buildSyntheticSpeechFeatures,
} from '../api/syntheticSamples';
import { ParkTwinApiError } from '../api/client';
import type { SpeechFeatureKey, SpeechFeatures, TwinUpdatePayload } from '../api/types';

interface ObservationFormProps {
  twinId: string;
  twinVersion: number;
  onSubmit: (payload: TwinUpdatePayload) => Promise<void>;
}

function nowDatetimeLocalUtc(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export function ObservationForm({ twinId, twinVersion, onSubmit }: ObservationFormProps) {
  const [observedAtLocal, setObservedAtLocal] = useState(nowDatetimeLocalUtc);
  const [features, setFeatures] = useState<SpeechFeatures>(() => buildSyntheticSpeechFeatures(0.9));
  const [observedTotal, setObservedTotal] = useState('');
  const [observedMotor, setObservedMotor] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleFeatureChange = (key: SpeechFeatureKey, value: string) => {
    setFeatures((prev) => ({ ...prev, [key]: Number(value) }));
  };

  const applyPreset = (severity: number, label: string) => {
    setFeatures(buildSyntheticSpeechFeatures(severity));
    setObservedAtLocal(nowDatetimeLocalUtc());
    setSuccessMsg(`Loaded synthetic preset: ${label}`);
    setErrorMsg(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await onSubmit({
        twin_id: twinId,
        observed_at: `${observedAtLocal}:00Z`,
        features,
        observed_total_updrs: observedTotal.trim() === '' ? null : Number(observedTotal),
        observed_motor_updrs: observedMotor.trim() === '' ? null : Number(observedMotor),
        expected_version: twinVersion,
        source: 'dashboard',
      });
      setSuccessMsg('Observation appended and trajectory recalculated.');
      setObservedTotal('');
      setObservedMotor('');
    } catch (err) {
      if (err instanceof ParkTwinApiError) {
        const fieldSummary = err.fields.map((f) => `${f.name}: ${f.reason}`).join('; ');
        setErrorMsg(
          `${err.message}${fieldSummary ? ` (${fieldSummary})` : ''} [Code: ${err.code}, Req: ${err.requestId}]`,
        );
      } else {
        setErrorMsg('Failed to submit voice observation.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="panel" aria-labelledby="obs-form-heading">
      <div className="panel-header">
        <div>
          <h3 id="obs-form-heading">Submit New Voice Observation</h3>
          <p className="muted-text">
            Appends an immutable observation and recalculates longitudinal state (Twin v{twinVersion}).
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide 16 Speech Inputs' : 'Edit All 16 Speech Inputs'}
        </button>
      </div>

      <div className="preset-bar">
        <span>Synthetic voice sample:</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => applyPreset(0.4, 'Stable')}>
          Stable
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => applyPreset(1.6, 'Worsening')}>
          Worsening
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => applyPreset(0.05, 'Improving')}>
          Improving
        </button>
      </div>

      {errorMsg && (
        <div className="alert alert-error" role="alert">
          {errorMsg}
        </div>
      )}
      {successMsg && (
        <div className="alert alert-success" role="status">
          {successMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="stack-sm">
        <div className="form-grid-3">
          <label className="field">
            <span>Observed At (UTC) *</span>
            <input
              type="datetime-local"
              required
              value={observedAtLocal}
              onChange={(e) => setObservedAtLocal(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Clinical Total UPDRS (optional)</span>
            <input
              type="number"
              step="0.1"
              min="0"
              max="199"
              value={observedTotal}
              onChange={(e) => setObservedTotal(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Clinical Motor UPDRS (optional)</span>
            <input
              type="number"
              step="0.1"
              min="0"
              max="108"
              value={observedMotor}
              onChange={(e) => setObservedMotor(e.target.value)}
            />
          </label>
        </div>

        {expanded && (
          <div className="feature-grid">
            {SPEECH_FEATURE_DEFINITIONS.map((def) => (
              <label key={def.key} className="field field-compact">
                <span>
                  {def.label} <small>({def.unit})</small>
                </span>
                <input
                  type="number"
                  required
                  step={def.step}
                  min={def.min}
                  max={def.max}
                  value={features[def.key]}
                  onChange={(e) => handleFeatureChange(def.key, e.target.value)}
                />
              </label>
            ))}
          </div>
        )}

        <div className="action-row">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Submitting & Recalculating...' : 'Append Voice Observation'}
          </button>
        </div>
      </form>
    </section>
  );
}
