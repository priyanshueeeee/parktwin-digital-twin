import { SPEECH_FEATURE_DEFINITIONS } from '../api/syntheticSamples';
import type { ObservationsData } from '../api/types';

interface VoiceProfilePanelProps {
  data: ObservationsData | null;
  loading: boolean;
}

const FEATURE_LABELS = Object.fromEntries(
  SPEECH_FEATURE_DEFINITIONS.map((d) => [d.key, { label: d.label, unit: d.unit }]),
);

export function VoiceProfilePanel({ data, loading }: VoiceProfilePanelProps) {
  if (loading && !data) {
    return (
      <section className="panel" role="status" aria-busy="true">
        Loading immutable observation history and voice biomarker profile...
      </section>
    );
  }

  if (!data || data.observations.length === 0) {
    return (
      <section className="panel empty-workspace" role="status">
        <strong>No voice observations recorded</strong>
        <p>Append a voice observation to inspect acoustic biomarker drift and model lineage.</p>
      </section>
    );
  }

  return (
    <div className="stack-md">
      <section className="panel" aria-labelledby="biomarker-drift-heading">
        <div className="panel-header">
          <div>
            <h3 id="biomarker-drift-heading">Acoustic Biomarker Drift (Baseline → Latest Complete)</h3>
            <p className="muted-text">
              Key dysphonia metrics driving speech-to-UPDRS estimation across longitudinal recordings.
            </p>
          </div>
        </div>

        {data.biomarker_deltas.length === 0 ? (
          <p className="muted-text">
            Complete 16-feature speech recordings are needed to compute biomarker deltas.
          </p>
        ) : (
          <div className="biomarker-grid">
            {data.biomarker_deltas.map((item) => {
              const meta = FEATURE_LABELS[item.feature] ?? { label: item.feature, unit: '' };
              const direction =
                Math.abs(item.delta) < 1e-6 ? '◆ Unchanged' : item.delta > 0 ? '▲ Increased' : '▼ Decreased';
              return (
                <article key={item.feature} className="biomarker-card">
                  <div className="biomarker-head">
                    <span className="metric-label">{meta.label}</span>
                    <small className="muted-text">{meta.unit}</small>
                  </div>
                  <div className="biomarker-val">{item.latest}</div>
                  <div className="biomarker-meta">
                    <span>Baseline: {item.baseline}</span>
                    <span className="delta-pill">
                      {direction}
                      {item.percent_change !== null
                        ? ` (${item.percent_change >= 0 ? '+' : ''}${item.percent_change}%)`
                        : ''}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="obs-log-heading">
        <div className="panel-header">
          <div>
            <h3 id="obs-log-heading">Immutable Observation Ledger ({data.count})</h3>
            <p className="muted-text">
              Ordered newest first. Raw observation records are append-only and never overwritten.
            </p>
          </div>
        </div>

        <div className="table-wrap" tabIndex={0}>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Observed (UTC)</th>
                <th scope="col">Source</th>
                <th scope="col">Observed UPDRS (T / M)</th>
                <th scope="col">Estimated UPDRS (T / M)</th>
                <th scope="col">Confidence</th>
                <th scope="col">Model Version</th>
                <th scope="col">Quality Flags</th>
              </tr>
            </thead>
            <tbody>
              {data.observations.map((obs) => (
                <tr key={obs.id}>
                  <td>{new Date(obs.observed_at).toISOString().replace('T', ' ').slice(0, 16)}</td>
                  <td>
                    <code>{obs.source}</code>
                    {obs.is_partial && <span className="status-badge badge-warn inline-badge">Partial</span>}
                  </td>
                  <td>
                    {obs.observed_total_updrs !== null ? obs.observed_total_updrs.toFixed(1) : '—'} /{' '}
                    {obs.observed_motor_updrs !== null ? obs.observed_motor_updrs.toFixed(1) : '—'}
                  </td>
                  <td>
                    {obs.estimated_total_updrs !== null ? obs.estimated_total_updrs.toFixed(1) : '—'} /{' '}
                    {obs.estimated_motor_updrs !== null ? obs.estimated_motor_updrs.toFixed(1) : '—'}
                  </td>
                  <td>
                    {obs.confidence_score !== null ? `${Math.round(obs.confidence_score * 100)}%` : '—'}
                  </td>
                  <td>
                    <code>{obs.model_version ?? 'N/A'}</code>
                  </td>
                  <td>{obs.quality_flags.length > 0 ? obs.quality_flags.join(', ') : 'OK'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
