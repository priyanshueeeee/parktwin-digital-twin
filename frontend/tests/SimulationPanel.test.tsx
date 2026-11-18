import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SimulationPanel } from '../src/components/SimulationPanel';

describe('SimulationPanel', () => {
  it('requires explicit hypothetical acknowledgment before running simulation', async () => {
    const user = userEvent.setup();
    const onRun = vi.fn().mockResolvedValue(undefined);
    const onReset = vi.fn();

    render(
      <SimulationPanel
        canSimulate={true}
        activeSimulation={null}
        pending={false}
        onRunSimulation={onRun}
        onResetSimulation={onReset}
      />,
    );

    const runBtn = screen.getByRole('button', { name: /Run Simulation/i });
    expect(runBtn).toBeDisabled();

    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);
    expect(runBtn).toBeEnabled();

    await user.click(runBtn);
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenCalledWith(
      expect.objectContaining({
        acknowledge_hypothetical: true,
        horizon_days: 90,
      }),
    );
  });

  it('disables simulation controls when twin has no estimated baseline', () => {
    render(
      <SimulationPanel
        canSimulate={false}
        activeSimulation={null}
        pending={false}
        onRunSimulation={vi.fn()}
        onResetSimulation={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/At least one complete estimated speech observation is required/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run Simulation/i })).toBeDisabled();
  });
});
