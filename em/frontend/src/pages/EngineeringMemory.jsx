import React, { useEffect, useState } from 'react';
import { Search, Database, FileText, FlaskConical } from 'lucide-react';
import api from '../services/api';

function Provenance({ source }) {
  if (source === 'verified_field_diagnosis') return <span className="chip-success">Technician verified</span>;
  if (source === 'tata_industry_demo') {
    return (
      <span className="chip-amber">
        <FlaskConical className="h-2.5 w-2.5" />
        Demo data
      </span>
    );
  }
  return <span className="chip-neutral">Historical record</span>;
}

export default function EngineeringMemory() {
  const [query, setQuery] = useState('hydraulic pump internal leakage weak digging force hot oil');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get('/stats').then(setStats).catch(() => setStats(null));
  }, []);

  const search = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.get('/memory/search', { params: { query, top_k: 8 } });
      setResults(res);
    } catch (err) {
      setError('Engineering memory retrieval unavailable. Confirm the retrieval index is loaded.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="tech-label">Semantic search across the knowledge base</span>
          <span className="tech-value tnum">
            {stats
              ? `${stats.cases.total.toLocaleString()} cases · ${stats.index.vectors.toLocaleString()} vectors`
              : 'Index unavailable'}
          </span>
        </div>
        <form onSubmit={search} className="mt-3 flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-em-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. pressure drop when hot, pump slippage, slow boom under load"
              className="field pl-9"
            />
          </div>
          <button type="submit" disabled={busy} className="btn-amber px-5">
            {busy ? 'Searching…' : 'Search'}
          </button>
        </form>
        {error && <p className="mt-3 border-l-2 border-em-fault bg-em-faultSoft px-3 py-2 text-2xs text-em-fault">{error}</p>}
      </div>

      {results && (
        <>
          <div className="flex items-center justify-between border-b border-em-line pb-2">
            <span className="tech-label">Results for “{results.query}”</span>
            <span className="tech-value tnum">{results.total_results} matches</span>
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <div className="panel">
              <div className="panel-head">
                <span className="tech-label flex items-center gap-2">
                  <Database className="h-3.5 w-3.5 text-em-steel" />
                  Maintenance cases
                </span>
                <span className="tech-value tnum">{results.cases?.length || 0}</span>
              </div>
              <ul className="divide-y divide-em-line">
                {(results.cases || []).map((c) => (
                  <li key={c.case_id} className="p-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-em-graphite">{c.case_id}</span>
                      <div className="flex items-center gap-2">
                        <Provenance source={c.source_type} />
                        <span className="tech-value tnum">Sim {c.similarity}</span>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-em-graphite">
                      {c.failure_mode} <span className="text-em-steel">({c.component})</span>
                    </p>
                    <p className="mt-1 text-2xs leading-relaxed text-em-steel">{c.symptom}</p>
                    <p className="mt-1 text-2xs leading-relaxed text-em-success">Repair: {c.repair}</p>
                  </li>
                ))}
                {!results.cases?.length && <li className="p-4 text-xs text-em-muted">No cases matched.</li>}
              </ul>
            </div>

            <div className="panel">
              <div className="panel-head">
                <span className="tech-label flex items-center gap-2">
                  <FileText className="h-3.5 w-3.5 text-em-steel" />
                  Manual passages
                </span>
                <span className="tech-value tnum">{results.chunks?.length || 0}</span>
              </div>
              <ul className="divide-y divide-em-line">
                {(results.chunks || []).map((chk) => (
                  <li key={chk.chunk_id} className="p-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-em-graphite">{chk.document_name}</span>
                      <span className="tech-value tnum">Sim {chk.similarity}</span>
                    </div>
                    <span className="tech-value mt-0.5 block">
                      Page {chk.page_number} · {chk.section_heading}
                    </span>
                    <p className="mt-2 border-l-2 border-em-line pl-2.5 text-2xs leading-relaxed text-em-steel">
                      {chk.chunk_text?.slice(0, 420)}
                      {chk.chunk_text?.length > 420 ? '…' : ''}
                    </p>
                  </li>
                ))}
                {!results.chunks?.length && (
                  <li className="p-4 text-xs text-em-muted">No manual passages matched.</li>
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
