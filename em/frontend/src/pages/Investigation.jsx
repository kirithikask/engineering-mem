import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardList,
  Clock,
  FileText,
  Gauge,
  History,
  Microscope,
  Plus,
  ShieldAlert,
  Sparkles,
  Truck,
  Wrench,
  XCircle,
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import MachineScene from '../components/3d/MachineScene';
import { ConfidenceMeter, DemoChip, EmptyState, Notice, QualityChip, StatusChip, SupersededChip } from '../components/common/Evidence';
import { formatHours, orNotRecorded } from '../utils/format';

// Local reasoning on CPU takes minutes; the client ceiling sits above the server's.
const DIAGNOSE_TIMEOUT_MS = 360000;

const FINDING_KINDS = [
  { value: 'measurement', label: 'Measurement' },
  { value: 'inspection', label: 'Inspection' },
  { value: 'observation', label: 'Observation' },
  { value: 'note', label: 'Note' },
];

const RULINGS = [
  { value: 'PENDING', label: 'Pending' },
  { value: 'FOUND', label: 'Found — supports a cause' },
  { value: 'RULED_OUT', label: 'Ruled out' },
  { value: 'INCONCLUSIVE', label: 'Inconclusive' },
];

const RULING_STYLE = {
  FOUND: 'chip-fault',
  RULED_OUT: 'chip-success',
  PENDING: 'chip-amber',
  INCONCLUSIVE: 'chip-neutral',
};

function SectionHead({ icon: Icon, title, right, hint }) {
  return (
    <div className="panel-head">
      <span className="tech-label flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-em-steel" />}
        {title}
      </span>
      {right}
      {hint && <span className="tech-value">{hint}</span>}
    </div>
  );
}

function KeyValue({ label, value, mono = false }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-em-lineSoft py-1.5 last:border-b-0">
      <span className="tech-label">{label}</span>
      <span className={`text-xs text-em-graphite ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

function EvidenceCard({ item }) {
  const isChunk = item.evidence_type === 'chunk';
  return (
    <div className="border border-em-line bg-em-surface p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-2xs font-bold text-em-graphite">{item.id}</span>
        <QualityChip level={item.quality_level} compact />
        {isChunk ? <StatusChip status={item.document_status} revision={item.revision} /> : null}
        <SupersededChip show={item.superseded} />
        <DemoChip show={item.demo_data} />
        <span className="ml-auto font-mono text-2xs text-em-muted tnum">
          sim {Number(item.similarity || 0).toFixed(3)} · eff {Number(item.effective_score || 0).toFixed(3)}
        </span>
      </div>
      <p className="mt-1.5 text-2xs font-semibold text-em-graphite">
        {isChunk ? `${item.document_name} — p${item.page_number} · ${item.section_heading || 'no section'}` : item.title}
      </p>
      {isChunk ? (
        <p className="mt-1 whitespace-pre-wrap text-2xs leading-relaxed text-em-steel">
          {(item.chunk_text || '').slice(0, 420)}
          {(item.chunk_text || '').length > 420 ? '…' : ''}
        </p>
      ) : (
        <div className="mt-1 space-y-0.5 text-2xs leading-relaxed text-em-steel">
          {item.component ? <p><span className="text-em-muted">Component:</span> {item.component}</p> : null}
          {item.failure_mode ? <p><span className="text-em-muted">Failure mode:</span> {item.failure_mode}</p> : null}
          {item.inspection ? <p><span className="text-em-muted">Recorded finding:</span> {item.inspection}</p> : null}
          {item.repair ? <p><span className="text-em-muted">Repair:</span> {item.repair}</p> : null}
        </div>
      )}
      {item.superseded_note ? <p className="mt-1 text-2xs text-em-fault">{item.superseded_note}</p> : null}
    </div>
  );
}

export default function Investigation() {
  const { investigationId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('evidence');
  const [busy, setBusy] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [diagnosisError, setDiagnosisError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [safety, setSafety] = useState(null);
  const [draft, setDraft] = useState(null);
  const [flash, setFlash] = useState(null);
  const [similar, setSimilar] = useState(null);
  const fileRef = useRef(null);

  const [finding, setFinding] = useState({
    kind: 'measurement',
    title: '',
    value: '',
    unit: '',
    component: '',
    detail: '',
    ruling: 'PENDING',
  });
  const [repair, setRepair] = useState({ action_taken: '', component: '', result: 'PERSISTED', note: '' });
  const [checks, setChecks] = useState([
    { label: 'Primary symptom no longer present', passed: false },
    { label: 'Performance normal under load', passed: false },
    { label: 'No abnormal noise or temperature', passed: false },
  ]);
  const [verifyNotes, setVerifyNotes] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/investigations/${investigationId}`);
      setState(res);
      setError(null);
      return res;
    } catch (err) {
      setError('Investigation could not be loaded.');
      return null;
    }
  }, [investigationId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .get(`/investigations/${investigationId}/safety`)
      .then(setSafety)
      .catch(() => setSafety(null));
  }, [investigationId]);

  useEffect(() => {
    if (busy !== 'diagnose') return undefined;
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 500);
    return () => clearInterval(timer);
  }, [busy]);

  const investigation = state?.investigation;
  const machine = state?.machine;
  const situation = state?.situation;
  const attempts = state?.attempts || [];
  const findings = state?.findings || [];
  const events = state?.events || [];
  const photos = state?.photos || [];

  const snapshotEvidence = situation?.latest_re_evaluation?.top_evidence || [];
  const nextChecks = situation?.what_should_be_checked_next || [];

  const machineComponentId = useMemo(() => {
    const map = {
      'hydraulic pump': 'comp_pump',
      'hydraulic filter': 'comp_filter',
      'hydraulic oil': 'comp_oil',
      'main control valve': 'comp_valve',
      'oil cooler': 'comp_cooler',
      'boom cylinder': 'comp_lift_cyl',
      'arm cylinder': 'comp_lift_cyl',
      'bucket cylinder': 'comp_tilt_cyl',
      'pilot system': 'comp_valve',
    };
    const component = (diagnosis?.affected_component || findings.find((f) => f.component)?.component || '').toLowerCase();
    return map[component] || null;
  }, [diagnosis, findings]);

  const runDiagnose = async () => {
    setBusy('diagnose');
    setDiagnosisError(null);
    setElapsed(0);
    try {
      const res = await api.post(`/investigations/${investigationId}/diagnose`, {}, { timeout: DIAGNOSE_TIMEOUT_MS });
      setDiagnosis(res);
      if (res.safety) setSafety(res.safety);
      await load();
    } catch (err) {
      setDiagnosisError(
        err?.detail ||
          'The investigation could not be re-evaluated. The recorded evidence is unchanged and no diagnosis was asserted.'
      );
    } finally {
      setBusy(null);
    }
  };

  const submitFinding = async (event) => {
    event.preventDefault();
    if (!finding.title.trim()) return;
    setBusy('finding');
    try {
      const res = await api.post(`/investigations/${investigationId}/findings`, finding);
      setFlash(
        `Finding recorded. Evidence re-evaluated: ${res?.re_evaluation?.evidence_sufficiency || 'not available'} ` +
          `(${res?.re_evaluation?.timings?.latency_ms ?? 0} ms).`
      );
      setFinding({ kind: 'measurement', title: '', value: '', unit: '', component: '', detail: '', ruling: 'PENDING' });
      await load();
    } catch (err) {
      setFlash(err?.detail || 'The finding could not be saved.');
    } finally {
      setBusy(null);
    }
  };

  const submitRepair = async (event) => {
    event.preventDefault();
    if (!repair.action_taken.trim()) return;
    setBusy('repair');
    try {
      const res = await api.post(`/investigations/${investigationId}/repair`, repair);
      setSimilar(res.historical_attempts);
      setFlash(res.was_successful ? 'Repair recorded as successful.' : 'Failed attempt recorded as engineering evidence.');
      setRepair({ action_taken: '', component: '', result: 'PERSISTED', note: '' });
      await load();
    } catch (err) {
      setFlash(err?.detail || 'The repair attempt could not be saved.');
    } finally {
      setBusy(null);
    }
  };

  const submitVerification = async () => {
    setBusy('verify');
    try {
      const res = await api.post(`/investigations/${investigationId}/verify`, {
        checks,
        notes: verifyNotes,
        root_cause: diagnosis?.likely_causes?.[0]?.cause || investigation?.root_cause,
      });
      setFlash(res.passed ? 'Verification passed.' : 'Verification recorded with failures — investigation stays open.');
      await load();
    } catch (err) {
      setFlash(err?.detail || 'Verification could not be saved.');
    } finally {
      setBusy(null);
    }
  };

  const createKnowledge = async () => {
    setBusy('knowledge');
    try {
      const res = await api.post(`/investigations/${investigationId}/create-knowledge`, {
        title: `${machine?.machine_id || investigation?.machine_id} — ${diagnosis?.likely_causes?.[0]?.cause || investigation?.root_cause || 'investigation'}`,
      });
      setDraft(res);
      setFlash('Case draft generated. It becomes knowledge only after expert review.');
      await load();
    } catch (err) {
      setFlash(err?.detail || 'The case draft could not be generated.');
    } finally {
      setBusy(null);
    }
  };

  const uploadPhoto = async (file) => {
    if (!file) return;
    setBusy('photo');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post(`/investigations/${investigationId}/photos`, form, { timeout: 120000 });
      setFlash(
        res.requires_manual_selection
          ? res.identification_basis
          : `Photo linked. Suggested component: ${res.detected_component} (${res.visual_match}). ${res.identification_basis}`
      );
      await load();
    } catch (err) {
      setFlash(err?.detail || 'The photo could not be uploaded.');
    } finally {
      setBusy(null);
    }
  };

  if (error) {
    return (
      <Notice tone="fault" title="Investigation unavailable">
        {error} <Link className="text-em-amberDark underline" to="/investigations">Back to investigations</Link>
      </Notice>
    );
  }
  if (!investigation) {
    return <p className="text-xs text-em-steel">Loading investigation…</p>;
  }

  return (
    <div className="space-y-4">
      {/* Machine + investigation identity strip */}
      <div className="panel">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <Truck className="h-5 w-5 text-em-amber" />
            <div>
              <p className="font-mono text-sm font-bold text-em-graphite">{machine?.machine_id || investigation.machine_id}</p>
              <p className="tech-value">
                {orNotRecorded(machine?.machine_model)} · {formatHours(machine?.operating_hours)} h · {orNotRecorded(machine?.status)}
              </p>
            </div>
          </div>
          <div className="border-l border-em-line pl-6">
            <p className="font-mono text-sm font-bold text-em-navy">{investigation.investigation_id}</p>
            <p className="tech-value">
              {investigation.status} · severity {investigation.severity} · opened by {investigation.opened_by_name || 'unknown'}
            </p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span className="chip-neutral">{findings.length} findings</span>
            <span className={`chip-${attempts.some((a) => !a.was_successful) ? 'fault' : 'neutral'}`}>
              {attempts.filter((a) => !a.was_successful).length} failed attempts
            </span>
            {situation?.what_we_know?.evidence_sufficiency && (
              <span className={`chip-${situation.what_we_know.evidence_sufficiency === 'sufficient' ? 'success' : situation.what_we_know.evidence_sufficiency === 'partial' ? 'amber' : 'fault'}`}>
                evidence {situation.what_we_know.evidence_sufficiency}
              </span>
            )}
            <button className="btn-amber" onClick={runDiagnose} disabled={busy === 'diagnose'}>
              <Sparkles className="h-3.5 w-3.5" />
              {busy === 'diagnose' ? `Re-evaluating… ${elapsed.toFixed(0)}s` : 'Re-evaluate evidence'}
            </button>
          </div>
        </div>
      </div>

      {flash && (
        <Notice tone="info" title="Last action">
          {flash}
        </Notice>
      )}
      {diagnosisError && (
        <Notice tone="fault" title="Reasoning unavailable">
          {diagnosisError}
        </Notice>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* LEFT — machine identity */}
        <div className="space-y-4 xl:col-span-3">
          <div className="panel">
            <SectionHead icon={Truck} title="Machine identity" right={<span className="tech-value">reference assembly</span>} />
            <MachineScene
              machineLabel={machine?.machine_model || 'Reference assembly'}
              highlightedComponentId={machineComponentId}
              machineState={investigation.status === 'CLOSED' || investigation.status === 'VERIFIED' ? 'verified' : 'faulted'}
              className="h-56 w-full"
              autoRotate
            />
            <div className="p-3">
              <KeyValue label="Subsystem" value={orNotRecorded(investigation.subsystem)} />
              <KeyValue label="Last maintenance" value={orNotRecorded(machine?.last_maintenance)} />
              <KeyValue label="Manufacturer" value={orNotRecorded(machine?.manufacturer)} />
              <Link to={`/machines/${investigation.machine_id}/passport`} className="btn-outline mt-3 w-full justify-center">
                <ClipboardList className="h-3.5 w-3.5" />
                Machine passport
              </Link>
            </div>
          </div>

          <div className="panel">
            <SectionHead icon={AlertTriangle} title="What we know" />
            <div className="space-y-2 p-3">
              <p className="text-xs font-semibold text-em-graphite">{investigation.problem_statement}</p>
              <div className="flex flex-wrap gap-1.5">
                {(investigation.symptoms || []).map((symptom) => (
                  <span key={symptom} className="chip-neutral">{symptom}</span>
                ))}
              </div>
              {(diagnosis?.similar_machine_inference_note || !diagnosis) && (
                <p className="text-2xs leading-relaxed text-em-muted">
                  {diagnosis?.similar_machine_inference_note ||
                    'Retrieval uses this machine’s own history when it exists, and clearly labelled similar-machine history when it does not.'}
                </p>
              )}
            </div>
          </div>

          <div className="panel">
            <SectionHead icon={ShieldAlert} title="Safety before the next step" />
            <div className="space-y-2 p-3">
              {safety?.approved_procedures?.length > 0 && (
                <div>
                  <p className="tech-label">Approved procedures in the knowledge base</p>
                  {safety.approved_procedures.map((procedure) => (
                    <div key={procedure.procedure_id} className="mt-1 border border-em-line p-2">
                      <p className="text-2xs font-semibold text-em-graphite">{procedure.title}</p>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-2xs text-em-steel">
                        {(procedure.steps || []).map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
              {safety?.document_excerpts?.length > 0 && (
                <div>
                  <p className="tech-label">Excerpts from approved documents</p>
                  {safety.document_excerpts.slice(0, 2).map((row) => (
                    <p key={row.chunk_id} className="mt-1 border-l-2 border-l-em-line pl-2 text-2xs leading-relaxed text-em-steel">
                      {row.chunk_text.slice(0, 240)}…
                      <span className="mt-0.5 block text-em-muted">
                        Source: {row.document_name} p{row.page_number} · rev {row.revision || 'n/a'}
                      </span>
                    </p>
                  ))}
                </div>
              )}
              <div>
                <p className="tech-label">Standing advisory</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-2xs text-em-steel">
                  {(safety?.standing_advisory || []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p className="mt-1 text-2xs text-em-muted">{safety?.standing_advisory_source}</p>
              </div>
            </div>
          </div>
        </div>

        {/* CENTER — the investigation itself */}
        <div className="space-y-4 xl:col-span-6">
          <div className="panel">
            <SectionHead icon={Microscope} title="Next best inspection" right={<span className="tech-value">ranked by retrieved evidence</span>} />
            <div className="divide-y divide-em-line">
              {nextChecks.length === 0 && (
                <div className="p-3">
                  <EmptyState
                    title="No re-evaluation recorded yet"
                    detail="Record a finding or run a re-evaluation. The recommendation is derived from the retrieved evidence, never from a generic checklist."
                  />
                </div>
              )}
              {nextChecks.slice(0, 5).map((check, index) => (
                <div key={check.id || check.key} className="p-3">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center bg-em-navy font-mono text-2xs font-bold text-white">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-em-graphite">{check.title || check.inspection}</p>
                      <p className="mt-0.5 text-2xs leading-relaxed text-em-steel">{check.why}</p>
                      {check.expected && (
                        <p className="mt-1 text-2xs text-em-steel">
                          <span className="text-em-muted">Expected finding:</span> {check.expected}
                        </p>
                      )}
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="chip-neutral">{check.origin === 'recorded_historical_inspection' ? 'from historical record' : 'workstation inspection catalogue'}</span>
                        {check.already_checked && <span className="chip-amber">already checked — ranked lower</span>}
                        {check.failed_attempt_overlap?.length > 0 && <span className="chip-fault">previous attempt did not resolve</span>}
                        {check.historical_cases?.length > 0 && (
                          <span className="chip-navy">{check.historical_cases.slice(0, 3).join(', ')}</span>
                        )}
                        <span className="ml-auto font-mono text-2xs text-em-muted tnum">rank {Number(check.rank_score || 0).toFixed(3)}</span>
                      </div>
                      {(check.supporting_evidence || []).length > 0 && (
                        <div className="mt-1.5 space-y-1">
                          {check.supporting_evidence.slice(0, 2).map((source) => (
                            <p key={`${source.id}-${source.page_number}`} className="border-l-2 border-l-em-amberSoft pl-2 text-2xs text-em-muted">
                              {source.id} · {source.title} {source.page_number ? `p${source.page_number}` : ''} · sim{' '}
                              {Number(source.similarity || 0).toFixed(3)}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <SectionHead
              icon={ClipboardList}
              title="Investigation"
              right={<span className="tech-value">{findings.length} recorded</span>}
            />
            <div className="divide-y divide-em-line">
              {findings.length === 0 && (
                <div className="p-3">
                  <EmptyState title="Nothing checked yet" detail="Record the first measurement or inspection below." />
                </div>
              )}
              {findings.map((row) => (
                <div key={row.finding_id} className="flex items-start gap-2 px-3 py-2">
                  {row.ruling === 'RULED_OUT' ? (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-success" />
                  ) : row.ruling === 'FOUND' ? (
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-fault" />
                  ) : (
                    <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-amber" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-em-graphite">
                      <span className="font-semibold">{row.title}</span>
                      {row.value ? <span className="tnum"> — {row.value} {row.unit || ''}</span> : null}
                    </p>
                    {row.detail && <p className="text-2xs text-em-steel">{row.detail}</p>}
                    <p className="text-2xs text-em-muted">
                      {row.kind} · {row.component || 'component not stated'} · {row.created_by_name || 'unknown'} · {row.created_at}
                    </p>
                  </div>
                  <span className={RULING_STYLE[row.ruling] || 'chip-neutral'}>{row.ruling.replace('_', ' ').toLowerCase()}</span>
                </div>
              ))}
            </div>
            <form className="grid grid-cols-1 gap-2 border-t border-em-line p-3 sm:grid-cols-6" onSubmit={submitFinding}>
              <select className="field sm:col-span-1" value={finding.kind} onChange={(e) => setFinding({ ...finding, kind: e.target.value })}>
                {FINDING_KINDS.map((kind) => (
                  <option key={kind.value} value={kind.value}>{kind.label}</option>
                ))}
              </select>
              <input
                className="field sm:col-span-2"
                placeholder="What was checked (e.g. Hydraulic oil temperature)"
                value={finding.title}
                onChange={(e) => setFinding({ ...finding, title: e.target.value })}
              />
              <input className="field sm:col-span-1" placeholder="Value" value={finding.value} onChange={(e) => setFinding({ ...finding, value: e.target.value })} />
              <input className="field sm:col-span-1" placeholder="Unit" value={finding.unit} onChange={(e) => setFinding({ ...finding, unit: e.target.value })} />
              <select className="field sm:col-span-1" value={finding.ruling} onChange={(e) => setFinding({ ...finding, ruling: e.target.value })}>
                {RULINGS.map((ruling) => (
                  <option key={ruling.value} value={ruling.value}>{ruling.label}</option>
                ))}
              </select>
              <input
                className="field sm:col-span-3"
                placeholder="Component (optional — inferred from the text when left blank)"
                value={finding.component}
                onChange={(e) => setFinding({ ...finding, component: e.target.value })}
              />
              <input
                className="field sm:col-span-3"
                placeholder="Detail / conditions (e.g. after 25 minutes of sustained digging)"
                value={finding.detail}
                onChange={(e) => setFinding({ ...finding, detail: e.target.value })}
              />
              <button className="btn-dark sm:col-span-6" type="submit" disabled={busy === 'finding'}>
                <Plus className="h-3.5 w-3.5" />
                {busy === 'finding' ? 'Recording and re-evaluating…' : 'Record finding and re-evaluate evidence'}
              </button>
            </form>
          </div>

          <div className="panel">
            <SectionHead icon={Camera} title="Photo evidence" right={<span className="tech-value">{photos.length} stored</span>} />
            <div className="space-y-2 p-3">
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => uploadPhoto(e.target.files?.[0])}
                />
                <button className="btn-outline" onClick={() => fileRef.current?.click()} disabled={busy === 'photo'}>
                  <Camera className="h-3.5 w-3.5" />
                  {busy === 'photo' ? 'Analysing…' : 'Upload photo'}
                </button>
                <p className="text-2xs leading-relaxed text-em-muted">
                  Photos are stored as investigation evidence and measured locally (focus, exposure, contrast). No
                  vision model is configured, so no automatic visual diagnosis is produced — you confirm the component.
                </p>
              </div>
              {photos.map((photo) => (
                <div key={photo.photo_id} className="border border-em-line p-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-2xs font-bold text-em-graphite">{photo.photo_id}</span>
                    <span className="chip-neutral">{photo.original_filename}</span>
                    <span className={`chip-${photo.visual_match === 'MANUALLY_CONFIRMED' ? 'success' : photo.visual_match === 'UNDETERMINED' ? 'fault' : 'amber'}`}>
                      visual match: {String(photo.visual_match || 'undetermined').toLowerCase()}
                    </span>
                    <span className="chip-navy">{photo.component_confirmed || photo.component_suggested || 'component not set'}</span>
                  </div>
                  {photo.caption && <p className="mt-1 text-2xs text-em-steel">{photo.caption}</p>}
                </div>
              ))}
              {photos.length === 0 && <p className="text-2xs text-em-muted">No photo evidence attached.</p>}
            </div>
          </div>

          <div className="panel">
            <SectionHead icon={Wrench} title="Repair attempts" hint="failures are retained as evidence" />
            <div className="divide-y divide-em-line">
              {attempts.length === 0 && (
                <div className="p-3">
                  <EmptyState title="No repair attempted" detail="Recorded attempts — successful or not — become part of the engineering memory." />
                </div>
              )}
              {attempts.map((attempt) => (
                <div key={attempt.attempt_id} className="flex items-start gap-2 px-3 py-2">
                  {attempt.was_successful ? (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-em-success" />
                  ) : (
                    <XCircle className="mt-0.5 h-3.5 w-3.5 text-em-fault" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-em-graphite">{attempt.action_taken}</p>
                    <p className="text-2xs text-em-muted">
                      {attempt.component || 'component not stated'} · result {attempt.result} · {attempt.created_by_name || 'unknown'} · {attempt.created_at}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <form className="grid grid-cols-1 gap-2 border-t border-em-line p-3 sm:grid-cols-4" onSubmit={submitRepair}>
              <input
                className="field sm:col-span-2"
                placeholder="Action taken (e.g. Filter element replaced)"
                value={repair.action_taken}
                onChange={(e) => setRepair({ ...repair, action_taken: e.target.value })}
              />
              <input className="field" placeholder="Component" value={repair.component} onChange={(e) => setRepair({ ...repair, component: e.target.value })} />
              <select className="field" value={repair.result} onChange={(e) => setRepair({ ...repair, result: e.target.value })}>
                <option value="PERSISTED">Problem persisted</option>
                <option value="RESOLVED">Problem resolved</option>
                <option value="PARTIAL">Partially improved</option>
                <option value="UNKNOWN">Outcome unknown</option>
              </select>
              <input
                className="field sm:col-span-4"
                placeholder="Note (optional)"
                value={repair.note}
                onChange={(e) => setRepair({ ...repair, note: e.target.value })}
              />
              <button className="btn-dark sm:col-span-4" type="submit" disabled={busy === 'repair'}>
                Record repair attempt
              </button>
            </form>
            {similar?.failed_attempts?.length > 0 && (
              <div className="border-t border-em-line p-3">
                <Notice tone="warning" title="Previous attempts for similar cases">
                  <ul className="space-y-0.5">
                    {similar.failed_attempts.map((item) => (
                      <li key={item.attempt_id}>✗ {item.label}</li>
                    ))}
                    {similar.successful_attempts.map((item) => (
                      <li key={item.attempt_id}>✓ {item.label}</li>
                    ))}
                  </ul>
                  <p className="mt-1 text-em-muted">{similar.warning}</p>
                </Notice>
              </div>
            )}
          </div>

          <div className="panel">
            <SectionHead icon={Gauge} title="Repair verification" hint={investigation.verification?.passed ? 'passed' : 'not verified'} />
            <div className="space-y-2 p-3">
              {checks.map((check, index) => (
                <label key={check.label} className="flex items-center gap-2 text-xs text-em-graphite">
                  <input
                    type="checkbox"
                    checked={check.passed}
                    onChange={(e) => {
                      const next = [...checks];
                      next[index] = { ...check, passed: e.target.checked };
                      setChecks(next);
                    }}
                  />
                  {check.label}
                </label>
              ))}
              <input className="field" placeholder="Verification notes" value={verifyNotes} onChange={(e) => setVerifyNotes(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                <button className="btn-dark" onClick={submitVerification} disabled={busy === 'verify'}>
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Record verification
                </button>
                <button className="btn-amber" onClick={createKnowledge} disabled={busy === 'knowledge'}>
                  <FileText className="h-3.5 w-3.5" />
                  {busy === 'knowledge' ? 'Generating…' : 'Create engineering memory'}
                </button>
                {investigation.knowledge_id && (
                  <span className="chip-success">case {investigation.knowledge_id}</span>
                )}
              </div>
              {draft && (
                <div className="border border-em-line bg-em-paper p-3">
                  <p className="text-2xs font-bold uppercase tracking-label text-em-graphite">
                    Case draft {draft.knowledge_id} · {draft.knowledge_status} · {draft.quality_level}
                  </p>
                  <pre className="mt-1 whitespace-pre-wrap text-2xs leading-relaxed text-em-steel">{draft.content}</pre>
                  <button className="btn-outline mt-2" onClick={() => navigate('/review')}>
                    Submit for expert review
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT — evidence */}
        <div className="space-y-4 xl:col-span-3">
          <div className="panel">
            <div className="panel-head">
              <div className="flex w-full items-center gap-1">
                {[
                  { key: 'evidence', label: 'Evidence' },
                  { key: 'cases', label: 'Similar cases' },
                  { key: 'manual', label: 'Manual' },
                  { key: 'photos', label: 'Photos' },
                ].map((item) => (
                  <button
                    key={item.key}
                    onClick={() => setTab(item.key)}
                    className={`px-2 py-1 text-2xs font-semibold uppercase tracking-label ${
                      tab === item.key ? 'text-em-navy' : 'text-em-muted hover:text-em-graphite'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[560px] space-y-2 overflow-y-auto p-3">
              {tab === 'evidence' &&
                (diagnosis?.supporting_evidence?.length
                  ? diagnosis.supporting_evidence.map((item) => <EvidenceCard key={item.vector_id} item={item} />)
                  : snapshotEvidence.length
                    ? snapshotEvidence.map((item) => (
                        <div key={item.id} className="border border-em-line p-2.5">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-2xs font-bold text-em-graphite">{item.id}</span>
                            <QualityChip level={item.quality_level} compact />
                            <span className="ml-auto font-mono text-2xs text-em-muted tnum">
                              eff {Number(item.effective_score || 0).toFixed(3)}
                            </span>
                          </div>
                          <p className="mt-1 text-2xs text-em-steel">{item.title || item.component}</p>
                        </div>
                      ))
                    : <EmptyState title="No evidence retrieved yet" detail="Run a re-evaluation to retrieve engineering evidence for this investigation." />)}

              {tab === 'cases' &&
                (diagnosis?.previous_failed_attempts?.length || diagnosis?.previous_successful_resolutions?.length ? (
                  <>
                    <p className="tech-label">Previous attempts for similar cases</p>
                    {(diagnosis.previous_failed_attempts || []).map((item) => (
                      <p key={item.attempt_id} className="text-2xs text-em-fault">✗ {item.action_taken} — unsuccessful</p>
                    ))}
                    {(diagnosis.previous_successful_resolutions || []).map((item) => (
                      <p key={item.attempt_id} className="text-2xs text-em-success">✓ {item.action_taken} — successful</p>
                    ))}
                  </>
                ) : (
                  <EmptyState
                    title="No comparable attempts recorded"
                    detail="Historical attempts appear here once similar cases exist in the engineering memory."
                  />
                ))}

              {tab === 'manual' &&
                ((diagnosis?.supporting_evidence || []).filter((item) => item.evidence_type === 'chunk').length ? (
                  (diagnosis?.supporting_evidence || [])
                    .filter((item) => item.evidence_type === 'chunk')
                    .map((item) => <EvidenceCard key={item.vector_id} item={item} />)
                ) : (
                  <EmptyState title="No manual passage retrieved" detail="Approved documents appear here after retrieval." />
                ))}

              {tab === 'photos' &&
                (photos.length ? (
                  photos.map((photo) => (
                    <div key={photo.photo_id} className="border border-em-line p-2.5">
                      <p className="font-mono text-2xs font-bold text-em-graphite">{photo.photo_id}</p>
                      <p className="text-2xs text-em-steel">{photo.component_confirmed || photo.component_suggested || 'component not set'}</p>
                      {photo.image_analysis_json && (
                        <pre className="mt-1 whitespace-pre-wrap text-2xs text-em-muted">{photo.image_analysis_json}</pre>
                      )}
                    </div>
                  ))
                ) : (
                  <EmptyState title="No photo evidence" detail="Upload a component photograph above." />
                ))}
            </div>
          </div>

          {diagnosis && (
            <div className="panel">
              <SectionHead icon={Sparkles} title="Reasoning" hint={diagnosis.reasoning_status} />
              <div className="space-y-2 p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={`chip-${diagnosis.evidence_sufficiency === 'sufficient' ? 'success' : diagnosis.evidence_sufficiency === 'partial' ? 'amber' : 'fault'}`}>
                    evidence {diagnosis.evidence_sufficiency}
                  </span>
                  <span className="chip-navy">confidence {diagnosis.confidence}</span>
                  {diagnosis.exact_machine_history === false && <span className="chip-amber">similar machines only</span>}
                </div>
                {diagnosis.sufficiency_reason && <p className="text-2xs text-em-steel">{diagnosis.sufficiency_reason}</p>}
                {(diagnosis.likely_causes || []).map((cause) => (
                  <div key={cause.cause} className="border border-em-line p-2">
                    <p className="text-2xs font-semibold text-em-graphite">{cause.cause}</p>
                    <p className="text-2xs text-em-muted">{cause.component} · confidence {Number(cause.confidence || 0).toFixed(2)}</p>
                    {cause.reason && <p className="mt-1 text-2xs leading-relaxed text-em-steel">{cause.reason}</p>}
                    {(cause.evidence || []).length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {cause.evidence.map((source) => (
                          <span key={source.id} className="chip-neutral">{source.id}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {diagnosis.reasoning && <p className="text-2xs leading-relaxed text-em-steel">{diagnosis.reasoning}</p>}
                {(diagnosis.what_to_collect_next || []).length > 0 && (
                  <div>
                    <p className="tech-label">Still missing</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-2xs text-em-steel">
                      {diagnosis.what_to_collect_next.slice(0, 5).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {(diagnosis.unverified_citations || []).length > 0 && (
                  <p className="text-2xs text-em-fault">
                    Dropped unsupported citations: {diagnosis.unverified_citations.join(', ')}
                  </p>
                )}
                {(diagnosis.conflicting_evidence || []).length > 0 && (
                  <div className="border border-em-line border-l-2 border-l-em-warning bg-em-amberSoft/40 p-2">
                    <p className="text-2xs font-bold uppercase tracking-label text-em-warning">
                      Conflicting engineering information
                    </p>
                    {diagnosis.conflicting_evidence.slice(0, 3).map((conflict) => (
                      <div key={`${conflict.topic}-${conflict.values.join('-')}`} className="mt-1 text-2xs text-em-steel">
                        <p className="font-semibold">{conflict.topic} ({conflict.unit})</p>
                        {conflict.sources.map((source) => (
                          <p key={`${source.id}-${source.value}`}>
                            {source.id} · {source.title} · {source.document_status}: {source.value} {source.unit}
                          </p>
                        ))}
                        <p className="text-em-muted">Current approved source priority: {conflict.priority_source?.id}</p>
                      </div>
                    ))}
                  </div>
                )}
                {diagnosis.timings && (
                  <p className="font-mono text-2xs text-em-muted">
                    retrieval {diagnosis.timings.latency_ms ?? diagnosis.timings.faiss_ms ?? 0} ms · llm{' '}
                    {diagnosis.timings.llm_ms ?? 0} ms · total {diagnosis.timings.total_ms ?? 0} ms
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* BOTTOM — timeline */}
      <div className="panel">
        <SectionHead icon={History} title="Investigation timeline" right={<span className="tech-value">{events.length} events</span>} />
        <ol className="divide-y divide-em-line">
          {events.length === 0 && (
            <li className="p-3">
              <EmptyState title="No events recorded" detail="Every action in this investigation is written to the timeline." />
            </li>
          )}
          {events.map((event) => (
            <li key={event.event_id} className="flex items-start gap-3 px-3 py-2">
              <span className="w-32 shrink-0 font-mono text-2xs text-em-muted">{event.created_at}</span>
              <span className="w-40 shrink-0 text-2xs font-semibold uppercase tracking-label text-em-steel">
                {event.event_type.replace(/_/g, ' ').toLowerCase()}
              </span>
              <span className="min-w-0 flex-1 text-2xs leading-relaxed text-em-graphite">{event.summary}</span>
              <span className="w-32 shrink-0 text-right text-2xs text-em-muted">{event.actor_name || 'system'}</span>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-2 border-t border-em-line p-3">
          <Activity className="h-3.5 w-3.5 text-em-steel" />
          <span className="text-2xs text-em-muted">
            Timeline rows are read from the investigation_events table; nothing is reconstructed on the client.
          </span>
          <button className="btn-outline ml-auto" onClick={load}>
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}
