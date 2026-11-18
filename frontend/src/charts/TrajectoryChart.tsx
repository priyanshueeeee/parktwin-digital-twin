import { useMemo, useState } from 'react';
import * as d3 from 'd3';
import type { SimulationData, TrajectoryPoint } from '../api/types';

export type UpdrsMetric = 'total_updrs' | 'motor_updrs';

interface TrajectoryChartProps {
  observedPoints: TrajectoryPoint[];
  estimatedPoints: TrajectoryPoint[];
  simulation: SimulationData | null;
  metric: UpdrsMetric;
  simulationPending?: boolean;
}

interface RenderPoint {
  id: string;
  date: Date;
  timestamp: string;
  value: number;
  ciLow: number | null;
  ciHigh: number | null;
  sourceType: 'observed' | 'estimated' | 'simulated' | 'baseline_forecast';
  hypothetical: boolean;
  qualityFlags: string[];
}

const CHART_WIDTH = 860;
const CHART_HEIGHT = 360;
const MARGIN = { top: 28, right: 32, bottom: 52, left: 60 };
const INNER_W = CHART_WIDTH - MARGIN.left - MARGIN.right;
const INNER_H = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;

function extractValue(point: TrajectoryPoint, metric: UpdrsMetric): number | null {
  return metric === 'total_updrs' ? point.total_updrs : point.motor_updrs;
}

function extractCi(
  point: TrajectoryPoint,
  metric: UpdrsMetric,
): [number | null, number | null] {
  if (metric === 'total_updrs') {
    return [point.total_updrs_ci_low ?? null, point.total_updrs_ci_high ?? null];
  }
  return [point.motor_updrs_ci_low ?? null, point.motor_updrs_ci_high ?? null];
}

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function formatDateFull(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  }) + ' UTC';
}

function diamondPath(cx: number, cy: number, r: number): string {
  return `M ${cx} ${cy - r} L ${cx + r} ${cy} L ${cx} ${cy + r} L ${cx - r} ${cy} Z`;
}

function trianglePath(cx: number, cy: number, r: number): string {
  return `M ${cx} ${cy - r} L ${cx + r} ${cy + r * 0.85} L ${cx - r} ${cy + r * 0.85} Z`;
}

export function TrajectoryChart({
  observedPoints,
  estimatedPoints,
  simulation,
  metric,
  simulationPending = false,
}: TrajectoryChartProps) {
  const [activePoint, setActivePoint] = useState<RenderPoint | null>(null);

  const metricLabel = metric === 'total_updrs' ? 'Total UPDRS Score' : 'Motor UPDRS Score';

  const series = useMemo(() => {
    const mapPoints = (
      pts: TrajectoryPoint[],
      sourceType: RenderPoint['sourceType'],
      hypothetical: boolean,
    ): RenderPoint[] =>
      pts
        .map((pt, index) => {
          const val = extractValue(pt, metric);
          if (val === null || val === undefined) return null;
          const [ciLow, ciHigh] = extractCi(pt, metric);
          return {
            id: `${sourceType}-${pt.observation_id ?? index}-${pt.timestamp}`,
            date: new Date(pt.timestamp),
            timestamp: pt.timestamp,
            value: val,
            ciLow,
            ciHigh,
            sourceType,
            hypothetical,
            qualityFlags: pt.quality_flags ?? [],
          };
        })
        .filter((p): p is RenderPoint => p !== null)
        .sort((a, b) => a.date.getTime() - b.date.getTime());

    const observed = mapPoints(observedPoints, 'observed', false);
    const estimated = mapPoints(estimatedPoints, 'estimated', false);
    const baselineForecast = simulation
      ? mapPoints(simulation.baseline_series, 'baseline_forecast', false)
      : [];
    const simulated = simulation
      ? mapPoints(simulation.scenario_series, 'simulated', true)
      : [];

    return { observed, estimated, baselineForecast, simulated };
  }, [observedPoints, estimatedPoints, simulation, metric]);

  const allPoints = [
    ...series.observed,
    ...series.estimated,
    ...series.baselineForecast,
    ...series.simulated,
  ];

  if (allPoints.length === 0) {
    return (
      <div className="empty-chart" role="status" aria-live="polite">
        <strong>No plottable UPDRS series yet</strong>
        <p>
          Submit a complete 16-feature speech observation or baseline UPDRS score to render
          the longitudinal trajectory.
        </p>
      </div>
    );
  }

  const minDate = d3.min(allPoints, (p) => p.date) as Date;
  const maxDate = d3.max(allPoints, (p) => p.date) as Date;
  const padMs = minDate.getTime() === maxDate.getTime() ? 86_400_000 * 7 : (maxDate.getTime() - minDate.getTime()) * 0.06;

  const xScale = d3
    .scaleTime()
    .domain([new Date(minDate.getTime() - padMs), new Date(maxDate.getTime() + padMs)])
    .range([0, INNER_W]);

  const yValues = allPoints.flatMap((p) => [
    p.value,
    ...(p.ciLow != null ? [p.ciLow] : []),
    ...(p.ciHigh != null ? [p.ciHigh] : []),
  ]);
  const rawMinY = d3.min(yValues) ?? 0;
  const rawMaxY = d3.max(yValues) ?? 50;
  const yPad = Math.max(4, (rawMaxY - rawMinY) * 0.15);
  const yScale = d3
    .scaleLinear()
    .domain([Math.max(0, Math.floor(rawMinY - yPad)), Math.ceil(rawMaxY + yPad)])
    .nice()
    .range([INNER_H, 0]);

  const lineGen = d3
    .line<RenderPoint>()
    .x((d) => xScale(d.date))
    .y((d) => yScale(d.value));

  const ciAreaGen = d3
    .area<RenderPoint>()
    .defined((d) => d.ciLow != null && d.ciHigh != null)
    .x((d) => xScale(d.date))
    .y0((d) => yScale(d.ciLow as number))
    .y1((d) => yScale(d.ciHigh as number));

  const xTicks = xScale.ticks(6);
  const yTicks = yScale.ticks(5);

  const forecastStartDate = series.simulated.length > 0 ? series.simulated[0].date : null;
  const forecastStartX = forecastStartDate ? xScale(forecastStartDate) : null;

  return (
    <div className={`chart-shell ${simulationPending ? 'chart-pending' : ''}`}>
      <div className="chart-legend" aria-label="Trajectory series legend">
        <span className="legend-item">
          <svg width="26" height="12" aria-hidden="true">
            <line x1="2" y1="6" x2="24" y2="6" stroke="#0f766e" strokeWidth="2.5" />
            <circle cx="13" cy="6" r="4" fill="#0f766e" />
          </svg>
          <span>Observed UPDRS (solid, circle)</span>
        </span>
        <span className="legend-item">
          <svg width="26" height="12" aria-hidden="true">
            <line x1="2" y1="6" x2="24" y2="6" stroke="#4338ca" strokeWidth="2.5" strokeDasharray="5,3" />
            <path d={diamondPath(13, 6, 4.5)} fill="#4338ca" />
          </svg>
          <span>Model-Estimated UPDRS (dashed, diamond + CI band)</span>
        </span>
        {simulation && (
          <span className="legend-item legend-hypothetical">
            <svg width="26" height="12" aria-hidden="true">
              <line x1="2" y1="6" x2="24" y2="6" stroke="#c2410c" strokeWidth="2.5" strokeDasharray="2,3" />
              <path d={trianglePath(13, 6, 4.5)} fill="#c2410c" />
            </svg>
            <span>Hypothetical Simulation (dotted, triangle — NOT clinical evidence)</span>
          </span>
        )}
      </div>

      {simulationPending && (
        <div className="pending-pill" role="status" aria-live="polite">
          Recalculating hypothetical scenario (previous result remains visible)...
        </div>
      )}

      <svg
        className="trajectory-svg"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label={`${metricLabel} longitudinal trajectory chart showing observed, estimated, and any active hypothetical simulation series`}
      >
        <title>{metricLabel} Longitudinal Trajectory</title>
        <desc>
          Observed clinical UPDRS points are drawn with solid teal lines and circles; model-estimated
          UPDRS points use dashed indigo lines, diamonds, and a shaded confidence band; hypothetical
          intervention forecasts use dotted terracotta lines and triangles in a shaded forecast region.
        </desc>

        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {/* Hypothetical forecast backdrop region */}
          {forecastStartX !== null && (
            <g data-testid="hypothetical-region">
              <rect
                x={forecastStartX}
                y={0}
                width={Math.max(0, INNER_W - forecastStartX)}
                height={INNER_H}
                fill="#fff7ed"
              />
              <line
                x1={forecastStartX}
                x2={forecastStartX}
                y1={0}
                y2={INNER_H}
                stroke="#ea580c"
                strokeWidth="1.25"
                strokeDasharray="4,4"
              />
              <text
                x={Math.min(INNER_W - 8, forecastStartX + 8)}
                y={16}
                fill="#9a3412"
                fontSize="11"
                fontWeight="700"
              >
                HYPOTHETICAL FORECAST SANDBOX
              </text>
            </g>
          )}

          {/* Horizontal gridlines */}
          {yTicks.map((tick) => (
            <g key={`y-${tick}`} transform={`translate(0,${yScale(tick)})`}>
              <line x1={0} x2={INNER_W} stroke="#e2e8f0" strokeWidth="1" />
              <text x={-10} dy="0.32em" textAnchor="end" fontSize="11" fill="#475569">
                {tick}
              </text>
            </g>
          ))}

          {/* X-axis ticks */}
          <line x1={0} x2={INNER_W} y1={INNER_H} y2={INNER_H} stroke="#94a3b8" strokeWidth="1.2" />
          <line x1={0} x2={0} y1={0} y2={INNER_H} stroke="#94a3b8" strokeWidth="1.2" />
          {xTicks.map((tick) => (
            <g key={`x-${tick.getTime()}`} transform={`translate(${xScale(tick)},${INNER_H})`}>
              <line y2={6} stroke="#94a3b8" />
              <text y={22} textAnchor="middle" fontSize="11" fill="#475569">
                {formatDateShort(tick)}
              </text>
            </g>
          ))}

          {/* Axis labels */}
          <text
            x={INNER_W / 2}
            y={INNER_H + 42}
            textAnchor="middle"
            fontSize="12"
            fontWeight="600"
            fill="#334155"
          >
            Observation / Forecast Date (UTC)
          </text>
          <text
            transform="rotate(-90)"
            x={-INNER_H / 2}
            y={-44}
            textAnchor="middle"
            fontSize="12"
            fontWeight="600"
            fill="#334155"
          >
            {metricLabel} (points)
          </text>

          {/* Model estimated CI band */}
          {series.estimated.length >= 2 && (
            <path
              d={ciAreaGen(series.estimated) ?? ''}
              fill="#6366f1"
              fillOpacity={0.14}
              data-testid="estimated-ci-band"
            />
          )}

          {/* Simulation uncertainty band */}
          {series.simulated.length >= 2 && (
            <path
              d={ciAreaGen(series.simulated) ?? ''}
              fill="#fb923c"
              fillOpacity={0.16}
              data-testid="simulated-ci-band"
            />
          )}

          {/* Baseline projection line during simulation */}
          {series.baselineForecast.length >= 2 && (
            <path
              d={lineGen(series.baselineForecast) ?? ''}
              fill="none"
              stroke="#64748b"
              strokeWidth="2"
              strokeDasharray="6,4"
              data-testid="baseline-projection-line"
            />
          )}

          {/* Model estimated series line */}
          {series.estimated.length >= 2 && (
            <path
              d={lineGen(series.estimated) ?? ''}
              fill="none"
              stroke="#4338ca"
              strokeWidth="2.5"
              strokeDasharray="6,4"
              data-testid="estimated-series-line"
            />
          )}

          {/* Observed clinical series line */}
          {series.observed.length >= 2 && (
            <path
              d={lineGen(series.observed) ?? ''}
              fill="none"
              stroke="#0f766e"
              strokeWidth="2.5"
              data-testid="observed-series-line"
            />
          )}

          {/* Hypothetical simulated series line */}
          {series.simulated.length >= 2 && (
            <path
              d={lineGen(series.simulated) ?? ''}
              fill="none"
              stroke="#c2410c"
              strokeWidth="2.75"
              strokeDasharray="2,4"
              data-testid="simulated-series-line"
            />
          )}

          {/* Estimated diamond markers */}
          {series.estimated.map((pt) => (
            <path
              key={pt.id}
              d={diamondPath(xScale(pt.date), yScale(pt.value), 5.5)}
              fill="#4338ca"
              stroke="#ffffff"
              strokeWidth="1.5"
              tabIndex={0}
              role="button"
              aria-label={`Model estimated ${metricLabel} ${pt.value} on ${formatDateFull(pt.timestamp)}`}
              onMouseEnter={() => setActivePoint(pt)}
              onFocus={() => setActivePoint(pt)}
              onMouseLeave={() => setActivePoint(null)}
              onBlur={() => setActivePoint(null)}
              className="chart-marker"
            />
          ))}

          {/* Observed circle markers */}
          {series.observed.map((pt) => (
            <circle
              key={pt.id}
              cx={xScale(pt.date)}
              cy={yScale(pt.value)}
              r={5.5}
              fill="#0f766e"
              stroke="#ffffff"
              strokeWidth="1.75"
              tabIndex={0}
              role="button"
              aria-label={`Observed ${metricLabel} ${pt.value} on ${formatDateFull(pt.timestamp)}`}
              onMouseEnter={() => setActivePoint(pt)}
              onFocus={() => setActivePoint(pt)}
              onMouseLeave={() => setActivePoint(null)}
              onBlur={() => setActivePoint(null)}
              className="chart-marker"
            />
          ))}

          {/* Simulated triangle markers */}
          {series.simulated.map((pt) => (
            <path
              key={pt.id}
              d={trianglePath(xScale(pt.date), yScale(pt.value), 6)}
              fill="#c2410c"
              stroke="#ffffff"
              strokeWidth="1.5"
              tabIndex={0}
              role="button"
              aria-label={`Hypothetical simulated ${metricLabel} ${pt.value} on ${formatDateFull(pt.timestamp)}`}
              onMouseEnter={() => setActivePoint(pt)}
              onFocus={() => setActivePoint(pt)}
              onMouseLeave={() => setActivePoint(null)}
              onBlur={() => setActivePoint(null)}
              className="chart-marker"
            />
          ))}
        </g>
      </svg>

      <div className="chart-inspector" aria-live="polite">
        {activePoint ? (
          <div>
            <span className={`source-chip source-${activePoint.sourceType}`}>
              {activePoint.sourceType === 'observed' && 'Observed Clinical'}
              {activePoint.sourceType === 'estimated' && 'Model-Estimated'}
              {activePoint.sourceType === 'simulated' && 'Hypothetical Simulation'}
              {activePoint.sourceType === 'baseline_forecast' && 'Baseline Projection'}
            </span>{' '}
            <strong>{activePoint.value.toFixed(2)} UPDRS</strong>
            {activePoint.ciLow != null && activePoint.ciHigh != null && (
              <span>
                {' '}
                (interval: {activePoint.ciLow.toFixed(1)}–{activePoint.ciHigh.toFixed(1)})
              </span>
            )}{' '}
            on {formatDateFull(activePoint.timestamp)}
            {activePoint.qualityFlags.length > 0 && (
              <span className="flag-note"> — Flags: {activePoint.qualityFlags.join(', ')}</span>
            )}
          </div>
        ) : (
          <span className="muted-text">
            Hover or focus any chart marker with Tab to inspect exact timestamp, UPDRS score, and uncertainty interval.
          </span>
        )}
      </div>
    </div>
  );
}
