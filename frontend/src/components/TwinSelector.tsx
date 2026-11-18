import { useMemo, useState } from 'react';
import type { TwinListItem } from '../api/types';

interface TwinSelectorProps {
  twins: TwinListItem[];
  selectedTwinId: string | null;
  loading: boolean;
  onSelect: (twinId: string) => void;
  onOpenCreate: () => void;
  onRefresh: () => void;
}

type StatusFilter = 'all' | 'active' | 'insufficient_data' | 'paused' | 'archived' | 'stale';

function statusCue(twin: TwinListItem): { symbol: string; label: string; className: string } {
  if (twin.status === 'archived') {
    return { symbol: '■', label: 'Archived', className: 'badge-archived' };
  }
  if (twin.status === 'paused') {
    return { symbol: '❚❚', label: 'Paused', className: 'badge-stale' };
  }
  if (twin.status === 'insufficient_data') {
    return { symbol: '△', label: 'Insufficient data', className: 'badge-warn' };
  }
  if (twin.is_stale) {
    return { symbol: '◷', label: 'Stale data', className: 'badge-stale' };
  }
  return { symbol: '●', label: 'Active', className: 'badge-ok' };
}

export function TwinSelector({
  twins,
  selectedTwinId,
  loading,
  onSelect,
  onOpenCreate,
  onRefresh,
}: TwinSelectorProps) {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const filteredTwins = useMemo(() => {
    const q = query.trim().toLowerCase();
    return twins.filter((twin) => {
      if (q && !twin.external_reference.toLowerCase().includes(q)) return false;
      if (statusFilter === 'all') return true;
      if (statusFilter === 'stale') return twin.is_stale;
      return twin.status === statusFilter;
    });
  }, [twins, query, statusFilter]);

  return (
    <nav className="sidebar-panel" aria-label="Digital twin selection">
      <div className="sidebar-header">
        <div>
          <h2>Digital Twins ({twins.length})</h2>
          <p className="muted-text">Pseudonymous cohorts only</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRefresh} disabled={loading}>
          Refresh
        </button>
      </div>

      <button type="button" className="btn btn-primary btn-full" onClick={onOpenCreate}>
        + Initialize Baseline Twin
      </button>

      <div className="sidebar-filters">
        <label className="sr-only" htmlFor="twin-search-input">
          Search pseudonymous twin reference
        </label>
        <input
          id="twin-search-input"
          type="search"
          className="search-input"
          placeholder="Filter by pseudonymous ID..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="filter-pills" role="group" aria-label="Filter twins by status">
          {(
            [
              ['all', 'All'],
              ['active', 'Active'],
              ['insufficient_data', 'Insufficient'],
              ['stale', 'Stale'],
              ['paused', 'Paused'],
              ['archived', 'Archived'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`pill-btn ${statusFilter === key ? 'pill-btn-active' : ''}`}
              aria-pressed={statusFilter === key}
              onClick={() => setStatusFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && twins.length === 0 ? (
        <div className="sidebar-state" role="status" aria-busy="true">
          Loading digital twins...
        </div>
      ) : filteredTwins.length === 0 ? (
        <div className="sidebar-state" role="status">
          <strong>{twins.length === 0 ? 'No twins initialized' : 'No matching twins'}</strong>
          <p>
            {twins.length === 0
              ? 'Create a synthetic baseline twin or run the demo seed script to begin.'
              : 'Adjust the search or status filter to view other cohorts.'}
          </p>
        </div>
      ) : (
        <ul className="twin-list" role="listbox" aria-label="Available pseudonymous twins">
          {filteredTwins.map((twin) => {
            const cue = statusCue(twin);
            const selected = twin.id === selectedTwinId;
            return (
              <li key={twin.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`twin-card ${selected ? 'twin-card-selected' : ''}`}
                  onClick={() => onSelect(twin.id)}
                >
                  <div className="twin-card-top">
                    <span className="twin-ref">{twin.external_reference}</span>
                    <span className={`status-badge ${cue.className}`}>
                      <span aria-hidden="true">{cue.symbol}</span> {cue.label}
                    </span>
                  </div>
                  <div className="twin-card-meta">
                    <span>
                      Total UPDRS:{' '}
                      <strong>
                        {twin.latest_total_updrs !== null ? twin.latest_total_updrs.toFixed(1) : 'N/A'}
                      </strong>
                    </span>
                    <span>{twin.observation_count} obs</span>
                  </div>
                  <div className="twin-card-foot">
                    <span>
                      Slope:{' '}
                      {twin.slope_status === 'computed' && twin.slope_total_per_30_days !== null
                        ? `${twin.slope_total_per_30_days >= 0 ? '+' : ''}${twin.slope_total_per_30_days.toFixed(2)}/30d`
                        : 'Insufficient history'}
                    </span>
                    <span>v{twin.version}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
