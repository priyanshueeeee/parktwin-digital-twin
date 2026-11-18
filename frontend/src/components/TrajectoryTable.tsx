import type { SimulationData, TrajectoryPoint } from '../api/types';

interface TrajectoryTableProps {
  observedPoints: TrajectoryPoint[];
  estimatedPoints: TrajectoryPoint[];
  simulation: SimulationData | null;
}

export function TrajectoryTable({
  observedPoints,
  estimatedPoints,
  simulation,
}: TrajectoryTableProps) {
  const rows: TrajectoryPoint[] = [
    ...observedPoints,
    ...estimatedPoints,
    ...(simulation ? simulation.scenario_series : []),
  ].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (rows.length === 0) {
    return <p className="muted-text">No tabular trajectory rows available.</p>;
  }

  return (
    <div className="table-wrap" role="region" aria-label="Accessible trajectory data table" tabIndex={0}>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Timestamp (UTC)</th>
            <th scope="col">Source</th>
            <th scope="col">Total UPDRS</th>
            <th scope="col">Motor UPDRS</th>
            <th scope="col">Quality / Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((pt, idx) => (
            <tr key={`${pt.source_type}-${pt.timestamp}-${idx}`}>
              <td>{new Date(pt.timestamp).toISOString().replace('T', ' ').slice(0, 16)}</td>
              <td>
                <span className={`source-chip source-${pt.source_type}`}>
                  {pt.source_type === 'observed' && 'Observed'}
                  {pt.source_type === 'estimated' && 'Estimated'}
                  {pt.source_type === 'simulated' && 'Hypothetical'}
                </span>
              </td>
              <td>{pt.total_updrs !== null ? pt.total_updrs.toFixed(2) : '—'}</td>
              <td>{pt.motor_updrs !== null ? pt.motor_updrs.toFixed(2) : '—'}</td>
              <td>
                {pt.hypothetical
                  ? 'Hypothetical simulation (non-clinical)'
                  : pt.quality_flags && pt.quality_flags.length > 0
                    ? pt.quality_flags.join(', ')
                    : 'OK'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
