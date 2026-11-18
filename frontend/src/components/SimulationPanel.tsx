import { useState } from 'react';
import { ParkTwinApiError } from '../api/client';
import type { SimulationData, SimulationPayload } from '../api/types';

interface SimulationPanelProps {
  canSimulate: boolean;
  activeSimulation: SimulationData | null;
  pending: boolean;
  onRunSimulation: (payload: SimulationPayload) => Promise<void>;
  onResetSimulation: () => void;
}

export function SimulationPanel({
  canSimulate,
  activeSimulation,
  pending,
  onRunSimulation,
  onResetSimulation,
}: SimulationPanelProps) {
  const [label, setLabel] = useState('Levodopa + Physical Therapy Scenario');
  const [levodopaDelta, setLevodopaDelta] = useState(150);
  const [ptSessions, setPtSessions] = useState(3);
  const [adherencePercent, setAdherencePercent] = useState(90);
  const [horizonDays, setHorizonDays] = useState(90);
  const [stepDays, setStepDays] = useState(15);
  const [acknowledge, setAcknowledge] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    try {
      await onRunSimulation({
        label: label.trim() || 'Hypothetical Scenario',
        interventions: {
          levodopa_dose_change_mg: levodopaDelta,
          physical_therapy_sessions_per_week: ptSessions,
          adherence_ratio: Number((adherencePercent / 100).toFixed(2)),
        },
        horizon_days: horizonDays,
        step_days: stepDays,
        acknowledge_hypothetical: acknowledge,
      });
    } catch (err) {
      if (err instanceof ParkTwinApiError) {
        setErrorMsg(`${err.message} [Code: ${err.code}, Req: ${err.requestId}]`);
      } else {
        setErrorMsg('Failed to execute simulation scenario.');
      }
    }
  };

  return (
    <section className="panel simulation-panel" aria-labelledby="sim-panel-heading">
      <div className="panel-header">
        <div>
          <span className="hypothetical-tag">HYPOTHETICAL SANDBOX · READ-ONLY</span>
          <h3 id="sim-panel-heading">Intervention Scenario Simulator</h3>
          <p className="muted-text">
            Explores prototype what-if assumptions without modifying observed history or twin state.
          </p>
        </div>
        {activeSimulation && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onResetSimulation}
            disabled={pending}
          >
            Reset Scenario
          </button>
        )}
      </div>

      {!canSimulate && (
        <div className="alert alert-warn" role="status">
          At least one complete estimated speech observation is required before running a scenario simulation.
        </div>
      )}

      {errorMsg && (
        <div className="alert alert-error" role="alert">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="stack-sm">
        <label className="field">
          <span>Scenario Label</span>
          <input
            type="text"
            value={label}
            maxLength={128}
            onChange={(e) => setLabel(e.target.value)}
            disabled={!canSimulate}
          />
        </label>

        <div className="slider-grid">
          <label className="field">
            <span>
              Levodopa Dose Change: <strong>{levodopaDelta >= 0 ? `+${levodopaDelta}` : levodopaDelta} mg/day</strong>
            </span>
            <input
              type="range"
              min={-300}
              max={600}
              step={25}
              value={levodopaDelta}
              onChange={(e) => setLevodopaDelta(Number(e.target.value))}
              disabled={!canSimulate}
              aria-label="Levodopa dose change in milligrams per day"
            />
            <span className="range-caption">-300 mg to +600 mg</span>
          </label>

          <label className="field">
            <span>
              Physical Therapy: <strong>{ptSessions} sessions/week</strong>
            </span>
            <input
              type="range"
              min={0}
              max={7}
              step={1}
              value={ptSessions}
              onChange={(e) => setPtSessions(Number(e.target.value))}
              disabled={!canSimulate}
              aria-label="Physical therapy sessions per week"
            />
            <span className="range-caption">0 to 7 sessions/week</span>
          </label>

          <label className="field">
            <span>
              Assumed Adherence: <strong>{adherencePercent}%</strong>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={adherencePercent}
              onChange={(e) => setAdherencePercent(Number(e.target.value))}
              disabled={!canSimulate}
              aria-label="Assumed adherence percentage"
            />
            <span className="range-caption">0% to 100%</span>
          </label>
        </div>

        <div className="form-grid-2">
          <label className="field">
            <span>Forecast Horizon (days)</span>
            <input
              type="number"
              min={7}
              max={180}
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value))}
              disabled={!canSimulate}
            />
          </label>
          <label className="field">
            <span>Step Size (days)</span>
            <input
              type="number"
              min={1}
              max={30}
              value={stepDays}
              onChange={(e) => setStepDays(Number(e.target.value))}
              disabled={!canSimulate}
            />
          </label>
        </div>

        <label className="checkbox-row ack-box">
          <input
            type="checkbox"
            checked={acknowledge}
            onChange={(e) => setAcknowledge(e.target.checked)}
            disabled={!canSimulate}
          />
          <span>
            I acknowledge this output is <strong>hypothetical</strong>, non-diagnostic, and does not
            constitute medication or treatment advice.
          </span>
        </label>

        <div className="action-row">
          <button
            type="submit"
            className="btn btn-simulate"
            disabled={!canSimulate || !acknowledge || pending}
          >
            {pending ? 'Running Hypothetical Simulation...' : 'Run Simulation'}
          </button>
          {activeSimulation && (
            <button type="button" className="btn btn-secondary" onClick={onResetSimulation}>
              Clear Overlay
            </button>
          )}
        </div>
      </form>

      {activeSimulation && (
        <div className="sim-summary-box" role="region" aria-label="Hypothetical simulation summary">
          <div className="sim-summary-head">
            <strong>{activeSimulation.label}</strong>
            <span className="hypothetical-tag">HYPOTHETICAL RESULT</span>
          </div>
          <div className="sim-summary-grid">
            <div>
              <span className="metric-label">Projected Total UPDRS (Day {activeSimulation.summary.horizon_days})</span>
              <div>
                Baseline: <strong>{activeSimulation.summary.baseline_end_total_updrs.toFixed(1)}</strong> →
                Scenario: <strong>{activeSimulation.summary.scenario_end_total_updrs.toFixed(1)}</strong>{' '}
                (Δ {activeSimulation.summary.delta_total_updrs >= 0 ? '+' : ''}
                {activeSimulation.summary.delta_total_updrs.toFixed(1)})
              </div>
            </div>
            <div>
              <span className="metric-label">Projected Motor UPDRS (Day {activeSimulation.summary.horizon_days})</span>
              <div>
                Baseline: <strong>{activeSimulation.summary.baseline_end_motor_updrs.toFixed(1)}</strong> →
                Scenario: <strong>{activeSimulation.summary.scenario_end_motor_updrs.toFixed(1)}</strong>{' '}
                (Δ {activeSimulation.summary.delta_motor_updrs >= 0 ? '+' : ''}
                {activeSimulation.summary.delta_motor_updrs.toFixed(1)})
              </div>
            </div>
          </div>
          <p className="muted-text">
            Assumptions: <code>{activeSimulation.assumptions_version}</code> · Model:{' '}
            <code>{activeSimulation.model_version}</code> · Snapshot twin version: v
            {activeSimulation.baseline_twin_version}
          </p>
        </div>
      )}
    </section>
  );
}
