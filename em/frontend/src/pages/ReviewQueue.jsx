import React, { useCallback, useEffect, useState } from 'react';
import { Check, FileSignature, FileWarning, Pencil, ShieldCheck, X } from 'lucide-react';
import api from '../services/api';
import { ConfidenceMeter, DemoChip, EmptyState, Notice, QualityChip } from '../components/common/Evidence';

export default function ReviewQueue() {
  const [queue, setQueue] = useState([]);
  const [ocrAvailable, setOcrAvailable] = useState(false);
  const [extractions, setExtractions] = useState({});
  const [selected, setSelected] = useState(null);
  const [knowledge, setKnowledge] = useState({ pending_review: [], drafts: [], recent_reviews: [] });
  const [edits, setEdits] = useState({});
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const [docs, items, versions] = await Promise.all([
        api.get('/ingestion/queue'),
        api.get('/knowledge/review-queue'),
        api.get('/documents').catch(() => ({ documents: [] })),
      ]);
      setQueue(docs.queue || []);
      setOcrAvailable(Boolean(docs.ocr_available));
      setKnowledge(items);
      return versions;
    } catch (err) {
      setMessage({ tone: 'fault', text: 'The review queue could not be loaded. Engineer or administrator role is required.' });
      return null;
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDocument = async (documentId) => {
    setSelected(documentId);
    if (extractions[documentId]) return;
    try {
      const res = await api.get(`/documents/${documentId}/extractions`);
      setExtractions((prev) => ({ ...prev, [documentId]: res.extractions || [] }));
    } catch (err) {
      setExtractions((prev) => ({ ...prev, [documentId]: [] }));
    }
  };

  const saveTranscript = async (extractionId, text) => {
    setBusy(extractionId);
    try {
      await api.put(`/ingestion/extractions/${extractionId}`, { raw_text: text, extraction_confidence: 0.6 });
      setMessage({ tone: 'info', text: 'Transcript saved. Rebuild the passages, then approve the document to index it.' });
      if (selected) {
        const res = await api.get(`/documents/${selected}/extractions`);
        setExtractions((prev) => ({ ...prev, [selected]: res.extractions || [] }));
      }
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'The transcript could not be saved.' });
    } finally {
      setBusy(null);
    }
  };

  const rebuild = async (documentId) => {
    setBusy(documentId);
    try {
      const res = await api.post(`/ingestion/documents/${documentId}/rebuild-chunks`, {});
      setMessage({ tone: 'info', text: `Passages rebuilt from the corrected text: ${res.chunks_created}.` });
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'Passages could not be rebuilt.' });
    } finally {
      setBusy(null);
    }
  };

  const decideDocument = async (documentId, decision) => {
    setBusy(documentId);
    try {
      const res =
        decision === 'approve'
          ? await api.post(`/documents/${documentId}/approve`, {})
          : await api.post(`/documents/${documentId}/reject`, { comment: 'Rejected in review queue' });
      setMessage({ tone: decision === 'approve' ? 'success' : 'warning', text: res.message || 'Decision recorded.' });
      await load();
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'The decision could not be recorded.' });
    } finally {
      setBusy(null);
    }
  };

  const reviewKnowledge = async (knowledgeId, action) => {
    setBusy(knowledgeId);
    try {
      const res = await api.post(`/knowledge/${knowledgeId}/review`, {
        action,
        quality_level: action === 'APPROVE' ? 'VERIFIED' : undefined,
        comment: action === 'APPROVE' ? 'Reviewed in the review queue' : 'Rejected in review queue',
        edits: edits[knowledgeId] || undefined,
      });
      setMessage({ tone: 'success', text: res.message });
      setEdits((prev) => ({ ...prev, [knowledgeId]: {} }));
      await load();
    } catch (err) {
      setMessage({ tone: 'fault', text: err?.detail || 'The review could not be recorded.' });
    } finally {
      setBusy(null);
    }
  };

  const editField = (knowledgeId, field, value) =>
    setEdits((prev) => ({ ...prev, [knowledgeId]: { ...(prev[knowledgeId] || {}), [field]: value } }));

  const pendingKnowledge = [...(knowledge.pending_review || []), ...(knowledge.drafts || [])];

  return (
    <div className="space-y-5">
      {message && <Notice tone={message.tone} title="Review">{message.text}</Notice>}

      {!ocrAvailable && (
        <Notice tone="warning" title="No local OCR engine on this host">
          Scanned and handwritten documents are stored and queued here. Type the transcription into the page record below —
          the system does not guess text it could not read. Installing Tesseract locally enables automatic OCR; nothing is
          sent to an external service either way.
        </Notice>
      )}

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <FileWarning className="h-3.5 w-3.5 text-em-steel" />
            Document extractions awaiting a decision
          </span>
          <span className="tech-value">{queue.length} item(s)</span>
        </div>
        <ul className="divide-y divide-em-line">
          {queue.map((item) => (
            <li key={`${item.document_id}-${item.version_id}`} className="px-3.5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-xs font-semibold text-em-graphite">{item.document_name}</span>
                <span className="chip-neutral">{item.document_type}</span>
                {item.revision && <span className="chip-navy">rev {item.revision}</span>}
                <span className={`chip-${item.status === 'OCR_ENGINE_UNAVAILABLE' ? 'fault' : 'amber'}`}>{item.status.replace(/_/g, ' ').toLowerCase()}</span>
                <span className="font-mono text-2xs text-em-muted">{item.chunk_count} passages · {item.page_count} pages</span>
                <button className="btn-outline" onClick={() => openDocument(item.document_id)}>
                  <Pencil className="h-3 w-3" />
                  Inspect / edit
                </button>
                <button className="btn-dark" onClick={() => decideDocument(item.document_id, 'approve')} disabled={busy === item.document_id}>
                  <Check className="h-3 w-3" />
                  Approve &amp; index
                </button>
                <button className="btn-ghost" onClick={() => decideDocument(item.document_id, 'reject')} disabled={busy === item.document_id}>
                  <X className="h-3 w-3" />
                  Reject
                </button>
              </div>

              <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                <ConfidenceMeter value={item.extraction_confidence} label="Extraction confidence" basis={item.note?.slice(0, 200)} />
                <div className="text-2xs text-em-steel">
                  <p><span className="text-em-muted">Method:</span> {item.extraction_method}</p>
                  <p><span className="text-em-muted">Uploaded:</span> {item.created_at}</p>
                  <p className="text-em-muted">
                    Approving sets this revision CURRENT, supersedes older revisions of the same document, embeds the
                    passages with BGE and adds them to the FAISS index.
                  </p>
                </div>
              </div>

              {selected === item.document_id && (
                <div className="mt-2 space-y-2 border border-em-line bg-em-paper p-2.5">
                  {(extractions[item.document_id] || []).length === 0 && (
                    <EmptyState title="No page records" detail="This document produced no extraction rows." />
                  )}
                  {(extractions[item.document_id] || []).map((page) => (
                    <div key={page.extraction_id} className="border border-em-line bg-em-surface p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-2xs text-em-graphite">page {page.page_number}</span>
                        <span className="chip-neutral">{page.extraction_method}</span>
                        <span className="chip-neutral">{page.review_status}</span>
                        <span className="font-mono text-2xs text-em-muted tnum">confidence {(page.extraction_confidence * 100).toFixed(0)}%</span>
                      </div>
                      {(page.structure?.tables || []).length > 0 && (
                        <p className="mt-1 text-2xs text-em-steel">{page.structure.tables.length} table(s) preserved with headers</p>
                      )}
                      {(page.structure?.images || []).length > 0 && (
                        <p className="text-2xs text-em-steel">{page.structure.images.length} figure(s) linked to this page and its text</p>
                      )}
                      <textarea
                        className="field mt-1 h-28 font-mono text-2xs"
                        defaultValue={page.raw_text}
                        onBlur={(e) => {
                          if (e.target.value !== page.raw_text) saveTranscript(page.extraction_id, e.target.value);
                        }}
                        placeholder="Type the transcribed text for this page (used when no local OCR engine is available)"
                      />
                    </div>
                  ))}
                  <button className="btn-outline" onClick={() => rebuild(item.document_id)} disabled={busy === item.document_id}>
                    Rebuild passages from the corrected text
                  </button>
                </div>
              )}
            </li>
          ))}
          {queue.length === 0 && (
            <li className="p-4">
              <EmptyState title="Nothing awaiting review" detail="Uploads land here until an engineer approves them for indexing." />
            </li>
          )}
        </ul>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <FileSignature className="h-3.5 w-3.5 text-em-steel" />
            Knowledge submitted by technicians
          </span>
          <span className="tech-value">{pendingKnowledge.length} item(s)</span>
        </div>
        <ul className="divide-y divide-em-line">
          {pendingKnowledge.map((item) => (
            <li key={item.knowledge_id} className="px-3.5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-2xs font-bold text-em-navy">{item.knowledge_id}</span>
                <span className="min-w-0 flex-1 truncate text-xs font-semibold text-em-graphite">{item.title}</span>
                <QualityChip level={item.quality_level} compact />
                <span className="chip-neutral">{item.status}</span>
                <DemoChip show={String(item.source_type || '').includes('demo')} />
                {item.investigation_id && (
                  <a className="chip-navy" href={`/investigations/${item.investigation_id}`}>{item.investigation_id}</a>
                )}
              </div>

              <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                <div>
                  <p className="text-2xs text-em-steel"><span className="text-em-muted">Machine:</span> {item.machine_id} · {item.machine_model || 'model not recorded'}</p>
                  <p className="text-2xs text-em-steel"><span className="text-em-muted">Component:</span> {item.component} · {item.failure_mode}</p>
                  <p className="text-2xs text-em-steel"><span className="text-em-muted">Root cause:</span> {item.root_cause}</p>
                  <p className="text-2xs text-em-steel"><span className="text-em-muted">Repair:</span> {item.repair_action}</p>
                  <p className="text-2xs text-em-muted">Submitted by {item.created_by_name || 'unknown'} · {item.created_at}</p>
                </div>
                <div className="space-y-1.5">
                  <p className="tech-label">Edit before approving (engineer correction)</p>
                  <input className="field" placeholder={item.root_cause || 'Root cause'} onChange={(e) => editField(item.knowledge_id, 'root_cause', e.target.value)} />
                  <input className="field" placeholder={item.repair_action || 'Repair action'} onChange={(e) => editField(item.knowledge_id, 'repair_action', e.target.value)} />
                  <div className="flex gap-2">
                    <button className="btn-amber" onClick={() => reviewKnowledge(item.knowledge_id, 'APPROVE')} disabled={busy === item.knowledge_id}>
                      <ShieldCheck className="h-3 w-3" />
                      Approve as verified knowledge
                    </button>
                    <button className="btn-ghost" onClick={() => reviewKnowledge(item.knowledge_id, 'REJECT')} disabled={busy === item.knowledge_id}>
                      <X className="h-3 w-3" />
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            </li>
          ))}
          {pendingKnowledge.length === 0 && (
            <li className="p-4">
              <EmptyState
                title="No knowledge awaiting review"
                detail="Case drafts are created from completed investigations and appear here for expert approval."
              />
            </li>
          )}
        </ul>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label">Recent review decisions</span>
        </div>
        <ul className="divide-y divide-em-line">
          {(knowledge.recent_reviews || []).map((row) => (
            <li key={`${row.knowledge_id}-${row.created_at}`} className="flex flex-wrap items-center gap-2 px-3.5 py-2">
              <span className="font-mono text-2xs text-em-navy">{row.knowledge_id}</span>
              <span className="chip-neutral">{row.action}</span>
              <span className="text-2xs text-em-steel">{row.reviewer_name} ({row.reviewer_role})</span>
              <span className="text-2xs text-em-muted">{row.comment}</span>
              <span className="ml-auto font-mono text-2xs text-em-muted">{row.created_at}</span>
            </li>
          ))}
          {(knowledge.recent_reviews || []).length === 0 && (
            <li className="p-3 text-2xs text-em-muted">No review decisions recorded yet.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
