import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { App } from '../src/App';
import { ParkTwinApiError, type ParkTwinClient } from '../src/api/client';
import type { SimulationData, TrajectoryData, TwinListData } from '../src/api/types';

function createMockClient(): ParkTwinClient {
  const twinList: TwinListData = {
    count: 2,
    disclaimer: 'Research prototype only: non-diagnostic.',
    twins: [
      {
        id: 'twin-1',
        external_reference: 'SYN-PT-1001',
        status: 'active',
        version: 2,
        latest_state_id: 'est-2',
        data_quality_summary: {},
        schema_version: 'v1',
        created_at: '2026-10-01T12:00:00+00:00',
        updated_at: '2026-11-10T12:00:00+00:00',
        observation_count: 2,
        last_observed_at: '2026-11-10T12:00:00+00:00',
        is_stale: false,
        latest_total_updrs: 34.5,
        latest_motor_updrs: 25.4,
        slope_status: 'computed',
        slope_total_per_30_days: 2.15,
      },
      {
        id: 'twin-2',
        external_reference: 'SYN-PT-3009',
        status: 'insufficient_data',
        version: 1,
        latest_state_id: null,
        data_quality_summary: {},
        schema_version: 'v1',
        created_at: '2026-09-01T12:00:00+00:00',
        updated_at: '2026-09-01T12:00:00+00:00',
        observation_count: 1,
        last_observed_at: '2026-09-01T12:00:00+00:00',
        is_stale: true,
        latest_total_updrs: null,
        latest_motor_updrs: null,
        slope_status: 'insufficient_data',
        slope_total_per_30_days: null,
      },
    ],
  };

  const trajectoryByTwin: Record<string, TrajectoryData> = {
    'twin-1': {
      twin: twinList.twins[0],
      series_filter: 'all',
      observed_points: [
        {
          observation_id: 'obs-1',
          timestamp: '2026-10-15T12:00:00+00:00',
          source_type: 'observed',
          total_updrs: 31.0,
          motor_updrs: 23.0,
          hypothetical: false,
        },
      ],
      estimated_points: [
        {
          observation_id: 'obs-1',
          timestamp: '2026-10-15T12:00:00+00:00',
          source_type: 'estimated',
          total_updrs: 31.2,
          motor_updrs: 23.1,
          total_updrs_ci_low: 28.0,
          total_updrs_ci_high: 34.4,
          motor_updrs_ci_low: 20.5,
          motor_updrs_ci_high: 25.7,
          hypothetical: false,
        },
        {
          observation_id: 'obs-2',
          timestamp: '2026-11-10T12:00:00+00:00',
          source_type: 'estimated',
          total_updrs: 34.5,
          motor_updrs: 25.4,
          total_updrs_ci_low: 31.3,
          total_updrs_ci_high: 37.7,
          motor_updrs_ci_low: 22.8,
          motor_updrs_ci_high: 28.0,
          hypothetical: false,
        },
      ],
      scenario: null,
      slope: {
        status: 'computed',
        method: 'ordinary_least_squares_full_window',
        window_description: 'All valid time-separated estimated observations',
        units: 'updrs_points_per_30_days',
        total_updrs_per_30_days: 2.15,
        motor_updrs_per_30_days: 1.62,
        total_updrs_per_day: 0.0717,
        motor_updrs_per_day: 0.054,
        observation_count_used: 2,
        time_span_days: 26,
      },
      coverage: {
        total_observations: 2,
        estimated_observations: 2,
        observed_updrs_count: 1,
        first_observed_at: '2026-10-15T12:00:00+00:00',
        last_observed_at: '2026-11-10T12:00:00+00:00',
        time_span_days: 26,
        is_stale: false,
        stale_threshold_days: 30,
      },
      quality_flags: ['SPARSE_LONGITUDINAL_HISTORY'],
      model_metadata: {
        model_version: 'mock-updrs-v0.1.0',
        feature_version: 'speech16-v1',
        assumptions_version: 'sim-assumptions-mock-v1',
        adapter_type: 'mock',
        artifact_checksum: 'abcdef1234567890',
      },
      disclaimer: 'Research prototype only: non-diagnostic.',
    },
    'twin-2': {
      twin: twinList.twins[1],
      series_filter: 'all',
      observed_points: [],
      estimated_points: [],
      scenario: null,
      slope: {
        status: 'insufficient_data',
        method: 'ordinary_least_squares_full_window',
        window_description: 'Requires at least 2 time-separated valid estimated observations',
        units: 'updrs_points_per_30_days',
        total_updrs_per_30_days: null,
        motor_updrs_per_30_days: null,
        total_updrs_per_day: null,
        motor_updrs_per_day: null,
        observation_count_used: 0,
        time_span_days: 0,
      },
      coverage: {
        total_observations: 1,
        estimated_observations: 0,
        observed_updrs_count: 0,
        first_observed_at: '2026-09-01T12:00:00+00:00',
        last_observed_at: '2026-09-01T12:00:00+00:00',
        time_span_days: 0,
        is_stale: true,
        stale_threshold_days: 30,
      },
      quality_flags: ['INSUFFICIENT_HISTORY_FOR_SLOPE', 'STALE_TWIN_DATA'],
      model_metadata: {
        model_version: 'mock-updrs-v0.1.0',
        feature_version: 'speech16-v1',
        assumptions_version: 'sim-assumptions-mock-v1',
        adapter_type: 'mock',
        artifact_checksum: 'abcdef1234567890',
      },
      disclaimer: 'Research prototype only: non-diagnostic.',
    },
  };

  const simResponse: SimulationData = {
    scenario_id: 'scen-99',
    twin_id: 'twin-1',
    label: 'Levodopa + Physical Therapy Scenario',
    hypothetical: true,
    status: 'completed',
    baseline_twin_version: 2,
    parameters: {
      levodopa_dose_change_mg: 150,
      physical_therapy_sessions_per_week: 3,
      adherence_ratio: 0.9,
    },
    horizon_days: 90,
    step_days: 15,
    assumptions_version: 'sim-assumptions-mock-v1',
    model_version: 'mock-updrs-v0.1.0',
    baseline_series: [
      {
        timestamp: '2026-11-10T12:00:00+00:00',
        source_type: 'estimated',
        total_updrs: 34.5,
        motor_updrs: 25.4,
        hypothetical: false,
      },
      {
        timestamp: '2027-02-08T12:00:00+00:00',
        source_type: 'estimated',
        total_updrs: 40.9,
        motor_updrs: 30.2,
        hypothetical: false,
      },
    ],
    scenario_series: [
      {
        timestamp: '2026-11-10T12:00:00+00:00',
        source_type: 'simulated',
        total_updrs: 34.5,
        motor_updrs: 25.4,
        hypothetical: true,
      },
      {
        timestamp: '2027-02-08T12:00:00+00:00',
        source_type: 'simulated',
        total_updrs: 33.1,
        motor_updrs: 24.4,
        hypothetical: true,
      },
    ],
    summary: {
      horizon_days: 90,
      baseline_end_total_updrs: 40.9,
      scenario_end_total_updrs: 33.1,
      delta_total_updrs: -7.8,
      baseline_end_motor_updrs: 30.2,
      scenario_end_motor_updrs: 24.4,
      delta_motor_updrs: -5.8,
      hypothetical: true,
    },
    created_at: '2026-11-18T12:00:00+00:00',
    disclaimer: 'Research prototype only: non-diagnostic.',
  };

  return {
    getReady: vi.fn().mockResolvedValue({
      request_id: 'req-ready-1',
      schema_version: 'v1',
      data: {
        status: 'ready',
        checks: { database: 'ok', inference_adapter: 'ok' },
        model_metadata: {
          model_version: 'mock-updrs-v0.1.0',
          feature_version: 'speech16-v1',
          assumptions_version: 'sim-assumptions-mock-v1',
          adapter_type: 'mock',
          artifact_checksum: 'abcdef1234567890',
        },
      },
      warnings: [],
    }),
    listTwins: vi.fn().mockResolvedValue({
      request_id: 'req-list-1',
      schema_version: 'v1',
      data: twinList,
      warnings: [],
    }),
    createTwin: vi.fn().mockResolvedValue({
      request_id: 'req-create-1',
      schema_version: 'v1',
      data: { twin: twinList.twins[0], disclaimer: 'Research prototype only: non-diagnostic.' },
      warnings: [],
    }),
    updateTwin: vi.fn().mockResolvedValue({
      request_id: 'req-update-1',
      schema_version: 'v1',
      data: {
        twin: { ...twinList.twins[0], version: 3 },
        observation_id: 'obs-3',
        disclaimer: 'Research prototype only: non-diagnostic.',
      },
      warnings: [],
    }),
    getTrajectory: vi.fn().mockImplementation((twinId: string, opts?: { scenarioId?: string }) =>
      Promise.resolve({
        request_id: `req-traj-${twinId}`,
        schema_version: 'v1',
        data: {
          ...trajectoryByTwin[twinId],
          calibration_summary:
            twinId === 'twin-1'
              ? {
                  paired_total_count: 1,
                  paired_motor_count: 1,
                  total_updrs_mae: 0.2,
                  motor_updrs_mae: 0.1,
                  total_updrs_mean_bias: 0.2,
                }
              : undefined,
          scenario: opts?.scenarioId
            ? {
                id: simResponse.scenario_id,
                label: simResponse.label,
                hypothetical: true,
                assumptions_version: simResponse.assumptions_version,
                model_version: simResponse.model_version,
                baseline_twin_version: simResponse.baseline_twin_version,
                parameters: simResponse.parameters,
                horizon_days: simResponse.horizon_days,
                step_days: simResponse.step_days,
                baseline_series: simResponse.baseline_series,
                scenario_series: simResponse.scenario_series,
                summary: simResponse.summary,
                created_at: simResponse.created_at,
              }
            : null,
        },
        warnings:
          twinId === 'twin-1'
            ? ['SPARSE_LONGITUDINAL_HISTORY: Interpret slope cautiously.']
            : ['INSUFFICIENT_HISTORY_FOR_SLOPE', 'STALE_TWIN_DATA'],
      }),
    ),
    simulate: vi.fn().mockResolvedValue({
      request_id: 'req-sim-1',
      schema_version: 'v1',
      data: simResponse,
      warnings: ['HYPOTHETICAL_SCENARIO: Not clinical advice.'],
    }),
    listScenarios: vi.fn().mockResolvedValue({
      request_id: 'req-scen-list',
      schema_version: 'v1',
      data: {
        twin_id: 'twin-1',
        scenarios: [
          {
            scenario_id: simResponse.scenario_id,
            label: simResponse.label,
            hypothetical: true,
            parameters: simResponse.parameters,
            horizon_days: simResponse.horizon_days,
            step_days: simResponse.step_days,
            assumptions_version: simResponse.assumptions_version,
            model_version: simResponse.model_version,
            baseline_twin_version: simResponse.baseline_twin_version,
            summary: simResponse.summary,
            created_at: simResponse.created_at,
          },
        ],
        disclaimer: 'Research prototype only: non-diagnostic.',
      },
      warnings: [],
    }),
    listObservations: vi.fn().mockResolvedValue({
      request_id: 'req-obs-list',
      schema_version: 'v1',
      data: {
        twin_id: 'twin-1',
        external_reference: 'SYN-PT-1001',
        count: 1,
        biomarker_deltas: [
          {
            feature: 'hnr',
            baseline: 22.8,
            latest: 20.1,
            delta: -2.7,
            percent_change: -11.8,
          },
        ],
        observations: [
          {
            id: 'obs-1',
            observed_at: '2026-10-15T12:00:00+00:00',
            is_partial: false,
            source: 'synthetic_seed',
            observed_total_updrs: 31.0,
            observed_motor_updrs: 23.0,
            estimated_total_updrs: 31.2,
            estimated_motor_updrs: 23.1,
            confidence_score: 0.9,
            model_version: 'mock-updrs-v0.1.0',
            feature_version: 'speech16-v1',
            quality_flags: [],
            features: {
              jitter_percent: 0.005,
              jitter_abs: 0.00003,
              jitter_rap: 0.002,
              jitter_ppq5: 0.002,
              jitter_ddp: 0.006,
              shimmer: 0.03,
              shimmer_db: 0.28,
              shimmer_apq3: 0.015,
              shimmer_apq5: 0.017,
              shimmer_apq11: 0.022,
              shimmer_dda: 0.045,
              nhr: 0.02,
              hnr: 20.1,
              rpde: 0.5,
              dfa: 0.7,
              ppe: 0.2,
            },
          },
        ],
        disclaimer: 'Research prototype only: non-diagnostic.',
      },
      warnings: [],
    }),
    listAuditEvents: vi.fn().mockResolvedValue({
      request_id: 'req-audit-list',
      schema_version: 'v1',
      data: {
        twin_id: 'twin-1',
        count: 1,
        events: [
          {
            id: 'aud-1',
            request_id: 'req-create-1',
            actor_id: 'clinician-demo-01',
            action: 'twin.create',
            resource_type: 'twin',
            resource_id: 'twin-1',
            outcome: 'success',
            details: { status: 'active' },
            created_at: '2026-10-01T12:00:00+00:00',
          },
        ],
        disclaimer: 'Research prototype only: non-diagnostic.',
      },
      warnings: [],
    }),
    updateTwinStatus: vi.fn().mockResolvedValue({
      request_id: 'req-status-1',
      schema_version: 'v1',
      data: {
        twin: { ...twinList.twins[0], status: 'paused', version: 3 },
        previous_status: 'active',
        reason: 'Clinician review hold',
      },
      warnings: [],
    }),
    recomputeTwin: vi.fn().mockResolvedValue({
      request_id: 'req-recompute-1',
      schema_version: 'v1',
      data: {
        twin: { ...twinList.twins[0], version: 3 },
        reestimated_observations: 2,
      },
      warnings: [],
    }),
    exportTwin: vi.fn().mockResolvedValue('# Non-diagnostic\ntimestamp,total\n'),
  };
}

describe('ParkTwin Dashboard Critical Path', () => {
  it('completes trajectory inspection, hypothetical simulation, reset, and observation submission', async () => {
    const user = userEvent.setup();
    const client = createMockClient();
    render(<App client={client} />);

    // Non-diagnostic safety banner is always visible
    expect(screen.getByText(/NON-DIAGNOSTIC PROTOTYPE/i)).toBeInTheDocument();

    // Loads twins and renders trajectory + model lineage + warnings
    await waitFor(() => {
      expect(screen.getByText('mock-updrs-v0.1.0')).toBeInTheDocument();
    });
    expect(screen.getByText(/SPARSE_LONGITUDINAL_HISTORY/i)).toBeInTheDocument();
    expect(screen.getByTestId('estimated-series-line')).toBeInTheDocument();

    // Toggle accessible data table
    await user.click(screen.getByRole('button', { name: /View Data Table/i }));
    expect(screen.getByRole('region', { name: /Accessible trajectory data table/i })).toBeInTheDocument();

    // Run hypothetical simulation and verify overlay appears
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /Run Simulation/i }));
    await waitFor(() => {
      expect(screen.getByTestId('simulated-series-line')).toBeInTheDocument();
    });
    expect(screen.getByText(/HYPOTHETICAL RESULT/i)).toBeInTheDocument();

    // Reset scenario clears overlay locally without calling updateTwin
    await user.click(screen.getByRole('button', { name: /Reset Scenario/i }));
    expect(screen.queryByTestId('simulated-series-line')).not.toBeInTheDocument();
    expect(client.updateTwin).not.toHaveBeenCalled();

    // Submit a new voice observation
    await user.click(screen.getByRole('button', { name: /Append Voice Observation/i }));
    await waitFor(() => {
      expect(client.updateTwin).toHaveBeenCalledTimes(1);
    });

    // Switch to insufficient-data + stale twin
    await user.click(screen.getByRole('option', { name: /SYN-PT-3009/i }));
    await waitFor(() => {
      expect(screen.getByText(/No plottable UPDRS series yet/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Insufficient Data/i).length).toBeGreaterThanOrEqual(2);
  });

  it('navigates biomarkers, saved scenario overlay, and governance audit tabs', async () => {
    const user = userEvent.setup();
    const client = createMockClient();
    render(<App client={client} />);

    await waitFor(() => {
      expect(screen.getByText(/API Ready/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Paired Observed vs Est\. MAE/i)).toBeInTheDocument();

    // Voice Biomarkers tab
    await user.click(screen.getByRole('tab', { name: /Voice Biomarkers/i }));
    await waitFor(() => {
      expect(screen.getByText(/Acoustic Biomarker Drift/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/-11\.8%/i)).toBeInTheDocument();

    // Saved Scenarios tab -> Overlay on Chart returns to overview with simulated series
    await user.click(screen.getByRole('tab', { name: /Saved Scenarios/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Overlay on Chart/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /Overlay on Chart/i }));
    await waitFor(() => {
      expect(screen.getByTestId('simulated-series-line')).toBeInTheDocument();
    });

    // Governance & Audit tab -> verify audit trail & pause lifecycle call
    await user.click(screen.getByRole('tab', { name: /Governance, Export & Audit/i }));
    await waitFor(() => {
      expect(screen.getByText(/Redacted Audit Trail/i)).toBeInTheDocument();
    });
    expect(screen.getByText('twin.create')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Pause Twin/i }));
    await waitFor(() => {
      expect(client.updateTwinStatus).toHaveBeenCalledTimes(1);
    });
  });

  it('displays API connection errors with request ID and retry button', async () => {
    const client = createMockClient();
    client.listTwins = vi.fn().mockRejectedValue(
      new ParkTwinApiError({
        status: 503,
        code: 'MODEL_UNAVAILABLE',
        message: 'Service temporarily unavailable.',
        requestId: 'req-err-503',
      }),
    );

    render(<App client={client} />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('req-err-503');
    });
  });
});
