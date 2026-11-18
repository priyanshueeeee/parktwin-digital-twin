import type { TrajectoryData } from '../api/types';

interface MetricsStripProps {
  trajectory: TrajectoryData;
  requestId: string;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'None';
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

export function MetricsStrip({ trajectory, requestId }: MetricsStripProps) {
  const { slope, coverage, model_metadata: meta, estimated_points: estPoints } = trajectory;
  const latestEst = estPoints.length > 0 ? estPoints[estPoints.length - 1] : null;

  const slopeDirection =
    slope.status !== 'computed' || slope.total_updrs_per_30_days === null
      ? 'Insufficient history'
      : slope.total_updrs_per_30_days > 0.25
        ? '▲ Worsening trend'
        : slope.total_updrs_per_30_days < -0.25
          ? '▼ Improving trend'
          : '◆ Stable trend';

  return (
    <section className="metrics-grid" aria-label="Twin summary telemetry and model lineage">
      <article className="metric-card">
        <span className="metric-label">Latest Model-Estimated UPDRS</span>
        {latestEst && latestEst.total_updrs !== null ? (
          <>
            <div className="metric-value">
              {latestEst.total_updrs.toFixed(1)} <small>Total</small>
            </div>
            <p className="metric-sub">
              Motor: <strong>{latestEst.motor_updrs?.toFixed(1) ?? 'N/A'}</strong>
              {latestEst.total_updrs_ci_low != null && latestEst.total_updrs_ci_high != null && (
                <> · Total CI: {latestEst.total_updrs_ci_low.toFixed(1)}–{latestEst.total_updrs_ci_high.toFixed(1)}</>
              )}
            </p>
          </>
        ) : (
          <>
            <div className="metric-value metric-muted">Unavailable</div>
            <p className="metric-sub">Complete 16-feature speech observation required</p>
          </>
        )}
      </article>

      <article className="metric-card">
        <span className="metric-label">Progression Slope (ΔUPDRS / 30 days)</span>
        {slope.status === 'computed' && slope.total_updrs_per_30_days !== null ? (
          <>
            <div className="metric-value">
              {slope.total_updrs_per_30_days >= 0 ? '+' : ''}
              {slope.total_updrs_per_30_days.toFixed(2)}{' '}
              <small>pts/30d</small>
            </div>
            <p className="metric-sub">
              {slopeDirection} · Motor: {slope.motor_updrs_per_30_days?.toFixed(2)} pts/30d · Method:{' '}
              <code>{slope.method}</code>
            </p>
          </>
        ) : (
          <>
            <div className="metric-value metric-muted">Insufficient Data</div>
            <p className="metric-sub">{slope.window_description}</p>
          </>
        )}
      </article>

      <article className="metric-card">
        <span className="metric-label">Longitudinal Coverage & Freshness</span>
        <div className="metric-value">
          {coverage.total_observations} <small>observations</small>
        </div>
        <p className="metric-sub">
          Span: {coverage.time_span_days.toFixed(1)} days · Last update: {formatDate(coverage.last_observed_at)}
          {coverage.is_stale && (
            <span className="status-badge badge-stale inline-badge">◷ Stale (&gt;{coverage.stale_threshold_days}d)</span>
          )}
        </p>
      </article>

      <article className="metric-card">
        <span className="metric-label">Model Lineage & Traceability</span>
        <div className="metric-value metric-code">{meta.model_version}</div>
        <p className="metric-sub">
          Features: <code>{meta.feature_version}</code> · Adapter: <code>{meta.adapter_type}</code> · Req:{' '}
          <code>{requestId}</code>
        </p>
      </article>
    </section>
  );
}
