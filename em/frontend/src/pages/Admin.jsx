import React, { useEffect, useRef, useState } from 'react';
import { Upload, Database, Users, AlertTriangle, CircleDot } from 'lucide-react';
import api from '../services/api';

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [operators, setOperators] = useState(null);
  const [operatorsError, setOperatorsError] = useState(null);
  const [file, setFile] = useState(null);
  const [docName, setDocName] = useState('');
  const [uploadStatus, setUploadStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const refresh = () => {
    api.get('/stats').then(setStats).catch(() => setStats(null));
    api
      .get('/auth/directory')
      .then((res) => setOperators(res.users || []))
      .catch(() => setOperatorsError('Operator directory requires administrator role.'));
  };

  useEffect(refresh, []);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setUploadStatus(null);
    try {
      const form = new FormData();
      form.append('file', file);
      if (docName) form.append('document_name', docName);
      form.append('document_type', 'service_manual');
      const res = await api.post('/documents/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUploadStatus({
        ok: true,
        text: `Indexed “${res.document_name}” into ${res.chunks_indexed} retrievable passages. Rebuild the retrieval index to include them in semantic search.`,
      });
      setFile(null);
      setDocName('');
      if (fileRef.current) fileRef.current.value = '';
      refresh();
    } catch (err) {
      setUploadStatus({
        ok: false,
        text: err?.detail || 'Ingestion failed. Check the document format and try again.',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Platform state — every value reported by the backend */}
        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Database className="h-3.5 w-3.5 text-em-steel" />
              Platform state
            </span>
          </div>
          <dl className="divide-y divide-em-line">
            {[
              ['Database engine', stats?.database?.engine],
              ['Machines on record', stats?.machines?.total?.toLocaleString()],
              ['Maintenance cases', stats?.cases?.total?.toLocaleString()],
              ['Registered technicians', stats?.technicians?.toLocaleString()],
              ['Indexed documents', stats?.documents?.toLocaleString()],
              ['Indexed passages', stats?.document_chunks?.toLocaleString()],
              ['Retrieval vectors', stats?.index?.vectors?.toLocaleString()],
              ['Embedding dimension', stats?.index?.dimension],
              ['Embedding model', stats?.index?.embedding_model],
              ['Reasoning model', stats?.reasoning_model],
            ].map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                <dt className="tech-label">{label}</dt>
                <dd className="tech-value tnum">{value ?? '—'}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t border-em-line px-3.5 py-2.5 text-2xs leading-relaxed text-em-muted">
            Retrieval vectors reflect the index currently on disk. Documents uploaded here must be indexed
            before they appear in semantic search.
          </p>
        </div>

        {/* Document ingestion */}
        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Upload className="h-3.5 w-3.5 text-em-steel" />
              Engineering document ingestion
            </span>
          </div>
          <form onSubmit={handleUpload} className="space-y-4 p-4">
            <div>
              <label htmlFor="docName" className="tech-label mb-1.5 block">
                Document title
              </label>
              <input
                id="docName"
                value={docName}
                onChange={(e) => setDocName(e.target.value)}
                placeholder="e.g. ZX210 Hydraulic System Service Manual"
                className="field"
              />
            </div>
            <div>
              <label htmlFor="docFile" className="tech-label mb-1.5 block">
                File
              </label>
              <input
                id="docFile"
                ref={fileRef}
                type="file"
                accept=".txt,.md,.csv,.pdf,.docx"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="field text-xs file:mr-3 file:border-0 file:bg-em-panel file:px-3 file:py-1.5 file:text-2xs file:font-semibold file:uppercase file:tracking-wider"
              />
              <p className="mt-1.5 text-2xs leading-relaxed text-em-muted">
                Text is extracted, split into overlapping passages with page and section metadata, then
                stored. Machine identifiers and component references are preserved where present.
              </p>
            </div>

            {uploadStatus && (
              <p
                className={`border-l-2 px-3 py-2 text-2xs leading-relaxed ${
                  uploadStatus.ok
                    ? 'border-em-success bg-em-successSoft text-em-success'
                    : 'border-em-fault bg-em-faultSoft text-em-fault'
                }`}
              >
                {uploadStatus.text}
              </p>
            )}

            <button type="submit" disabled={busy || !file} className="btn-amber">
              {busy ? 'Ingesting…' : 'Ingest document'}
            </button>
          </form>
        </div>
      </div>

      {/* Operators */}
      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <Users className="h-3.5 w-3.5 text-em-steel" />
            Registered operators
          </span>
          <span className="tech-value tnum">{operators ? operators.length : '—'}</span>
        </div>
        {operatorsError ? (
          <div className="flex items-start gap-2 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-warning" />
            <p className="text-xs text-em-graphite">{operatorsError}</p>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-em-panelDeep">
              <tr>
                {['Operator ID', 'Name', 'Email', 'Role', 'Created'].map((h) => (
                  <th key={h} className="tech-label px-3 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-em-line">
              {(operators || []).map((u) => (
                <tr key={u.user_id} className="hover:bg-em-paper">
                  <td className="px-3 py-2 font-mono text-em-steel">{u.username}</td>
                  <td className="px-3 py-2 text-em-graphite">{u.full_name}</td>
                  <td className="px-3 py-2 text-em-steel">{u.email}</td>
                  <td className="px-3 py-2">
                    <span className={u.role === 'ADMIN' ? 'chip-amber' : 'chip-neutral'}>{u.role}</span>
                  </td>
                  <td className="px-3 py-2 font-mono text-em-muted">{u.created_at}</td>
                </tr>
              ))}
              {operators && operators.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-em-muted">
                    No operators registered.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="flex items-center gap-1.5 border-t border-em-line px-3 py-2.5 text-2xs text-em-muted">
          <CircleDot className="h-3 w-3" />
          Password hashes are never returned by the API.
        </p>
      </div>
    </div>
  );
}
