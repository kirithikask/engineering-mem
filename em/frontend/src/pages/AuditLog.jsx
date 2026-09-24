import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ScrollText } from 'lucide-react';
import api from '../services/api';
import { EmptyState, Notice } from '../components/common/Evidence';

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [filters, setFilters] = useState({ action: '', machine_id: '', investigation_id: '' });
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [res, sum] = await Promise.all([
        api.get('/audit', { params: { limit: 200, ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) } }),
        api.get('/system/audit-summary'),
      ]);
      setLogs(res.logs || []);
      setTotal(res.total || 0);
      setSummary(sum);
      setError(null);
    } catch (err) {
      setError('The audit log requires administrator role.');
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      {error && <Notice tone="fault" title="Access">{error}</Notice>}

      {summary && (
        <div className="panel">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <ScrollText className="h-3.5 w-3.5 text-em-steel" />
              Recorded actions
            </span>
            <span className="tech-value">{summary.total_events} events</span>
          </div>
          <div className="flex flex-wrap gap-2 p-3.5">
            {summary.by_action.map((row) => (
              <button
                key={row.action}
                onClick={() => setFilters({ ...filters, action: filters.action === row.action ? '' : row.action })}
                className={`border px-2 py-1 text-2xs ${
                  filters.action === row.action ? 'border-em-amber bg-em-amberSoft text-em-amberDark' : 'border-em-line text-em-steel'
                }`}
              >
                {row.action.toLowerCase()} · {row.count}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label">Audit trail</span>
          <div className="flex items-center gap-2">
            <input
              className="field w-auto"
              placeholder="machine id"
              value={filters.machine_id}
              onChange={(e) => setFilters({ ...filters, machine_id: e.target.value })}
            />
            <input
              className="field w-auto"
              placeholder="investigation id"
              value={filters.investigation_id}
              onChange={(e) => setFilters({ ...filters, investigation_id: e.target.value })}
            />
            <button className="btn-ghost" onClick={load}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-2xs">
            <thead>
              <tr className="border-b border-em-line text-left">
                {['time', 'operator', 'role', 'action', 'entity', 'machine', 'investigation', 'outcome', 'detail'].map((header) => (
                  <th key={header} className="px-3 py-2 font-semibold uppercase tracking-label text-em-muted">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((row) => (
                <tr key={row.audit_id} className="border-b border-em-lineSoft align-top">
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{row.created_at}</td>
                  <td className="px-3 py-2">{row.username || 'anonymous'}</td>
                  <td className="px-3 py-2">{row.role || '—'}</td>
                  <td className="px-3 py-2 font-semibold text-em-graphite">{row.action}</td>
                  <td className="px-3 py-2 font-mono text-em-muted">{row.entity_type}:{row.entity_id}</td>
                  <td className="px-3 py-2 font-mono">{row.machine_id || '—'}</td>
                  <td className="px-3 py-2 font-mono">{row.investigation_id || '—'}</td>
                  <td className="px-3 py-2">
                    <span className={`chip-${row.outcome === 'OK' ? 'success' : 'fault'}`}>{row.outcome}</span>
                  </td>
                  <td className="max-w-[360px] px-3 py-2 text-em-steel">{JSON.stringify(row.detail)}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={9} className="p-4">
                    <EmptyState
                      title="No audit rows"
                      detail="Every state change in the platform writes one append-only row: who did it, to what, with which evidence."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-em-line p-3 text-2xs text-em-muted">
          Showing {logs.length} of {total} recorded events. Audit rows are append-only and are never edited or deleted.
        </div>
      </div>
    </div>
  );
}
