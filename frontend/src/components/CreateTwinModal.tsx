import { useEffect, useState } from 'react';
import {
  SPEECH_FEATURE_DEFINITIONS,
  buildPartialSpeechFeatures,
  buildSyntheticSpeechFeatures,
} from '../api/syntheticSamples';
import { ParkTwinApiError } from '../api/client';
import type { PartialSpeechFeatures, SpeechFeatureKey, TwinCreatePayload } from '../api/types';

interface CreateTwinModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: TwinCreatePayload) => Promise<void>;
}

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}

export function CreateTwinModal({ open, onClose, onSubmit }: CreateTwinModalProps) {
  const [externalReference, setExternalReference] = useState('SYN-NEW-101');
  const [observedAtLocal, setObservedAtLocal] = useState(() =>
    toDatetimeLocalValue(new Date(Date.now() - 14 * 86_400_000)),
  );
  const [allowPartial, setAllowPartial] = useState(false);
  const [observedTotal, setObservedTotal] = useState('30.5');
  const [observedMotor, setObservedMotor] = useState('22.5');
  const [features, setFeatures] = useState<PartialSpeechFeatures>(() =>
    buildSyntheticSpeechFeatures(0.35),
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleFeatureChange = (key: SpeechFeatureKey, raw: string) => {
    setFeatures((prev) => ({
      ...prev,
      [key]: raw.trim() === '' ? null : Number(raw),
    }));
  };

  const loadCompleteSample = () => {
    setAllowPartial(false);
    setFeatures(buildSyntheticSpeechFeatures(0.35));
    setObservedTotal('30.5');
    setObservedMotor('22.5');
  };

  const loadPartialSample = () => {
    setAllowPartial(true);
    setFeatures(buildPartialSpeechFeatures());
    setObservedTotal('28.0');
    setObservedMotor('21.0');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg(null);
    setFieldErrors([]);
    try {
      const isoObservedAt = `${observedAtLocal}:00Z`;
      await onSubmit({
        external_reference: externalReference.trim(),
        observed_at: isoObservedAt,
        features,
        allow_partial: allowPartial,
        observed_total_updrs: observedTotal.trim() === '' ? null : Number(observedTotal),
        observed_motor_updrs: observedMotor.trim() === '' ? null : Number(observedMotor),
        source: 'dashboard',
      });
      onClose();
    } catch (err) {
      if (err instanceof ParkTwinApiError) {
        setErrorMsg(`${err.message} (Code: ${err.code}, Request: ${err.requestId})`);
        setFieldErrors(err.fields.map((f) => `${f.name}: ${f.reason}`));
      } else {
        setErrorMsg('Failed to initialize twin baseline.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-twin-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2 id="create-twin-title">Initialize Baseline Digital Twin</h2>
            <p className="muted-text">
              Enter a pseudonymous token (never a real patient name) and baseline voice metrics.
            </p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close dialog">
            Close
          </button>
        </div>

        <div className="preset-bar">
          <span>Synthetic presets:</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadCompleteSample}>
            Complete 16-Feature Baseline
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadPartialSample}>
            Partial Baseline (Insufficient Data)
          </button>
        </div>

        {errorMsg && (
          <div className="alert alert-error" role="alert">
            <strong>{errorMsg}</strong>
            {fieldErrors.length > 0 && (
              <ul>
                {fieldErrors.map((fe) => (
                  <li key={fe}>{fe}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} className="stack-md">
          <div className="form-grid-2">
            <label className="field">
              <span>Pseudonymous Reference *</span>
              <input
                type="text"
                required
                value={externalReference}
                onChange={(e) => setExternalReference(e.target.value)}
                placeholder="SYN-PT-4001"
                pattern="^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$"
              />
            </label>
            <label className="field">
              <span>Baseline Timestamp (UTC) *</span>
              <input
                type="datetime-local"
                required
                value={observedAtLocal}
                onChange={(e) => setObservedAtLocal(e.target.value)}
              />
            </label>
          </div>

          <div className="form-grid-2">
            <label className="field">
              <span>Observed Total UPDRS (optional)</span>
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
              <span>Observed Motor UPDRS (optional)</span>
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

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={allowPartial}
              onChange={(e) => setAllowPartial(e.target.checked)}
            />
            <span>
              Explicitly allow partial baseline features (marks twin as <code>insufficient_data</code> without fabricating UPDRS)
            </span>
          </label>

          <fieldset className="feature-fieldset">
            <legend>16 Biomedical Speech Metrics</legend>
            <div className="feature-grid">
              {SPEECH_FEATURE_DEFINITIONS.map((def) => (
                <label key={def.key} className="field field-compact">
                  <span>
                    {def.label} <small>({def.unit})</small>
                  </span>
                  <input
                    type="number"
                    step={def.step}
                    min={def.min}
                    max={def.max}
                    required={!allowPartial}
                    value={features[def.key] ?? ''}
                    onChange={(e) => handleFeatureChange(def.key, e.target.value)}
                  />
                </label>
              ))}
            </div>
          </fieldset>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating Twin...' : 'Create Baseline Twin'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
