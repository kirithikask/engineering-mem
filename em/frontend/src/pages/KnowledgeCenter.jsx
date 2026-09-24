import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BookOpenCheck, Layers, RefreshCw, Scale } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { DemoChip, EmptyState, Notice, QualityChip } from '../components/common/Evidence';

const STATUS_FILTERS = ['', 'DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED'];
const QUALITY_FILTERS = ['', 'UNVERIFIED', 'TECHNICIAN_SUBMITTED', 'ENGINEER_REVIEWED', 'VERIFIED'];

export default function KnowledgeCenter() {
  const { user } = useAuth();
  const [overview, setOverview] = useState(null);
  const [items, setItems] = useState({ items: [], total: 0 });
  const [conflicts, setConflicts] = useState([]);
  const [levels, setLevels] = useState(null);
  const [filters, setFilters] = useState({ status: '', quality_level: '' });
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    try {
      const [ov, list, conf, lvl] = await Promise.all([
        api.get('/knowledge/overview'),
        api.get('/knowledge', { params: { status: filters.status || undefined, quality_level: filters.quality_level || undefined } }),
        api.get('/knowledge/conflicts'),
        api.get('/knowledge/quality-levels'),
      ]);
      setOverview(ov);
      setItems(list);
      setConflicts(conf.conflicts || []);
      setLevels(lvl);
    } catch (err) {
      setMessage({ tone: 'fault', text: 'Knowledge center data could not be loaded.' });
    }
  }, [filters.status, filters.quality_level]);

  useEffect(() => {
    load();
  }, [load]);

  const reindex = async () => {
    setBusy('reindex');
    try {
      const res = await api.post('/knowledge/reindex', { note: `reindex requested by ${user?.username}` });
      setMessage({ tone: 'info', text: `Rebuild started (${res.job_id}). It runs in the background; refresh the vector database page to watch progress.` });
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'Reindex could not be started (administrator role required).' });
    } finally {
      setBusy(null);
    }
  };

  const resolveConflict = async (conflictId) => {
    setBusy(conflictId);
    try {
      await api.post(`/knowledge/conflicts/${conflictId}/resolve`, {
        resolution: 'Reviewed by engineer; both sources retained, current approved revision takes priority.',
      });
      await load();
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'The conflict could not be resolved.' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      {message && <Notice tone={message.tone} title="Knowledge center">{message.text}</Notice>}

      {overview && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          {[
            { label: 'Knowledge items', value: overview.knowledge_items },
            { label: 'Documents', value: overview.documents },
            { label: 'Document passages', value: overview.document_chunks },
            { label: 'Awaiting review', value: overview.pending_reviews },
            { label: 'Open conflicts', value: overview.open_conflicts },
            { label: 'Investigations', value: overview.investigations },
            { label: 'Failed attempts kept', value: overview.failed_attempts },
            { label: 'Indexed passages', value: overview.vector_index?.vectors },
            { label: 'Embedding dim', value: overview.vector_index?.dimension },
            { label: 'Retrieval calls logged', value: overview.retrieval_latency?.measurements ?? 0 },
            {
              label: 'Mean retrieval',
              value: overview.retrieval_latency?.mean_latency_ms != null ? `${overview.retrieval_latency.mean_latency_ms} ms` : '—',
            },
            { label: 'Approved safety procedures', value: overview.verified_safety_procedures },
          ].map((card) => (
            <div key={card.label} className="panel p-3">
              <p className="tech-label">{card.label}</p>
              <p className="tnum mt-1 text-lg font-bold text-em-graphite">{card.value ?? '—'}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-8">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <BookOpenCheck className="h-3.5 w-3.5 text-em-steel" />
              Engineering knowledge
            </span>
            <div className="flex items-center gap-2">
              <select className="field w-auto" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
                {STATUS_FILTERS.map((status) => (
                  <option key={status || 'all'} value={status}>{status ? status.replace('_', ' ').toLowerCase() : 'all statuses'}</option>
                ))}
              </select>
              <select className="field w-auto" value={filters.quality_level} onChange={(e) => setFilters({ ...filters, quality_level: e.target.value })}>
                {QUALITY_FILTERS.map((level) => (
                  <option key={level || 'all'} value={level}>{level ? level.replace('_', ' ').toLowerCase() : 'all quality levels'}</option>
                ))}
              </select>
            </div>
          </div>
          <ul className="divide-y divide-em-line">
            {items.items.map((item) => (
              <li key={item.knowledge_id} className="px-3.5 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-2xs font-bold text-em-navy">{item.knowledge_id}</span>
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold text-em-graphite">{item.title}</span>
                  <QualityChip level={item.quality_level} compact />
                  <span className={`chip-${item.status === 'APPROVED' ? 'success' : item.status === 'REJECTED' ? 'fault' : 'amber'}`}>
                    {item.status.toLowerCase()}
                  </span>
                  <DemoChip show={String(item.source_type || '').includes('demo')} />
                  {item.vector_id != null && item.vector_id >= 0 && (
                    <span className="font-mono text-2xs text-em-muted">vector {item.vector_id}</span>
                  )}
                </div>
                <p className="mt-1 text-2xs text-em-steel">
                  {item.machine_id} · {item.component || 'component not stated'} · {item.failure_mode || 'failure mode not stated'}
                </p>
                <p className="text-2xs text-em-muted">
                  {item.investigation_id ? `from ${item.investigation_id} · ` : ''}
                  created {item.created_at}
                  {item.approved_by_name ? ` · approved by ${item.approved_by_name}` : ''}
                </p>
              </li>
            ))}
            {items.items.length === 0 && (
              <li className="p-4">
                <EmptyState
                  title="No knowledge items"
                  detail="Completed investigations become knowledge here after expert review — including the failed attempts that did not work."
                />
              </li>
            )}
          </ul>
          <div className="flex items-center gap-2 border-t border-em-line p-3">
            <span className="text-2xs text-em-muted">{items.total} item(s) match the filter</span>
            <button className="btn-ghost ml-auto" onClick={load}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
            <button className="btn-outline" onClick={reindex} disabled={busy === 'reindex'}>
              <Layers className="h-3.5 w-3.5" />
              {busy === 'reindex' ? 'Starting…' : 'Rebuild vector index'}
            </button>
          </div>
        </div>

        <div className="space-y-5 lg:col-span-4">
          <div className="panel">
            <div className="panel-head">
              <span className="tech-label flex items-center gap-2">
                <Scale className="h-3.5 w-3.5 text-em-steel" />
                Knowledge quality levels
              </span>
            </div>
            <div className="space-y-2 p-3">
              {levels?.levels?.map((level) => (
                <div key={level} className="border border-em-line p-2">
                  <div className="flex items-center gap-2">
                    <QualityChip level={level} />
                    <span className="ml-auto font-mono text-2xs text-em-muted">
                      weight {(levels.retrieval_weights?.quality?.[level] ?? 0).toFixed(2)}
                    </span>
                  </div>
                  <p className="mt-1 text-2xs leading-relaxed text-em-steel">{levels.meaning[level]}</p>
                </div>
              ))}
              <p className="text-2xs text-em-muted">
                Retrieval ranks {levels?.retrieval_weights?.score}. Document status priority:{' '}
                {Object.entries(levels?.retrieval_weights?.document_status || {})
                  .map(([status, weight]) => `${status} ${Number(weight).toFixed(2)}`)
                  .join(' · ')}
              </p>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="tech-label flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 text-em-warning" />
                Conflicting engineering information
              </span>
              <span className="tech-value">{conflicts.length}</span>
            </div>
            <div className="space-y-2 p-3">
              {conflicts.length === 0 && (
                <p className="text-2xs text-em-muted">
                  No conflicting values detected. Conflicts are only raised when two authoritative sources state different
                  values for the same measured quantity — they are never resolved automatically.
                </p>
              )}
              {conflicts.map((conflict) => {
                const a = conflict.source_a || {};
                const b = conflict.source_b || {};
                return (
                  <div key={conflict.conflict_id} className="border border-em-line border-l-2 border-l-em-warning bg-em-amberSoft/30 p-2">
                    <p className="text-2xs font-bold uppercase tracking-label text-em-warning">{conflict.severity} · {conflict.topic}</p>
                    <p className="mt-1 text-2xs text-em-steel">
                      Current approved: {a.document} rev {a.revision} — {a.value} {a.unit}
                    </p>
                    <p className="text-2xs text-em-steel">
                      Superseded: {b.document} rev {b.revision} — {b.value} {b.unit}
                    </p>
                    <div className="mt-1 flex items-center gap-2">
                      <span className={`chip-${conflict.status === 'OPEN' ? 'fault' : 'success'}`}>{conflict.status}</span>
                      <span className="font-mono text-2xs text-em-muted">{conflict.detected_by}</span>
                      {conflict.status === 'OPEN' && (
                        <button className="btn-ghost ml-auto" onClick={() => resolveConflict(conflict.conflict_id)} disabled={busy === conflict.conflict_id}>
                          Mark reviewed
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
