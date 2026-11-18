import { useCallback, useEffect, useMemo, useState } from 'react';
import { HttpParkTwinClient, ParkTwinApiError, type ParkTwinClient } from './api/client';
import type {
  SimulationData,
  SimulationPayload,
  TrajectoryData,
  TwinCreatePayload,
  TwinListItem,
  TwinUpdatePayload,
} from './api/types';
import { TrajectoryChart, type UpdrsMetric } from './charts/TrajectoryChart';
import { CreateTwinModal } from './components/CreateTwinModal';
import { MetricsStrip } from './components/MetricsStrip';
import { ObservationForm } from './components/ObservationForm';
import { SafetyBanner } from './components/SafetyBanner';
import { SimulationPanel } from './components/SimulationPanel';
import { TrajectoryTable } from './components/TrajectoryTable';
import { TwinSelector } from './components/TwinSelector';

interface AppProps {
  client?: ParkTwinClient;
}

export function App({ client }: AppProps) {
  const api = useMemo(() => client ?? new HttpParkTwinClient(), [client]);

  const [twins, setTwins] = useState<TwinListItem[]>([]);
  const [twinsLoading, setTwinsLoading] = useState(true);
  const [twinsError, setTwinsError] = useState<string | null>(null);
  const [selectedTwinId, setSelectedTwinId] = useState<string | null>(null);

  const [trajectory, setTrajectory] = useState<TrajectoryData | null>(null);
  const [trajectoryWarnings, setTrajectoryWarnings] = useState<string[]>([]);
  const [trajectoryRequestId, setTrajectoryRequestId] = useState('');
  const [trajectoryLoading, setTrajectoryLoading] = useState(false);
  const [trajectoryError, setTrajectoryError] = useState<string | null>(null);

  const [seriesFilter, setSeriesFilter] = useState<'all' | 'observed' | 'estimated'>('all');
  const [metric, setMetric] = useState<UpdrsMetric>('total_updrs');
  const [showTable, setShowTable] = useState(false);

  const [simulation, setSimulation] = useState<SimulationData | null>(null);
  const [simulationWarnings, setSimulationWarnings] = useState<string[]>([]);
  const [simulationPending, setSimulationPending] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);

  const loadTwins = useCallback(async (preferredId?: string) => {
    setTwinsLoading(true);
    setTwinsError(null);
    try {
      const env = await api.listTwins();
      setTwins(env.data.twins);
      setSelectedTwinId((current) => {
        if (preferredId) return preferredId;
        if (current && env.data.twins.some((t) => t.id === current)) return current;
        return env.data.twins[0]?.id ?? null;
      });
    } catch (err) {
      if (err instanceof ParkTwinApiError) {
        setTwinsError(`${err.message} (Code: ${err.code}, Request: ${err.requestId})`);
      } else {
        setTwinsError('Unable to load digital twins.');
      }
    } finally {
      setTwinsLoading(false);
    }
  }, [api]);

  const loadTrajectory = useCallback(
    async (twinId: string, series: 'all' | 'observed' | 'estimated') => {
      setTrajectoryLoading(true);
      setTrajectoryError(null);
      try {
        const env = await api.getTrajectory(twinId, { series });
        setTrajectory(env.data);
        setTrajectoryWarnings(env.warnings);
        setTrajectoryRequestId(env.request_id);
      } catch (err) {
        if (err instanceof ParkTwinApiError) {
          setTrajectoryError(`${err.message} (Code: ${err.code}, Request: ${err.requestId})`);
        } else {
          setTrajectoryError('Failed to retrieve twin trajectory.');
        }
      } finally {
        setTrajectoryLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadTwins();
  }, [loadTwins]);

  useEffect(() => {
    if (!selectedTwinId) {
      setTrajectory(null);
      setSimulation(null);
      setSimulationWarnings([]);
      return;
    }
    void loadTrajectory(selectedTwinId, seriesFilter);
  }, [selectedTwinId, seriesFilter, loadTrajectory]);

  const handleSelectTwin = (twinId: string) => {
    if (twinId !== selectedTwinId) {
      setSimulation(null);
      setSimulationWarnings([]);
      setSelectedTwinId(twinId);
    }
  };

  const handleCreateTwin = async (payload: TwinCreatePayload) => {
    const res = await api.createTwin(payload);
    setSimulation(null);
    setSimulationWarnings([]);
    await loadTwins(res.data.twin.id);
  };

  const handleUpdateTwin = async (payload: TwinUpdatePayload) => {
    await api.updateTwin(payload);
    setSimulation(null);
    setSimulationWarnings([]);
    await Promise.all([
      loadTwins(payload.twin_id),
      loadTrajectory(payload.twin_id, seriesFilter),
    ]);
  };

  const handleRunSimulation = async (payload: SimulationPayload) => {
    if (!selectedTwinId) return;
    setSimulationPending(true);
    try {
      const res = await api.simulate(selectedTwinId, payload);
      setSimulation(res.data);
      setSimulationWarnings(res.warnings);
    } finally {
      setSimulationPending(false);
    }
  };

  const handleResetSimulation = () => {
    // Pure local reset: never performs a write request against twin state.
    setSimulation(null);
    setSimulationWarnings([]);
  };

  const allWarnings = Array.from(new Set([...trajectoryWarnings, ...simulationWarnings]));

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main dashboard
      </a>
      <SafetyBanner disclaimer={trajectory?.disclaimer} />

      <header className="app-header">
        <div className="brand">
          <h1>ParkTwin Clinician Review Dashboard</h1>
          <p>Longitudinal Speech-to-UPDRS Progression Twin &amp; Hypothetical Scenario Sandbox</p>
        </div>
        {trajectory && (
          <div className="controls-bar">
            <span className="status-badge badge-ok">
              Active Reference: {trajectory.twin.external_reference} (v{trajectory.twin.version})
            </span>
          </div>
        )}
      </header>

      <div className="app-shell">
        <TwinSelector
          twins={twins}
          selectedTwinId={selectedTwinId}
          loading={twinsLoading}
          onSelect={handleSelectTwin}
          onOpenCreate={() => setCreateOpen(true)}
          onRefresh={() => void loadTwins(selectedTwinId ?? undefined)}
        />

        <main id="main-content" className="main-workspace" tabIndex={-1}>
          {twinsError && (
            <div className="alert alert-error" role="alert">
              <strong>Connection Error:</strong> {twinsError}{' '}
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void loadTwins()}>
                Retry
              </button>
            </div>
          )}

          {!selectedTwinId && !twinsLoading && (
            <section className="empty-workspace" role="status">
              <h2>Select or Initialize a Digital Twin</h2>
              <p>
                Choose a pseudonymous cohort from the left panel or initialize a new baseline twin
                to inspect longitudinal UPDRS estimates and explore hypothetical intervention scenarios.
              </p>
              <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
                + Initialize Baseline Twin
              </button>
            </section>
          )}

          {selectedTwinId && trajectoryError && (
            <div className="alert alert-error" role="alert">
              <strong>Trajectory Load Failed:</strong> {trajectoryError}{' '}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void loadTrajectory(selectedTwinId, seriesFilter)}
              >
                Retry
              </button>
            </div>
          )}

          {selectedTwinId && trajectoryLoading && !trajectory && (
            <section className="panel" role="status" aria-busy="true">
              Loading longitudinal trajectory and model lineage...
            </section>
          )}

          {trajectory && (
            <>
              <MetricsStrip trajectory={trajectory} requestId={trajectoryRequestId} />

              {/* Warnings are rendered BEFORE the chart so clinicians see quality/sparsity caveats first */}
              {allWarnings.length > 0 && (
                <div className="alert alert-warn" role="alert" aria-label="Data quality and safety warnings">
                  <strong>Data Quality &amp; Interpretation Notices ({allWarnings.length})</strong>
                  <ul>
                    {allWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <section className="panel" aria-labelledby="chart-heading">
                <div className="panel-header">
                  <div>
                    <h3 id="chart-heading">
                      Longitudinal UPDRS Trajectory — {trajectory.twin.external_reference}
                    </h3>
                    <p className="muted-text">
                      Observed clinical scores, model-estimated speech states, and optional hypothetical scenario overlay.
                    </p>
                  </div>

                  <div className="controls-bar">
                    <div className="segmented" role="group" aria-label="UPDRS score metric">
                      <button
                        type="button"
                        aria-pressed={metric === 'total_updrs'}
                        onClick={() => setMetric('total_updrs')}
                      >
                        Total UPDRS
                      </button>
                      <button
                        type="button"
                        aria-pressed={metric === 'motor_updrs'}
                        onClick={() => setMetric('motor_updrs')}
                      >
                        Motor UPDRS
                      </button>
                    </div>

                    <div className="segmented" role="group" aria-label="Series filter">
                      {(['all', 'observed', 'estimated'] as const).map((s) => (
                        <button
                          key={s}
                          type="button"
                          aria-pressed={seriesFilter === s}
                          onClick={() => setSeriesFilter(s)}
                        >
                          {s === 'all' ? 'All Series' : s === 'observed' ? 'Observed' : 'Estimated'}
                        </button>
                      ))}
                    </div>

                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      aria-pressed={showTable}
                      onClick={() => setShowTable((prev) => !prev)}
                    >
                      {showTable ? 'Hide Data Table' : 'View Data Table'}
                    </button>
                  </div>
                </div>

                <TrajectoryChart
                  observedPoints={trajectory.observed_points}
                  estimatedPoints={trajectory.estimated_points}
                  simulation={simulation}
                  metric={metric}
                  simulationPending={simulationPending}
                />

                {showTable && (
                  <TrajectoryTable
                    observedPoints={trajectory.observed_points}
                    estimatedPoints={trajectory.estimated_points}
                    simulation={simulation}
                  />
                )}
              </section>

              <div className="two-col-panels">
                <ObservationForm
                  twinId={trajectory.twin.id}
                  twinVersion={trajectory.twin.version}
                  onSubmit={handleUpdateTwin}
                />
                <SimulationPanel
                  canSimulate={trajectory.estimated_points.length > 0}
                  activeSimulation={simulation}
                  pending={simulationPending}
                  onRunSimulation={handleRunSimulation}
                  onResetSimulation={handleResetSimulation}
                />
              </div>
            </>
          )}
        </main>
      </div>

      <CreateTwinModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreateTwin}
      />
    </>
  );
}
