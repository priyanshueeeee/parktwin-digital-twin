import { render, screen, fireEvent } from '@testing-library/react';
import { TrajectoryChart } from '../src/charts/TrajectoryChart';
import type { SimulationData, TrajectoryPoint } from '../src/api/types';

const OBSERVED: TrajectoryPoint[] = [
  {
    observation_id: 'obs-1',
    timestamp: '2026-10-01T12:00:00+00:00',
    source_type: 'observed',
    total_updrs: 30.0,
    motor_updrs: 22.0,
    hypothetical: false,
  },
  {
    observation_id: 'obs-2',
    timestamp: '2026-10-20T12:00:00+00:00',
    source_type: 'observed',
    total_updrs: 33.5,
    motor_updrs: 24.5,
    hypothetical: false,
  },
];

const ESTIMATED: TrajectoryPoint[] = [
  {
    observation_id: 'obs-1',
    timestamp: '2026-10-01T12:00:00+00:00',
    source_type: 'estimated',
    total_updrs: 29.8,
    motor_updrs: 21.9,
    total_updrs_ci_low: 26.6,
    total_updrs_ci_high: 33.0,
    motor_updrs_ci_low: 19.3,
    motor_updrs_ci_high: 24.5,
    hypothetical: false,
  },
  {
    observation_id: 'obs-2',
    timestamp: '2026-10-20T12:00:00+00:00',
    source_type: 'estimated',
    total_updrs: 34.1,
    motor_updrs: 25.0,
    total_updrs_ci_low: 30.9,
    total_updrs_ci_high: 37.3,
    motor_updrs_ci_low: 22.4,
    motor_updrs_ci_high: 27.6,
    hypothetical: false,
  },
];

const SIMULATION: SimulationData = {
  scenario_id: 'sc-1',
  twin_id: 'tw-1',
  label: 'Levodopa + PT',
  hypothetical: true,
  status: 'completed',
  baseline_twin_version: 2,
  parameters: {
    levodopa_dose_change_mg: 150,
    physical_therapy_sessions_per_week: 3,
    adherence_ratio: 0.9,
  },
  horizon_days: 60,
  step_days: 30,
  assumptions_version: 'sim-assumptions-mock-v1',
  model_version: 'mock-updrs-v0.1.0',
  baseline_series: [
    {
      timestamp: '2026-10-20T12:00:00+00:00',
      source_type: 'estimated',
      total_updrs: 34.1,
      motor_updrs: 25.0,
      hypothetical: false,
    },
    {
      timestamp: '2026-12-19T12:00:00+00:00',
      source_type: 'estimated',
      total_updrs: 38.0,
      motor_updrs: 28.0,
      hypothetical: false,
    },
  ],
  scenario_series: [
    {
      timestamp: '2026-10-20T12:00:00+00:00',
      source_type: 'simulated',
      total_updrs: 34.1,
      motor_updrs: 25.0,
      total_updrs_ci_low: 31.1,
      total_updrs_ci_high: 37.1,
      hypothetical: true,
    },
    {
      timestamp: '2026-12-19T12:00:00+00:00',
      source_type: 'simulated',
      total_updrs: 32.5,
      motor_updrs: 23.8,
      total_updrs_ci_low: 27.1,
      total_updrs_ci_high: 37.9,
      hypothetical: true,
    },
  ],
  summary: {
    horizon_days: 60,
    baseline_end_total_updrs: 38.0,
    scenario_end_total_updrs: 32.5,
    delta_total_updrs: -5.5,
    baseline_end_motor_updrs: 28.0,
    scenario_end_motor_updrs: 23.8,
    delta_motor_updrs: -4.2,
    hypothetical: true,
  },
  created_at: '2026-10-20T12:05:00+00:00',
  disclaimer: 'Non-diagnostic research prototype.',
};

describe('TrajectoryChart', () => {
  it('renders observed, estimated, and hypothetical simulated series distinctly', () => {
    render(
      <TrajectoryChart
        observedPoints={OBSERVED}
        estimatedPoints={ESTIMATED}
        simulation={SIMULATION}
        metric="total_updrs"
      />,
    );

    expect(screen.getByTestId('observed-series-line')).not.toHaveAttribute('stroke-dasharray');
    expect(screen.getByTestId('estimated-series-line')).toHaveAttribute('stroke-dasharray', '6,4');
    expect(screen.getByTestId('simulated-series-line')).toHaveAttribute('stroke-dasharray', '2,4');
    expect(screen.getByTestId('hypothetical-region')).toBeInTheDocument();
    expect(screen.getByText(/HYPOTHETICAL FORECAST SANDBOX/i)).toBeInTheDocument();

    // Keyboard-accessible focus updates point inspector
    const marker = screen.getByRole('button', { name: /Observed Total UPDRS Score 30/i });
    fireEvent.focus(marker);
    expect(screen.getByText('Observed Clinical')).toBeInTheDocument();
    expect(screen.getByText(/30\.00 UPDRS/i)).toBeInTheDocument();
  });

  it('renders an empty state when no plottable points exist', () => {
    render(
      <TrajectoryChart
        observedPoints={[]}
        estimatedPoints={[]}
        simulation={null}
        metric="total_updrs"
      />,
    );
    expect(screen.getByText(/No plottable UPDRS series yet/i)).toBeInTheDocument();
  });
});
