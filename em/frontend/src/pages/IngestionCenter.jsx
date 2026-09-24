import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, FileUp, Layers, RefreshCw, ScanText, Table2 } from 'lucide-react';
import api from '../services/api';
import { ConfidenceMeter, EmptyState, Notice } from '../components/common/Evidence';

const STAGE_STYLES = {
  QUEUED: 'chip-neutral',
  EXTRACTING: 'chip-amber',
  REVIEW_REQUIRED: 'chip-amber',
  OCR_ENGINE_UNAVAILABLE: 'chip-fault',
  APPROVED: 'chip-navy',
  INDEXED: 'chip-success',
  REJECTED: 'chip-fault',
  EXTRACTION_FAILED: 'chip-fault',
};

function PipelineBar({ stages, active }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {stages.map((stage, index) => {
        const reached = active ? stages.indexOf(active) >= index : false;
        return (
          <React.Fragment key={stage}>
            <span
              className={`border px-2 py-1 text-2xs font-semibold uppercase tracking-label ${
                reached ? 'border-em-amber bg-em-amberSoft text-em-amberDark' : 'border-em-line text-em-muted'
              }`}
            >
              {stage.toLowerCase()}
            </span>
            {index < stages.length - 1 && <span className="text-em-line">›</span>}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export default function IngestionCenter() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [capabilities, setCapabilities] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [pipeline, setPipeline] = useState([]);
  const [form, setForm] = useState({ document_type: 'service_manual', revision: '1.0', source: 'field_upload', machine_model: 'All Models / Hydraulic Excavator' });
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [caps, jobsRes] = await Promise.all([api.get('/ingestion/capabilities'), api.get('/ingestion/jobs')]);
      setCapabilities(caps);
      setJobs(jobsRes.jobs || []);
      setPipeline(jobsRes.pipeline || []);
    } catch (err) {
      setError('Ingestion service is unreachable.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    setResult(null);
    setError(null);
    setProgress(0);
    try {
      const data = new FormData();
      data.append('file', file);
      data.append('document_type', form.document_type);
      data.append('revision', form.revision);
      data.append('source', form.source);
      data.append('machine_model', form.machine_model);
      const res = await api.post('/ingestion/upload', data, {
        timeout: 300000,
        onUploadProgress: (event) => {
          if (event.total) setProgress(Math.round((event.loaded / event.total) * 100));
        },
      });
      setResult(res);
      await load();
    } catch (err) {
      setError(err?.detail || 'The document could not be processed.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      {capabilities && (
        <Notice tone={capabilities.ocr_available ? 'info' : 'warning'} title="Local extraction capability">
          {capabilities.ocr_note} {capabilities.vision_note}
          <span className="mt-1 block text-em-muted">
            Supported formats: {capabilities.supported_types.join(', ')} · upload limit{' '}
            {(capabilities.max_upload_bytes / 1048576).toFixed(0)} MB · review threshold{' '}
            {(capabilities.review_threshold * 100).toFixed(0)}% ({capabilities.confidence_kind})
          </span>
        </Notice>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <FileUp className="h-3.5 w-3.5 text-em-steel" />
              Ingest an engineering document
            </span>
          </div>
          <div className="space-y-3 p-3.5">
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="tech-label">Document type</span>
                <select className="field mt-1" value={form.document_type} onChange={(e) => setForm({ ...form, document_type: e.target.value })}>
                  {['service_manual', 'service_bulletin', 'scanned_report', 'handwritten_note', 'inspection_report', 'field_procedure', 'parts_catalogue'].map((type) => (
                    <option key={type} value={type}>{type.replace('_', ' ')}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="tech-label">Revision</span>
                <input className="field mt-1" value={form.revision} onChange={(e) => setForm({ ...form, revision: e.target.value })} />
              </label>
            </div>
            <label className="block">
              <span className="tech-label">Source</span>
              <input className="field mt-1" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
            </label>
            <label className="block">
              <span className="tech-label">Machine model scope</span>
              <input className="field mt-1" value={form.machine_model} onChange={(e) => setForm({ ...form, machine_model: e.target.value })} />
            </label>

            <input ref={fileRef} type="file" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
            <button className="btn-amber w-full justify-center" onClick={() => fileRef.current?.click()} disabled={uploading}>
              <FileUp className="h-3.5 w-3.5" />
              {uploading ? `Processing ${progress}%` : 'Select file and run pipeline'}
            </button>
            {uploading && (
              <div className="h-1.5 w-full bg-em-panelDeep">
                <div className="h-full bg-em-amber" style={{ width: `${progress}%` }} />
              </div>
            )}
            {error && <Notice tone="fault" title="Ingestion failed">{error}</Notice>}
            <div>
              <span className="tech-label">Pipeline</span>
              <div className="mt-1.5">
                <PipelineBar stages={pipeline.length ? pipeline : ['UPLOAD', 'CLASSIFICATION', 'EXTRACTION', 'VALIDATION', 'CHUNKING', 'MYSQL']} active={uploading ? 'EXTRACTION' : result ? 'MYSQL' : 'UPLOAD'} />
              </div>
            </div>
          </div>
        </div>

        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <ScanText className="h-3.5 w-3.5 text-em-steel" />
              Latest extraction
            </span>
            {result && <span className="tech-value">{result.document_id}</span>}
          </div>
          <div className="p-3.5">
            {!result && <EmptyState title="Nothing processed in this session" detail="Upload a document to see detection, extraction, structure and confidence." />}
            {result && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip-navy">Document detected: {result.classification?.kind?.replace(/_/g, ' ')}</span>
                  <span className={`${STAGE_STYLES[result.status] || 'chip-neutral'}`}>status: {result.status.replace(/_/g, ' ').toLowerCase()}</span>
                  <span className="chip-neutral">method: {result.extraction_method}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-2xs md:grid-cols-4">
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Pages</span><span className="tnum text-sm text-em-graphite">{result.metrics?.page_count ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Pages with text</span><span className="tnum text-sm text-em-graphite">{result.metrics?.text_page_count ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Extracted characters</span><span className="tnum text-sm text-em-graphite">{result.metrics?.extracted_chars ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Passages created</span><span className="tnum text-sm text-em-graphite">{result.chunks_created ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Tables</span><span className="tnum text-sm text-em-graphite">{result.metrics?.table_count ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Figures</span><span className="tnum text-sm text-em-graphite">{result.metrics?.image_count ?? 0}</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Printable ratio</span><span className="tnum text-sm text-em-graphite">{((result.metrics?.printable_ratio ?? 0) * 100).toFixed(1)}%</span></span>
                  <span className="border border-em-line p-2"><span className="block text-em-muted">Passage kinds</span><span className="text-sm text-em-graphite">{Object.entries(result.chunk_kinds || {}).map(([k, v]) => `${k}:${v}`).join(' ')}</span></span>
                </div>

                <ConfidenceMeter
                  value={result.confidence?.extraction_confidence}
                  label="Extraction confidence (heuristic quality score)"
                  basis={(result.confidence?.confidence_basis || []).join(' · ')}
                />

                {(result.warnings || []).length > 0 && (
                  <Notice tone="warning" title="Extraction notes">
                    <ul className="list-disc space-y-0.5 pl-4">
                      {result.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </Notice>
                )}

                {(result.page_preview || []).length > 0 && (
                  <div>
                    <span className="tech-label">Extracted text (first pages)</span>
                    <div className="mt-1 max-h-48 space-y-1 overflow-y-auto">
                      {result.page_preview.map((page) => (
                        <div key={page.page_number} className="border border-em-line bg-em-surface p-2">
                          <p className="font-mono text-2xs text-em-muted">
                            page {page.page_number} · {page.chars} chars · {page.tables} table(s) · {page.figures} figure(s)
                          </p>
                          <p className="mt-0.5 whitespace-pre-wrap text-2xs text-em-steel">{page.excerpt || '— no text extracted —'}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button className="btn-dark" onClick={() => navigate('/review')}>
                    <Layers className="h-3.5 w-3.5" />
                    Open review queue
                  </button>
                  <button className="btn-outline" onClick={() => navigate('/evidence')}>
                    View stored documents
                  </button>
                </div>
                <p className="text-2xs text-em-muted">{result.message}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <Table2 className="h-3.5 w-3.5 text-em-steel" />
            Ingestion jobs
          </span>
          <button className="btn-ghost" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-2xs">
            <thead>
              <tr className="border-b border-em-line text-left">
                {['job', 'file', 'detected', 'pages', 'chars', 'tables', 'figures', 'confidence', 'chunks', 'vectors', 'status', 'stage'].map((header) => (
                  <th key={header} className="px-3 py-2 font-semibold uppercase tracking-label text-em-muted">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id} className="border-b border-em-lineSoft">
                  <td className="px-3 py-2 font-mono text-navy">{job.job_id}</td>
                  <td className="max-w-[220px] truncate px-3 py-2">{job.filename}</td>
                  <td className="px-3 py-2">{job.detected_type || '—'}</td>
                  <td className="px-3 py-2 tnum">{job.page_count}<span className="text-em-muted">/{job.text_page_count}</span></td>
                  <td className="px-3 py-2 tnum">{job.extracted_chars}</td>
                  <td className="px-3 py-2 tnum">{job.table_count}</td>
                  <td className="px-3 py-2 tnum">{job.image_count}</td>
                  <td className="px-3 py-2 tnum">{job.extraction_confidence ? `${(job.extraction_confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td className="px-3 py-2 tnum">{job.chunk_count}</td>
                  <td className="px-3 py-2 tnum">{job.vector_count}</td>
                  <td className="px-3 py-2"><span className={STAGE_STYLES[job.status] || 'chip-neutral'}>{job.status.replace(/_/g, ' ').toLowerCase()}</span></td>
                  <td className="px-3 py-2">{job.pipeline_stage}</td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={12} className="p-4">
                    <EmptyState title="No ingestion jobs yet" detail="Every upload is recorded here with what the pipeline actually measured." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center gap-2 border-t border-em-line p-3">
          <AlertTriangle className="h-3.5 w-3.5 text-em-warning" />
          <p className="text-2xs text-em-muted">
            Counts, confidence and status are read from the ingestion_jobs and document_extractions tables — nothing on this
            page is estimated.
          </p>
        </div>
      </div>
    </div>
  );
}
