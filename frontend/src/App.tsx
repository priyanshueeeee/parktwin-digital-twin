import { useCallback, useEffect, useMemo, useState } from 'react';
import { HttpParkTwinClient, ParkTwinApiError, type ParkTwinClient } from './api/client';
import type {
  AuditEventItem,
  ObservationsData,
  ReadinessData,
  ScenarioListItem,
  SimulationData,
  SimulationPayload,
  TrajectoryData,
  TwinCreatePayload,
  TwinListItem,
  TwinUpdatePayload,
} from './api/types';
import { TrajectoryChart, type UpdrsMetric } from './charts/TrajectoryChart';
import { CreateTwinModal } from './components/CreateTwinModal';
import { GovernancePanel } from './components/GovernancePanel';
import { MetricsStrip } from './components/MetricsStrip';
import { ObservationForm } from './components/ObservationForm';
import { SafetyBanner } from './components/SafetyBanner';
import { ScenarioHistoryPanel } from './components/ScenarioHistoryPanel';
import { SimulationPanel } from './components/SimulationPanel';
import { TrajectoryTable } from './components/TrajectoryTable';
import { TwinSelector } from './components/TwinSelector';
import { VoiceProfilePanel } from './components/VoiceProfilePanel';

interface AppProps {
  client?: ParkTwinClient;
}

type WorkspaceTab = 'overview' | 'biomarkers' | 'scenarios' | 'governance';
type TimeWindow = 'all' | '30d' | '90d';

function computeStartTime(window: TimeWindow): string | undefined {
  if (window === 'all') return undefined;
  const days = window === '30d' ? 30 : 90;
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

function triggerFileDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function App({ client }: AppProps) {
  const api = useMemo(() => client ?? new HttpParkTwinClient(), [client]);

  const [readiness, setReadiness] = useState<ReadinessData | null>(null);
  const [twins, setTwins] = useState<TwinListItem[]>([]);
  const [twinsLoading, setTwinsLoading] = useState(true);
  const [twinsError, setTwinsError] = useState<string | null>(null);
  const [selectedTwinId, setSelectedTwinId] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview');
  const [trajectory, setTrajectory] = useState<TrajectoryData | null>(null);
  const [trajectoryWarnings, setTrajectoryWarnings] = useState<string[]>([]);
  const [trajectoryRequestId, setTrajectoryRequestId] = useState('');
  const [trajectoryLoading, setTrajectoryLoading] = useState(false);
  const [trajectoryError, setTrajectoryError] = useState<string | null>(null);

  const [seriesFilter, setSeriesFilter] = useState<'all' | 'observed' | 'estimated'>('all');
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('all');
  const [metric, setMetric] = useState<UpdrsMetric>('total_updrs');
  const [showTable, setShowTable] = useState(false);

  const [simulation, setSimulation] = useState<SimulationData | null>(null);
  const [simulationWarnings, setSimulationWarnings] = useState<string[]>([]);
  const [simulationPending, setSimulationPending] = useState(false);

  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([]);
  const [scenariosLoading, setScenariosLoading] = useState(false);

  const [observationsData, setObservationsData] = useState<ObservationsData | null>(null);
  const [observationsLoading, setObservationsLoading] = useState(false);

  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);

  const loadReadiness = useCallback(async () => {
    try {
      const env = await api.getReady();
      setReadiness(env.data);
    } catch {
      setReadiness({
        status: 'not_ready',
        checks: { database: 'unknown', inference_adapter: 'unavailable' },
        model_metadata: null,
      });
    }
  }, [api]);

  const loadTwins = useCallback(
    async (preferredId?: string) => {
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
    },
    [api],
  );

  const loadTrajectory = useCallback(
    async (twinId: string, series: 'all' | 'observed' | 'estimated', window: TimeWindow) => {
      setTrajectoryLoading(true);
      setTrajectoryError(null);
      try {
        const env = await api.getTrajectory(twinId, {
          series,
          startTime: computeStartTime(window),
        });
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

  const loadScenarios = useCallback(
    async (twinId: string) => {
      setScenariosLoading(true);
      try {
        const env = await api.listScenarios(twinId);
        setScenarios(env.data.scenarios);
      } catch {
        setScenarios([]);
      } finally {
        setScenariosLoading(false);
      }
    },
    [api],
  );

  const loadObservations = useCallback(
    async (twinId: string) => {
      setObservationsLoading(true);
      try {
        const env = await api.listObservations(twinId);
        setObservationsData(env.data);
      } catch {
        setObservationsData(null);
      } finally {
        setObservationsLoading(false);
      }
    },
    [api],
  );

  const loadAudit = useCallback(
    async (twinId: string) => {
      setAuditLoading(true);
      try {
        const env = await api.listAuditEvents(twinId);
        setAuditEvents(env.data.events);
      } catch {
        setAuditEvents([]);
      } finally {
        setAuditLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadReadiness();
    void loadTwins();
  }, [loadReadiness, loadTwins]);

  useEffect(() => {
    if (!selectedTwinId) {
      setTrajectory(null);
      setSimulation(null);
      setSimulationWarnings([]);
      setScenarios([]);
      setObservationsData(null);
      setAuditEvents([]);
      return;
    }
    void loadTrajectory(selectedTwinId, seriesFilter, timeWindow);
  }, [selectedTwinId, seriesFilter, timeWindow, loadTrajectory]);

  useEffect(() => {
    if (!selectedTwinId) return;
    if (activeTab === 'biomarkers') void loadObservations(selectedTwinId);
    if (activeTab === 'scenarios') void loadScenarios(selectedTwinId);
    if (activeTab === 'governance') void loadAudit(selectedTwinId);
  }, [selectedTwinId, activeTab, loadObservations, loadScenarios, loadAudit]);

  const handleSelectTwin = (twinId: string) => {
    if (twinId !== selectedTwinId) {
      setSimulation(null);
      setSimulationWarnings([]);
      setObservationsData(null);
      setScenarios([]);
      setAuditEvents([]);
      setSelectedTwinId(twinId);
    }
  };

  const handleCreateTwin = async (payload: TwinCreatePayload) => {
    const res = await api.createTwin(payload);
    setSimulation(null);
    setSimulationWarnings([]);
    setActiveTab('overview');
    await loadTwins(res.data.twin.id);
  };

  const handleUpdateTwin = async (payload: TwinUpdatePayload) => {
    await api.updateTwin(payload);
    setSimulation(null);
    setSimulationWarnings([]);
    await Promise.all([
      loadTwins(payload.twin_id),
      loadTrajectory(payload.twin_id, seriesFilter, timeWindow),
    ]);
  };

  const handleRunSimulation = async (payload: SimulationPayload) => {
    if (!selectedTwinId) return;
    setSimulationPending(true);
    try {
      const res = await api.simulate(selectedTwinId, payload);
      setSimulation(res.data);
      setSimulationWarnings(res.warnings);
      void loadScenarios(selectedTwinId);
    } finally {
      setSimulationPending(false);
    }
  };

  const handleOverlaySavedScenario = async (scenarioId: string) => {
    if (!selectedTwinId) return;
    setSimulationPending(true);
    try {
      const env = await api.getTrajectory(selectedTwinId, {
        series: seriesFilter,
        startTime: computeStartTime(timeWindow),
        scenarioId,
      });
      if (env.data.scenario) {
        const sc = env.data.scenario;
        setSimulation({
          scenario_id: sc.id,
          twin_id: selectedTwinId,
          label: sc.label,
          hypothetical: true,
          status: 'completed',
          baseline_twin_version: sc.baseline_twin_version,
          parameters: sc.parameters,
          horizon_days: sc.horizon_days,
          step_days: sc.step_days,
          assumptions_version: sc.assumptions_version,
          model_version: sc.model_version,
          baseline_series: sc.baseline_series,
          scenario_series: sc.scenario_series,
          summary: sc.summary,
          created_at: sc.created_at,
          disclaimer: env.data.disclaimer,
        });
        setSimulationWarnings(env.warnings.filter((w) => w.includes('HYPOTHETICAL')));
        setActiveTab('overview');
      }
    } finally {
      setSimulationPending(false);
    }
  };

  const handleResetSimulation = () => {
    setSimulation(null);
    setSimulationWarnings([]);
  };

  const handleChangeStatus = async (status: 'active' | 'paused' | 'archived', reason: string) => {
    if (!trajectory) return;
    await api.updateTwinStatus(trajectory.twin.id, {
      status,
      reason,
      expected_version: trajectory.twin.version,
    });
    await Promise.all([
      loadTwins(trajectory.twin.id),
      loadTrajectory(trajectory.twin.id, seriesFilter, timeWindow),
      loadAudit(trajectory.twin.id),
    ]);
  };

  const handleRecompute = async (reRunInference: boolean, reason: string) => {
    if (!trajectory) return;
    await api.recomputeTwin(trajectory.twin.id, {
      re_run_inference: reRunInference,
      reason,
    });
    await Promise.all([
      loadTwins(trajectory.twin.id),
      loadTrajectory(trajectory.twin.id, seriesFilter, timeWindow),
      loadAudit(trajectory.twin.id),
    ]);
  };

  const handleExport = async (format: 'json' | 'csv', includeScenario: boolean) => {
    if (!trajectory) return;
    const scenarioId = includeScenario && simulation ? simulation.scenario_id : undefined;
    const content = await api.exportTwin(trajectory.twin.id, format, scenarioId);
    const mime = format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8';
    triggerFileDownload(
      content,
      `parktwin-${trajectory.twin.external_reference}-v${trajectory.twin.version}.${format}`,
      mime,
    );
    void loadAudit(trajectory.twin.id);
  };

  const allWarnings = Array.from(new Set([...trajectoryWarnings, ...simulationWarnings]));
  const isReadOnlyLifecycle =
    trajectory?.twin.status === 'paused' || trajectory?.twin.status === 'archived';
  const cal = trajectory?.calibration_summary;

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main dashboard
      </a>
      <SafetyBanner disclaimer={trajectory?.disclaimer} />

      <header className="app-header">
        <div className="brand">
          <div className="brand-title-row">
            <span className="brand-mark" aria-hidden="true">
              PT
            </span>
            <div>
              <h1>ParkTwin Clinician Review Dashboard</h1>
              <p>Longitudinal Speech-to-UPDRS Progression Twin &amp; Hypothetical Scenario Sandbox</p>
            </div>
          </div>
        </div>

        <div className="controls-bar">
          {readiness && (
            <span
              className={`status-badge ${readiness.status === 'ready' ? 'badge-ok' : 'badge-warn'}`}
              title="Backend readiness and active inference adapter"
            >
              {readiness.status === 'ready' ? '● API Ready' : '△ API Degraded'}
              {readiness.model_metadata &&
                ` · ${readiness.model_metadata.model_version} [${readiness.model_metadata.adapter_type}]`}
            </span>
          )}
          {trajectory && (
            <span className="status-badge badge-ref">
              {trajectory.twin.external_reference} · v{trajectory.twin.version}
            </span>
          )}
        </div>
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
                onClick={() => void loadTrajectory(selectedTwinId, seriesFilter, timeWindow)}
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

              <div className="workspace-tabs" role="tablist" aria-label="Twin review sections">
                {(
                  [
                    ['overview', 'Trajectory & Simulation'],
                    ['biomarkers', 'Voice Biomarkers & Ledger'],
                    ['scenarios', `Saved Scenarios${scenarios.length > 0 ? ` (${scenarios.length})` : ''}`],
                    ['governance', 'Governance, Export & Audit'],
                  ] as const
                ).map(([tabId, label]) => (
                  <button
                    key={tabId}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tabId}
                    className={`tab-btn ${activeTab === tabId ? 'tab-btn-active' : ''}`}
                    onClick={() => setActiveTab(tabId)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {activeTab === 'overview' && (
                <>
                  {/* Warnings rendered BEFORE the chart so clinicians see caveats first */}
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
                          {cal && cal.paired_total_count > 0 && cal.total_updrs_mae !== null && (
                            <span className="calibration-chip">
                              Paired Observed vs Est. MAE: <strong>{cal.total_updrs_mae.toFixed(2)} pts</strong> (n={cal.paired_total_count})
                            </span>
                          )}
                        </p>
                      </div>

                      <div className="controls-bar">
                        <div className="segmented" role="group" aria-label="Time window">
                          {(
                            [
                              ['all', 'All'],
                              ['90d', '90d'],
                              ['30d', '30d'],
                            ] as const
                          ).map(([win, label]) => (
                            <button
                              key={win}
                              type="button"
                              aria-pressed={timeWindow === win}
                              onClick={() => setTimeWindow(win)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>

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
                    {isReadOnlyLifecycle ? (
                      <section className="panel" role="status">
                        <h3>Voice Observation Ingestion Locked ({trajectory.twin.status})</h3>
                        <p className="muted-text">
                          This twin is currently <strong>{trajectory.twin.status}</strong>. Resume active
                          tracking from the <em>Governance, Export &amp; Audit</em> tab to append new voice observations.
                        </p>
                      </section>
                    ) : (
                      <ObservationForm
                        twinId={trajectory.twin.id}
                        twinVersion={trajectory.twin.version}
                        onSubmit={handleUpdateTwin}
                      />
                    )}
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

              {activeTab === 'biomarkers' && (
                <VoiceProfilePanel data={observationsData} loading={observationsLoading} />
              )}

              {activeTab === 'scenarios' && (
                <ScenarioHistoryPanel
                  scenarios={scenarios}
                  activeScenarioId={simulation?.scenario_id ?? null}
                  loading={scenariosLoading}
                  onOverlayScenario={(id) => void handleOverlaySavedScenario(id)}
                  onClearOverlay={handleResetSimulation}
                />
              )}

              {activeTab === 'governance' && (
                <GovernancePanel
                  twin={trajectory.twin}
                  activeScenarioId={simulation?.scenario_id ?? null}
                  auditEvents={auditEvents}
                  auditLoading={auditLoading}
                  onChangeStatus={handleChangeStatus}
                  onRecompute={handleRecompute}
                  onExport={handleExport}
                />
              )}
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
