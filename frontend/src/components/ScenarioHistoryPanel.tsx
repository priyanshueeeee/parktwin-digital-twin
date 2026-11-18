import type { ScenarioListItem } from '../api/types';

interface ScenarioHistoryPanelProps {
  scenarios: ScenarioListItem[];
  activeScenarioId: string | null;
  loading: boolean;
  onOverlayScenario: (scenarioId: string) => void;
  onClearOverlay: () => void;
}

export function ScenarioHistoryPanel({
  scenarios,
  activeScenarioId,
  loading,
  onOverlayScenario,
  onClearOverlay,
}: ScenarioHistoryPanelProps) {
  if (loading && scenarios.length === 0) {
    return (
      <section className="panel" role="status" aria-busy="true">
        Loading saved hypothetical scenarios...
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="scenario-history-heading">
      <div className="panel-header">
        <div>
          <span className="hypothetical-tag">ISOLATED SCENARIO LEDGER</span>
          <h3 id="scenario-history-heading">Saved Hypothetical Scenarios ({scenarios.length})</h3>
          <p className="muted-text">
            Scenarios are stored separately from observed history. Select any scenario to overlay it on the main trajectory chart.
          </p>
        </div>
        {activeScenarioId && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClearOverlay}>
            Clear Active Overlay
          </button>
        )}
      </div>

      {scenarios.length === 0 ? (
        <div className="empty-workspace" role="status">
          <strong>No saved scenarios yet</strong>
          <p>Run an intervention simulation from the Trajectory &amp; Simulation tab to compare regimens here.</p>
        </div>
      ) : (
        <div className="scenario-grid">
          {scenarios.map((sc) => {
            const isActive = sc.scenario_id === activeScenarioId;
            return (
              <article
                key={sc.scenario_id}
                className={`scenario-card ${isActive ? 'scenario-card-active' : ''}`}
              >
                <div className="scenario-card-top">
                  <strong>{sc.label}</strong>
                  <span className="hypothetical-tag">HYPOTHETICAL</span>
                </div>

                <div className="param-chips">
                  <span className="param-chip">
                    Levodopa: {sc.parameters.levodopa_dose_change_mg >= 0 ? '+' : ''}
                    {sc.parameters.levodopa_dose_change_mg} mg
                  </span>
                  <span className="param-chip">
                    PT: {sc.parameters.physical_therapy_sessions_per_week}x/wk
                  </span>
                  <span className="param-chip">
                    Adherence: {Math.round(sc.parameters.adherence_ratio * 100)}%
                  </span>
                  <span className="param-chip">Horizon: {sc.horizon_days}d</span>
                </div>

                <div className="scenario-deltas">
                  <div>
                    <span className="metric-label">Total UPDRS Δ</span>
                    <strong>
                      {sc.summary.delta_total_updrs >= 0 ? '+' : ''}
                      {sc.summary.delta_total_updrs.toFixed(1)} pts
                    </strong>{' '}
                    <span className="muted-text">
                      ({sc.summary.baseline_end_total_updrs.toFixed(1)} → {sc.summary.scenario_end_total_updrs.toFixed(1)})
                    </span>
                  </div>
                  <div>
                    <span className="metric-label">Motor UPDRS Δ</span>
                    <strong>
                      {sc.summary.delta_motor_updrs >= 0 ? '+' : ''}
                      {sc.summary.delta_motor_updrs.toFixed(1)} pts
                    </strong>
                  </div>
                </div>

                <p className="muted-text">
                  Snapshot v{sc.baseline_twin_version} · Assumptions <code>{sc.assumptions_version}</code> ·{' '}
                  {new Date(sc.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}
                </p>

                <div className="action-row">
                  <button
                    type="button"
                    className={`btn btn-sm ${isActive ? 'btn-secondary' : 'btn-simulate'}`}
                    onClick={() => onOverlayScenario(sc.scenario_id)}
                  >
                    {isActive ? 'Currently Overlaid on Chart' : 'Overlay on Chart'}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
