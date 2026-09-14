import React, { useEffect, useState } from 'react';
import { FileText, ChevronRight, AlertTriangle } from 'lucide-react';
import api from '../services/api';

export default function EvidenceDocuments() {
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get('/documents')
      .then((res) => {
        const docs = res.documents || [];
        setDocuments(docs);
        if (docs.length) selectDocument(docs[0].document_id);
      })
      .catch(() => setError('Document store unavailable.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectDocument = async (id) => {
    setSelectedId(id);
    try {
      const res = await api.get(`/documents/${id}`);
      setDetail(res);
    } catch (err) {
      setDetail(null);
    }
  };

  return (
    <div className="space-y-5">
      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-fault" />
            <p className="text-xs text-em-graphite">{error}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-4">
          <div className="panel-head">
            <span className="tech-label">Indexed documents</span>
            <span className="tech-value tnum">{documents.length}</span>
          </div>
          <ul className="divide-y divide-em-line">
            {documents.map((d) => (
              <li key={d.document_id}>
                <button
                  onClick={() => selectDocument(d.document_id)}
                  className={`flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left transition-colors ${
                    selectedId === d.document_id ? 'bg-em-amberSoft/40' : 'hover:bg-em-paper'
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold text-em-graphite">
                      {d.document_name}
                    </span>
                    <span className="tech-value mt-0.5 block">
                      {d.chunk_count} passages · {d.document_type}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-em-muted" />
                </button>
              </li>
            ))}
            {documents.length === 0 && !error && (
              <li className="p-4 text-xs text-em-muted">No documents indexed.</li>
            )}
          </ul>
        </div>

        <div className="panel lg:col-span-8">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-em-steel" />
              {detail?.document?.document_name || 'Document passages'}
            </span>
            <span className="tech-value tnum">{detail?.chunks?.length || 0} passages</span>
          </div>

          <ul className="max-h-[34rem] divide-y divide-em-line overflow-y-auto">
            {(detail?.chunks || []).map((chk) => (
              <li key={chk.chunk_id} className="p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-2xs text-em-muted">{chk.chunk_id}</span>
                  <span className="tech-value">
                    Page {chk.page_number} · {chk.section_heading}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-em-graphite">{chk.chunk_text}</p>
                {chk.component && (
                  <p className="tech-value mt-1.5 block">Referenced component: {chk.component}</p>
                )}
              </li>
            ))}
            {detail && (detail.chunks || []).length === 0 && (
              <li className="p-4 text-xs text-em-muted">This document has no indexed passages.</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
