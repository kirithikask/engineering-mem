import React, { useCallback, useEffect, useState } from 'react';
import { Activity, Boxes, Database, Search } from 'lucide-react';
import api from '../services/api';
import { DemoChip, EmptyState, Notice, QualityChip, StatusChip, SupersededChip } from '../components/common/Evidence';

export default function VectorDatabase() {
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({});
  const [query, setQuery] = useState('slow boom movement and weak digging force');
  const [activeFilters, setActiveFilters] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    try {
      const [vectorDb, options] = await Promise.all([api.get('/system/vector-db'), api.get('/retrieval/filters')]);
      setStats(vectorDb);
      setFilters(options);
    } catch (err) {
      setMessage({ tone: 'fault', text: 'Vector database state could not be read.' });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runSearch = async () => {
    setBusy('search');
    setResult(null);
    try {
      const res = await api.post('/retrieval/search', {
        query,
        filters: Object.fromEntries(Object.entries(activeFilters).filter(([, value]) => value)),
        top_k: 10,
      });
      setResult(res);
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'The retrieval test failed.' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      {message && <Notice tone={message.tone} title="Vector database">{message.text}</Notice>}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Database className="h-3.5 w-3.5 text-em-steel" />
              Index state (read from the running process)
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 p-3.5">
            {[
              { label: 'Vectors', value: stats?.vectors },
              { label: 'Dimension', value: stats?.dimension },
              { label: 'Index type', value: stats?.index_type },
              { label: 'Embedding model', value: stats?.embedding_model },
              { label: 'Mapping entries', value: stats?.mapping_entries },
              { label: 'Embedding records', value: stats?.embedding_records },
              { label: 'Document passages', value: stats?.document_chunks_total },
              { label: 'Passages approved', value: stats?.document_chunks_approved },
              { label: 'Maintenance cases', value: stats?.maintenance_cases_total },
              { label: 'Approved knowledge', value: stats?.approved_knowledge_total },
              { label: 'Knowledge indexed', value: stats?.approved_knowledge_indexed },
              { label: 'Retrieval measurements', value: stats?.retrieval_latency?.measurements ?? 0 },
            ].map((row) => (
              <div key={row.label} className="border border-em-line p-2">
                <p className="tech-label">{row.label}</p>
                <p className="tnum mt-0.5 text-sm text-em-graphite">{row.value ?? '—'}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-em-line p-3.5">
            <p className="tech-label">Measured retrieval latency</p>
            <p className="mt-1 text-2xs text-em-steel">
              {stats?.retrieval_latency?.measurements
                ? `mean ${stats.retrieval_latency.mean_latency_ms} ms · min ${stats.retrieval_latency.min_latency_ms} ms · max ${stats.retrieval_latency.max_latency_ms} ms over ${stats.retrieval_latency.measurements} logged retrievals`
                : 'No retrieval has been logged yet, so no latency figure is reported.'}
            </p>
            <p className="mt-2 text-2xs text-em-muted">{stats?.rebuild_note}</p>
            <p className="mt-1 font-mono text-2xs text-em-muted">{stats?.index_path} · {stats?.mapping_path}</p>
          </div>
        </div>

        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Search className="h-3.5 w-3.5 text-em-steel" />
              Retrieval test bench
            </span>
            <span className="tech-value">hybrid: semantic + metadata + quality + version</span>
          </div>
          <div className="space-y-3 p-3.5">
            <div className="flex flex-wrap gap-2">
              <input className="field flex-1" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Retrieval query" />
              <button className="btn-amber" onClick={runSearch} disabled={busy === 'search'}>
                {busy === 'search' ? 'Searching…' : 'Run retrieval'}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <label className="block">
                <span className="tech-label">Component</span>
                <select className="field mt-1" value={activeFilters.component || ''} onChange={(e) => setActiveFilters({ ...activeFilters, component: e.target.value })}>
                  <option value="">any</option>
                  {(filters.components || []).map((component) => (
                    <option key={component} value={component}>{component}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="tech-label">Document status</span>
                <select className="field mt-1" value={activeFilters.document_status || ''} onChange={(e) => setActiveFilters({ ...activeFilters, document_status: e.target.value })}>
                  <option value="">any</option>
                  {(filters.document_status || []).map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="tech-label">Quality level</span>
                <select className="field mt-1" value={activeFilters.quality_level || ''} onChange={(e) => setActiveFilters({ ...activeFilters, quality_level: e.target.value })}>
                  <option value="">any</option>
                  {(filters.quality_levels || []).map((level) => (
                    <option key={level} value={level}>{level}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="tech-label">Revision</span>
                <select className="field mt-1" value={activeFilters.revision || ''} onChange={(e) => setActiveFilters({ ...activeFilters, revision: e.target.value })}>
                  <option value="">any</option>
                  {(filters.revisions || []).map((revision) => (
                    <option key={revision} value={revision}>{revision}</option>
                  ))}
                </select>
              </label>
            </div>

            {result && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 border border-em-line bg-em-paper p-2 text-2xs">
                  <span className="chip-navy">candidates {result.counts?.candidates}</span>
                  <span className="chip-neutral">after filters {result.counts?.after_filters ?? 0}</span>
                  <span className="chip-neutral">returned {result.counts?.returned}</span>
                  <span className="chip-neutral">embedding {result.timings?.embedding_ms} ms</span>
                  <span className="chip-neutral">faiss {result.timings?.faiss_ms} ms</span>
                  <span className="chip-amber">total {result.timings?.latency_ms} ms</span>
                  <span className="chip-navy">index {result.index?.vectors} × {result.index?.dimension}</span>
                  <span className="ml-auto font-mono text-em-muted">{result.retrieval_id || 'not logged'}</span>
                </div>

                {(result.conflicts || []).length > 0 && (
                  <Notice tone="warning" title="Conflicting engineering information">
                    {result.conflicts.map((conflict) => (
                      <p key={conflict.topic}>
                        {conflict.topic} ({conflict.unit}): {conflict.sources.map((source) => `${source.value} from ${source.id}`).join(' vs ')}
                      </p>
                    ))}
                  </Notice>
                )}

                <div className="max-h-[520px] space-y-2 overflow-y-auto">
                  {(result.evidence || []).map((item) => (
                    <div key={`${item.evidence_type}-${item.id}`} className="border border-em-line p-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-2xs font-bold text-em-graphite">{item.id}</span>
                        <QualityChip level={item.quality_level} compact />
                        <StatusChip status={item.document_status} revision={item.revision} />
                        <SupersededChip show={item.superseded} />
                        <DemoChip show={item.demo_data} />
                        <span className="ml-auto font-mono text-2xs text-em-muted tnum">
                          sim {Number(item.similarity).toFixed(3)} × quality {Number(item.quality_weight).toFixed(2)} × status{' '}
                          {Number(item.version_priority).toFixed(2)} × priority {Number(item.source_priority).toFixed(2)} = {Number(item.effective_score).toFixed(3)}
                        </span>
                      </div>
                      <p className="mt-1 text-2xs font-semibold text-em-graphite">
                        {item.evidence_type === 'chunk'
                          ? `${item.document_name} — page ${item.page_number} · ${item.section_heading || 'no section'}`
                          : item.title}
                      </p>
                      <p className="mt-0.5 text-2xs leading-relaxed text-em-steel">
                        {(item.chunk_text || item.symptom || '').slice(0, 320)}
                      </p>
                      <p className="mt-1 font-mono text-2xs text-em-muted">
                        ranking: {item.source_priority_reason} · lexical overlap {item.lexical_overlap ?? '—'}
                      </p>
                    </div>
                  ))}
                  {(result.evidence || []).length === 0 && (
                    <EmptyState title="No evidence matched" detail="Insufficient evidence is a valid result: nothing is invented to fill the gap." />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Activity className="h-3.5 w-3.5 text-em-steel" />
              Recent retrievals
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-2xs">
              <thead>
                <tr className="border-b border-em-line text-left">
                  {['retrieval', 'query', 'results', 'top score', 'latency', 'embedding', 'index size', 'time'].map((header) => (
                    <th key={header} className="px-3 py-2 font-semibold uppercase tracking-label text-em-muted">{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(stats?.recent_retrievals || []).map((row) => (
                  <tr key={row.retrieval_id} className="border-b border-em-lineSoft">
                    <td className="px-3 py-2 font-mono text-navy">{row.retrieval_id}</td>
                    <td className="max-w-[260px] truncate px-3 py-2">{row.query_text}</td>
                    <td className="px-3 py-2 tnum">{row.result_count}</td>
                    <td className="px-3 py-2 tnum">{Number(row.top_score || 0).toFixed(3)}</td>
                    <td className="px-3 py-2 tnum">{Number(row.latency_ms || 0).toFixed(1)} ms</td>
                    <td className="px-3 py-2 tnum">{Number(row.embedding_ms || 0).toFixed(1)} ms</td>
                    <td className="px-3 py-2 tnum">{row.index_vector_count}</td>
                    <td className="px-3 py-2 font-mono text-em-muted">{row.created_at}</td>
                  </tr>
                ))}
                {(stats?.recent_retrievals || []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="p-4">
                      <EmptyState title="No retrieval recorded yet" detail="Run a retrieval test above; each call is logged with its measured latency." />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Boxes className="h-3.5 w-3.5 text-em-steel" />
              Index versions
            </span>
          </div>
          <ul className="divide-y divide-em-line">
            {(stats?.index_versions || []).map((version) => (
              <li key={version.index_version_id} className="px-3.5 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-2xs font-bold text-em-graphite">{version.index_version_id}</span>
                  <span className="chip-neutral">{version.operation}</span>
                  {version.is_current === 1 && <span className="chip-success">current</span>}
                  <span className="ml-auto font-mono text-2xs text-em-muted tnum">
                    {version.vector_count} × {version.dimension} · +{version.added_count}
                  </span>
                </div>
                <p className="mt-0.5 text-2xs text-em-steel">{version.model_name} · {version.note}</p>
                <p className="text-2xs text-em-muted">
                  {version.created_at} {version.created_by ? `· ${version.created_by}` : ''}
                </p>
              </li>
            ))}
            {(stats?.index_versions || []).length === 0 && (
              <li className="p-4">
                <EmptyState title="No recorded index versions" detail="Approving a document or knowledge item records a new index version." />
              </li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
