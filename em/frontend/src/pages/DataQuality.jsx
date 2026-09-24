import React, { useEffect, useState } from 'react';
import { BarChart3, FlaskConical, ShieldAlert } from 'lucide-react';
import api from '../services/api';
import { EmptyState, Notice } from '../components/common/Evidence';

export default function DataQuality() {
  const [overview, setOverview] = useState(null);
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/knowledge/overview'),
      api.get('/system/vector-db'),
      api.get('/ingestion/jobs', { params: { limit: 200 } }),
    ])
      .then(([ov, vectorDb, jobRows]) => {
        setOverview(ov);
        setStats(vectorDb);
        setJobs(jobRows.jobs || []);
      })
      .catch(() => setError('Data quality metrics could not be read from the backend.'));
  }, []);

  if (error) return <Notice tone="fault" title="Unavailable">{error}</Notice>;
  if (!overview) return <p className="text-xs text-em-steel">Reading quality metrics…</p>;

  const byQuality = overview.knowledge_by_quality || [];
  const totalItems = byQuality.reduce((sum, row) => sum + row.count, 0);
  const confidenceJobs = jobs.filter((job) => job.extraction_confidence > 0);
  const meanConfidence = confidenceJobs.length
    ? confidenceJobs.reduce((sum, job) => sum + job.extraction_confidence, 0) / confidenceJobs.length
    : null;
  const unreadable = jobs.filter((job) => job.status === 'OCR_ENGINE_UNAVAILABLE' || job.status === 'REVIEW_REQUIRED');
  const failed = jobs.filter((job) => job.status === 'EXTRACTION_FAILED');

  return (
    <div className="space-y-5">
      <Notice tone="warning" title="Provenance policy">
        Prototype and synthetic records are labelled wherever they appear. The public hydraulic test-rig dataset is used
        only as supporting condition evidence and is never presented as live excavator telemetry. No metric on this page is
        estimated — every figure is counted from the database or read from the running index.
      </Notice>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-6">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <BarChart3 className="h-3.5 w-3.5 text-em-steel" />
              Knowledge quality distribution
            </span>
            <span className="tech-value">{totalItems} item(s)</span>
          </div>
          <div className="space-y-2 p-3.5">
            {byQuality.length === 0 && <EmptyState title="No knowledge items recorded yet" />}
            {byQuality.map((row) => {
              const pct = totalItems ? (row.count / totalItems) * 100 : 0;
              return (
                <div key={row.quality_level}>
                  <div className="flex items-center justify-between text-2xs">
                    <span className="font-semibold uppercase tracking-label text-em-graphite">
                      {row.quality_level.replace('_', ' ').toLowerCase()}
                    </span>
                    <span className="tnum text-em-steel">{row.count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="mt-1 h-1.5 bg-em-panelDeep">
                    <div className="h-full bg-em-navy" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="mt-3 border-t border-em-line pt-3">
              <p className="tech-label">Knowledge by status</p>
              {(overview.knowledge_by_status || []).map((row) => (
                <p key={row.status} className="text-2xs text-em-steel">
                  {row.status}: <span className="tnum">{row.count}</span>
                </p>
              ))}
              {(overview.knowledge_by_status || []).length === 0 && <p className="text-2xs text-em-muted">No items yet.</p>}
            </div>
          </div>
        </div>

        <div className="panel lg:col-span-6">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <FlaskConical className="h-3.5 w-3.5 text-em-steel" />
              Knowledge base composition
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 p-3.5">
            {[
              { label: 'Verified maintenance cases in index', value: `${stats?.maintenance_cases_total ?? '—'}` },
              { label: 'Approved document passages', value: `${stats?.document_chunks_approved ?? '—'} of ${stats?.document_chunks_total ?? '—'}` },
              { label: 'Approved knowledge items', value: `${stats?.approved_knowledge_total ?? '—'} (${stats?.approved_knowledge_indexed ?? 0} indexed)` },
              { label: 'Embedding records', value: stats?.embedding_records },
              { label: 'Open conflicts', value: overview.open_conflicts },
              { label: 'Failures retained as evidence', value: overview.failed_attempts },
            ].map((row) => (
              <div key={row.label} className="border border-em-line p-2">
                <p className="tech-label">{row.label}</p>
                <p className="tnum mt-0.5 text-sm text-em-graphite">{row.value}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-em-line p-3.5">
            <p className="tech-label">Extraction quality across {confidenceJobs.length} jobs</p>
            <p className="mt-1 text-2xs text-em-steel">
              {meanConfidence != null
                ? `mean extraction confidence ${(meanConfidence * 100).toFixed(0)}%`
                : 'No extraction confidence recorded yet.'}
            </p>
            <p className="text-2xs text-em-steel">
              {unreadable.length} document(s) awaiting a human transcript · {failed.length} extraction failure(s)
            </p>
            <p className="mt-1 text-2xs text-em-muted">
              Extraction confidence is a heuristic quality score over measured signals (text coverage, character density,
              printable ratio, tables/figures). It is not a semantic accuracy claim.
            </p>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-em-warning" />
            Documents that could not be read locally
          </span>
          <span className="tech-value">{unreadable.length + failed.length}</span>
        </div>
        <ul className="divide-y divide-em-line">
          {[...unreadable, ...failed].map((job) => (
            <li key={job.job_id} className="flex flex-wrap items-center gap-2 px-3.5 py-2">
              <span className="font-mono text-2xs text-navy">{job.job_id}</span>
              <span className="min-w-0 flex-1 truncate text-2xs text-em-graphite">{job.filename}</span>
              <span className="chip-neutral">{job.detected_type}</span>
              <span className="chip-fault">{job.status.replace(/_/g, ' ').toLowerCase()}</span>
              <span className="font-mono text-2xs text-em-muted">{job.created_at}</span>
            </li>
          ))}
          {unreadable.length + failed.length === 0 && (
            <li className="p-4">
              <EmptyState title="No unreadable documents" detail="Every uploaded document produced extractable content." />
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
