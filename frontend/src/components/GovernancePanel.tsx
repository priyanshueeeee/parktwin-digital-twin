import { useState } from 'react';
import { ParkTwinApiError } from '../api/client';
import type { AuditEventItem, TwinRecord } from '../api/types';

interface GovernancePanelProps {
  twin: TwinRecord;
  activeScenarioId: string | null;
  auditEvents: AuditEventItem[];
  auditLoading: boolean;
  onChangeStatus: (status: 'active' | 'paused' | 'archived', reason: string) => Promise<void>;
  onRecompute: (reRunInference: boolean, reason: string) => Promise<void>;
  onExport: (format: 'json' | 'csv', includeScenario: boolean) => Promise<void>;
}

export function GovernancePanel({
  twin,
  activeScenarioId,
  auditEvents,
  auditLoading,
  onChangeStatus,
  onRecompute,
  onExport,
}: GovernancePanelProps) {
  const [reason, setReason] = useState('Routine clinical review lifecycle update');
  const [includeScenario, setIncludeScenario] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const runAction = async (label: string, fn: () => Promise<void>) => {
    setBusyAction(label);
    setFeedback(null);
    try {
      await fn();
      setFeedback({ kind: 'success', text: `${label} completed successfully.` });
    } catch (err) {
      if (err instanceof ParkTwinApiError) {
        setFeedback({ kind: 'error', text: `${err.message} [${err.code}, Req: ${err.requestId}]` });
      } else {
        setFeedback({ kind: 'error', text: `${label} failed.` });
      }
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="stack-md">
      {feedback && (
        <div
          className={`alert ${feedback.kind === 'error' ? 'alert-error' : 'alert-success'}`}
          role={feedback.kind === 'error' ? 'alert' : 'status'}
        >
          {feedback.text}
        </div>
      )}

      <div className="two-col-panels">
        <section className="panel" aria-labelledby="lifecycle-heading">
          <h3 id="lifecycle-heading">Twin Lifecycle &amp; State Recovery</h3>
          <p className="muted-text">
            Current status: <strong>{twin.status}</strong> (Version v{twin.version}). Pausing or archiving
            blocks new writes while preserving immutable history.
          </p>

          <div className="stack-sm" style={{ marginTop: '0.75rem' }}>
            <label className="field">
              <span>Audited Reason</span>
              <input
                type="text"
                value={reason}
                minLength={3}
                maxLength={256}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>

            <div className="action-row">
              {twin.status !== 'active' && twin.status !== 'insufficient_data' && (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busyAction !== null}
                  onClick={() => void runAction('Resume twin', () => onChangeStatus('active', reason))}
                >
                  Resume Active Tracking
                </button>
              )}
              {twin.status !== 'paused' && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busyAction !== null}
                  onClick={() => void runAction('Pause twin', () => onChangeStatus('paused', reason))}
                >
                  Pause Twin
                </button>
              )}
              {twin.status !== 'archived' && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busyAction !== null}
                  onClick={() => void runAction('Archive twin', () => onChangeStatus('archived', reason))}
                >
                  Archive Twin
                </button>
              )}
            </div>

            <hr className="divider" />

            <div>
              <strong>Recompute Derived State from Immutable History</strong>
              <p className="muted-text">
                Re-runs the currently registered model adapter across all raw observations without modifying observed records.
              </p>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ marginTop: '0.45rem' }}
                disabled={busyAction !== null}
                onClick={() =>
                  void runAction('Derived state recomputation', () =>
                    onRecompute(true, 'Model lineage recomputation from dashboard'),
                  )
                }
              >
                {busyAction === 'Derived state recomputation' ? 'Recomputing...' : 'Recompute with Active Model'}
              </button>
            </div>
          </div>
        </section>

        <section className="panel" aria-labelledby="export-heading">
          <h3 id="export-heading">Pseudonymous Research Export</h3>
          <p className="muted-text">
            Downloads include the non-diagnostic disclaimer, model/feature versions, and pseudonymous reference only.
          </p>

          <div className="stack-sm" style={{ marginTop: '0.75rem' }}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={includeScenario}
                disabled={!activeScenarioId}
                onChange={(e) => setIncludeScenario(e.target.checked)}
              />
              <span>
                Include currently overlaid hypothetical scenario{' '}
                {!activeScenarioId && <small className="muted-text">(no scenario overlaid)</small>}
              </span>
            </label>

            <div className="action-row">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busyAction !== null}
                onClick={() => void runAction('CSV export', () => onExport('csv', includeScenario))}
              >
                Download CSV Report
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busyAction !== null}
                onClick={() => void runAction('JSON export', () => onExport('json', includeScenario))}
              >
                Download JSON Bundle
              </button>
            </div>
          </div>
        </section>
      </div>

      <section className="panel" aria-labelledby="audit-heading">
        <div className="panel-header">
          <div>
            <h3 id="audit-heading">Redacted Audit Trail ({auditEvents.length})</h3>
            <p className="muted-text">
              Every create, update, read, simulation, status change, recompute, and export is logged with zero raw speech data or PII.
            </p>
          </div>
        </div>

        {auditLoading && auditEvents.length === 0 ? (
          <p role="status" aria-busy="true" className="muted-text">
            Loading audit events...
          </p>
        ) : auditEvents.length === 0 ? (
          <p className="muted-text">No audit events found for this twin.</p>
        ) : (
          <div className="table-wrap" tabIndex={0}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Timestamp (UTC)</th>
                  <th scope="col">Action</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Request ID</th>
                  <th scope="col">Redacted Metadata</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((ev) => (
                  <tr key={ev.id}>
                    <td>{new Date(ev.created_at).toISOString().replace('T', ' ').slice(0, 19)}</td>
                    <td>
                      <code>{ev.action}</code>
                    </td>
                    <td>{ev.actor_id}</td>
                    <td>
                      <span className={`status-badge ${ev.outcome === 'success' ? 'badge-ok' : 'badge-warn'}`}>
                        {ev.outcome}
                      </span>
                    </td>
                    <td>
                      <code>{ev.request_id}</code>
                    </td>
                    <td>
                      <code>{JSON.stringify(ev.details)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
