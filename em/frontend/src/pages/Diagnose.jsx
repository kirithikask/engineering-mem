import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Wrench,
  Plus,
  X,
  AlertTriangle,
  ShieldAlert,
  Database,
  FileText,
  Activity,
  Crosshair,
  CheckCircle2,
  FlaskConical,
  Clock,
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import MachineScene from '../components/3d/MachineScene';
import { formatHours, orNotRecorded } from '../utils/format';

// The local model is bounded server-side (OLLAMA_TIMEOUT); keep the client ceiling above it.
const REASON_TIMEOUT_MS = 360000;

const PRESET_SYMPTOMS = [
  'Slow boom movement',
  'Weak digging force',
  'Performance worsens when hot',
  'High hydraulic oil temperature',
  'Jerky cylinder movement',
  'Slow control response across all levers',
  'Arm drifts down when parked',
  'Filter warning indicator active',
];

// Component ids returned by the diagnosis engine map to the same ids the 3D
// twin uses, so the machine can be focused with no client-side translation.
const COMPONENT_LABELS = {
  comp_pump: 'Hydraulic Pump',
  comp_cooler: 'Hydraulic Cooler',
  comp_filter: 'Hydraulic Filter',
  comp_valve: 'Main Control Valve',
  comp_accumulator: 'Accumulator',
  comp_boom: 'Boom Cylinder',
  comp_arm: 'Arm Cylinder',
  comp_bucket: 'Bucket Cylinder',
  comp_pilot: 'Pilot System',
  comp_swing: 'Swing Motor',
  comp_travel: 'Travel Motor',
  comp_lines: 'Hydraulic Line',
  comp_oil: 'Hydraulic Oil',
};

const SUFFICIENCY_STYLE = {
  sufficient: { label: 'Sufficient', cls: 'chip-success' },
  partial: { label: 'Partial', cls: 'chip-amber' },
  insufficient: { label: 'Insufficient evidence', cls: 'chip-fault' },
};

function StageRow({ state, label, detail }) {
  // state: 'done' | 'active' | 'pending'
  const dot =
    state === 'done'
      ? 'border-em-success bg-em-success text-white'
      : state === 'active'
        ? 'border-em-amber bg-em-amberSoft'
        : 'border-em-line';
  return (
    <li className="flex items-start gap-2">
      <span className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center border ${dot}`}>
        {state === 'done' && <CheckCircle2 className="h-2.5 w-2.5" />}
        {state === 'active' && <span className="h-1.5 w-1.5 animate-pulseRing rounded-full bg-em-amber" />}
      </span>
      <span className="min-w-0">
        <span
          className={`block text-2xs font-semibold uppercase tracking-wider ${
            state === 'pending' ? 'text-em-muted' : state === 'active' ? 'text-em-graphite' : 'text-em-steel'
          }`}
        >
          {label}
        </span>
        {detail && <span className="block text-2xs text-em-muted">{detail}</span>}
      </span>
    </li>
  );
}

function ProvenanceTag({ source }) {
  if (source === 'verified_field_diagnosis') {
    return <span className="chip-success">Technician verified</span>;
  }
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

export default function Diagnose() {
  const { user } = useAuth();
  const isEngineer = user?.role === 'ENGINEER' || user?.role === 'ADMIN';

  const [machines, setMachines] = useState([]);
  const [machineId, setMachineId] = useState('');
  const [symptoms, setSymptoms] = useState(['Slow boom movement', 'Weak digging force', 'Performance worsens when hot']);
  const [draft, setDraft] = useState('');
  const [oilTemp, setOilTemp] = useState('92');
  const [pressure, setPressure] = useState('180');

  const [phase, setPhase] = useState('idle'); // idle | retrieving | retrieved | reasoning | done | evidence_only
  const [retrieval, setRetrieval] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);

  const [selectedComponent, setSelectedComponent] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [finding, setFinding] = useState('');
  const [repair, setRepair] = useState('');
  const [confirmMsg, setConfirmMsg] = useState(null);
  const startedAt = useRef(0);

  useEffect(() => {
    api
      .get('/machines')
      .then((res) => {
        const list = res.machines || [];
        setMachines(list);
        if (list.length && !machineId) setMachineId(list[0].machine_id);
      })
      .catch(() => setError('Engineering database unavailable. Machines could not be loaded.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Real elapsed time while the local model reasons.
  useEffect(() => {
    if (phase !== 'reasoning') return undefined;
    const timer = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 250);
    return () => clearInterval(timer);
  }, [phase]);

  const machine = useMemo(
    () => machines.find((m) => m.machine_id === machineId) || null,
    [machines, machineId]
  );

  const addSymptom = (value) => {
    const text = (value || '').trim();
    if (!text || symptoms.includes(text)) return;
    setSymptoms((s) => [...s, text]);
    setDraft('');
  };

  const runDiagnosis = async () => {
    if (!machineId || symptoms.length === 0) return;
    setError(null);
    setDiagnosis(null);
    setRetrieval(null);
    setSelectedComponent(null);
    setPhase('retrieving');

    const payload = {
      machine_id: machineId,
      symptoms,
      observations: {
        oil_temperature: parseFloat(oilTemp) || null,
        pressure_bar: parseFloat(pressure) || null,
      },
      sensor_telemetry: {
        oil_temperature: parseFloat(oilTemp) || null,
        pressure_bar: parseFloat(pressure) || null,
      },
    };

    let bundle;
    try {
      // Stage 1 — retrieval. Returns in tens of milliseconds and is displayed
      // immediately, so evidence is on screen before the model has finished.
      bundle = await api.post('/diagnose/retrieve', payload);
      setRetrieval(bundle);
      setPhase('reasoning');
      startedAt.current = Date.now();
      setElapsed(0);
    } catch (err) {
      setPhase('idle');
      setError(
        err?.detail || 'Engineering memory retrieval unavailable. Confirm the backend services are running.'
      );
      return;
    }

    try {
      // Stage 2 — local reasoning over the retrieved evidence. Runs as a
      // background job: /reason/start returns instantly, then short polls
      // collect the result. No single HTTP request carries a generation in
      // flight, so proxies with idle limits (Cloudflare ~100 s) can never
      // kill a slow CPU inference through the public link.
      const start = await api.post('/diagnose/reason/start', {
        retrieval_id: bundle.retrieval_id,
      });
      const jobId = start.job_id;
      const deadline = Date.now() + REASON_TIMEOUT_MS;
      for (;;) {
        if (Date.now() > deadline) throw new Error('reasoning deadline exceeded');
        await new Promise((resolve) => setTimeout(resolve, 2000));
        let poll;
        try {
          poll = await api.get(`/diagnose/reason/status/${jobId}`, { timeout: 15000 });
        } catch (pollErr) {
          continue; // transient poll failure — keep waiting within the deadline
        }
        if (poll.status === 'running') continue;
        if (poll.status === 'failed') throw new Error(poll.detail || 'reasoning failed');
        setDiagnosis(poll);
        setPhase('done');
        return;
      }
    } catch (err) {
      // Evidence is already displayed; report the reasoning outage plainly.
      setPhase('evidence_only');
    }
  };

  const submitVerification = async () => {
    if (!finding.trim() || !repair.trim() || !diagnosis) return;
    try {
      const res = await api.post('/diagnose/confirm', {
        diagnosis_id: diagnosis.diagnosis_id,
        machine_id: machineId,
        component: diagnosis.affected_component,
        failure_mode: diagnosis.likely_causes?.[0]?.cause || 'Verified failure',
        symptoms: symptoms.join('; '),
        actual_finding: finding,
        repair_performed: repair,
        outcome: 'Verified repair restored hydraulic operation',
      });
      setConfirmMsg(res.message);
      setTimeout(() => {
        setShowConfirm(false);
        setConfirmMsg(null);
        setFinding('');
        setRepair('');
      }, 2200);
    } catch (err) {
      setConfirmMsg('Verification could not be recorded. Engineering database unavailable.');
    }
  };

  const sufficient = SUFFICIENCY_STYLE[diagnosis?.evidence_sufficiency || retrieval?.evidence_sufficiency] ||
    SUFFICIENCY_STYLE.insufficient;

  const retrievalDone = Boolean(retrieval);
  const leadingCase = retrieval?.historical_evidence?.[0] || null;
  // Only a completed diagnosis drives the 3D focus; retrieved cases do not
  // auto-highlight a component that the model has not yet concluded on.
  const focusComponent = diagnosis?.component_id || null;
  const bestCause = diagnosis?.likely_causes?.[0] || null;
  const showResults = Boolean(diagnosis) || phase === 'evidence_only';

  return (
    <div className="space-y-5">
      {/* ==================== MACHINE + SYMPTOM INPUT ==================== */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="xl:col-span-7 space-y-4">
          <div className="panel">
            <div className="panel-head">
              <span className="tech-label">Machine under diagnosis</span>
              <span className="tech-value">{machines.length.toLocaleString()} on record</span>
            </div>
            <div className="p-4">
              <select
                value={machineId}
                onChange={(e) => setMachineId(e.target.value)}
                className="field font-mono text-xs"
              >
                {machines.length === 0 && <option value="">No machines available</option>}
                {machines.map((m) => (
                  <option key={m.machine_id} value={m.machine_id}>
                    {m.machine_id} · {m.machine_model} · {m.machine_type}
                  </option>
                ))}
              </select>
              {machine && (
                <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-em-line pt-3 sm:grid-cols-4">
                  <div>
                    <dt className="tech-label">Model</dt>
                    <dd className="tech-value mt-0.5">{machine.machine_model}</dd>
                  </div>
                  <div>
                    <dt className="tech-label">Manufacturer</dt>
                    <dd className="tech-value mt-0.5">{orNotRecorded(machine.manufacturer)}</dd>
                  </div>
                  <div>
                    <dt className="tech-label">Operating hours</dt>
                    <dd className="tech-value tnum mt-0.5">{formatHours(machine.operating_hours)}</dd>
                  </div>
                  <div>
                    <dt className="tech-label">Status</dt>
                    <dd className="tech-value mt-0.5">{machine.status}</dd>
                  </div>
                </dl>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="tech-label">Reported symptoms</span>
              <span className="tech-value tnum">{symptoms.length} recorded</span>
            </div>
            <div className="p-4 space-y-3">
              {symptoms.length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {symptoms.map((s) => (
                    <li
                      key={s}
                      className="flex items-center gap-1.5 border border-em-line bg-em-paper px-2.5 py-1 text-xs text-em-graphite"
                    >
                      {s}
                      <button
                        onClick={() => setSymptoms((list) => list.filter((x) => x !== s))}
                        className="text-em-muted hover:text-em-fault"
                        aria-label={`Remove ${s}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex gap-2">
                <input
                  type="text"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addSymptom(draft);
                    }
                  }}
                  placeholder="Describe an observed symptom, e.g. arm movement slow after oil warms"
                  className="field flex-1"
                />
                <button onClick={() => addSymptom(draft)} className="btn-outline px-3">
                  <Plus className="h-3.5 w-3.5" />
                  Add
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 border-t border-em-line pt-3">
                <span className="tech-label mr-1">Common</span>
                {PRESET_SYMPTOMS.filter((p) => !symptoms.includes(p)).slice(0, 6).map((p) => (
                  <button
                    key={p}
                    onClick={() => addSymptom(p)}
                    className="border border-em-line px-2 py-0.5 text-2xs text-em-steel transition-colors hover:border-em-steel hover:text-em-graphite"
                  >
                    + {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="tech-label">Measured observations (optional)</span>
              <span className="tech-value">Feeds condition analysis</span>
            </div>
            <div className="grid grid-cols-2 gap-4 p-4">
              <div>
                <label htmlFor="oilTemp" className="tech-label mb-1.5 block">
                  Hydraulic oil temperature (°C)
                </label>
                <input
                  id="oilTemp"
                  type="number"
                  value={oilTemp}
                  onChange={(e) => setOilTemp(e.target.value)}
                  className="field font-mono text-xs"
                />
              </div>
              <div>
                <label htmlFor="pressure" className="tech-label mb-1.5 block">
                  Main line pressure (bar)
                </label>
                <input
                  id="pressure"
                  type="number"
                  value={pressure}
                  onChange={(e) => setPressure(e.target.value)}
                  className="field font-mono text-xs"
                />
              </div>
            </div>
          </div>

          <button
            onClick={runDiagnosis}
            disabled={phase === 'retrieving' || phase === 'reasoning' || symptoms.length === 0 || !machineId}
            className="btn-amber w-full py-3"
          >
            <Wrench className="h-4 w-4" />
            Run diagnosis
          </button>
        </div>

        {/* 3D machine — large, always present, focused once a component is identified */}
        <div className="xl:col-span-5">
          <div className="overflow-hidden border border-em-navy/15">
            <div className="flex items-center justify-between border-b border-em-navy/20 bg-em-navyTint px-4 py-2">
              <span className="font-mono text-2xs font-bold uppercase tracking-[0.18em] text-em-navy">
                {machine ? `${machine.machine_id} · ${machine.machine_model}` : 'No machine selected'}
              </span>
              <span className="tech-value">
                {focusComponent ? 'Diagnosis focus' : selectedComponent ? 'Manual selection' : 'Interactive'}
              </span>
            </div>
            <MachineScene
              highlightedComponentId={focusComponent}
              selectedComponentId={selectedComponent}
              onSelectComponent={(id) => setSelectedComponent(id)}
              machineState={
                phase === 'retrieving' || phase === 'reasoning' ? 'scanning'
                : focusComponent ? 'faulted'
                : 'normal'
              }
              className="h-[480px] w-full"
            />
            {selectedComponent && (
              <div className="border-t border-em-navy/15 bg-em-navyTint/40 p-3">
                <span className="tech-label text-em-navy">Component inspection point</span>
                <p className="mt-1 text-xs text-em-graphite">
                  {COMPONENT_LABELS[selectedComponent] || selectedComponent}
                  <span className="ml-2 text-em-steel">
                    — cross-reference its recorded history before disassembly.
                  </span>
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ==================== ANALYSIS PROGRESS (real states) ==================== */}
      {(phase === 'retrieving' || phase === 'reasoning' || phase === 'evidence_only') && (
        <div className="panel">
          <div className={`panel-head ${phase === 'reasoning' ? 'scan-track' : ''}`}>
            <span className="tech-label">
              {phase === 'retrieving' ? 'Retrieving engineering evidence' : 'Evaluating diagnosis'}
            </span>
            {phase === 'reasoning' && (
              <span className="tech-value tnum flex items-center gap-1.5">
                <Clock className="h-3 w-3" />
                {elapsed.toFixed(0)}s
              </span>
            )}
          </div>
          <ul className="grid grid-cols-1 gap-2.5 p-4 sm:grid-cols-2 lg:grid-cols-3">
            <StageRow
              state={retrievalDone ? 'done' : phase === 'retrieving' ? 'active' : 'pending'}
              label="Symptoms parsed"
              detail={retrieval ? `${retrieval.symptoms_analyzed?.length ?? 0} structured` : undefined}
            />
            <StageRow
              state={retrievalDone ? 'done' : 'pending'}
              label="Engineering memory searched"
              detail={
                retrieval?.timings?.embedding_ms != null
                  ? `Embedding ${retrieval.timings.embedding_ms} ms · index ${retrieval.timings.faiss_retrieval_ms} ms`
                  : undefined
              }
            />
            <StageRow
              state={retrievalDone ? 'done' : 'pending'}
              label="Evidence retrieved"
              detail={
                retrieval
                  ? `${retrieval.historical_evidence?.length || 0} cases · ${retrieval.document_evidence?.length || 0} manual passages`
                  : undefined
              }
            />
            <StageRow
              state={phase === 'reasoning' ? 'active' : diagnosis ? 'done' : 'pending'}
              label="Evaluating against evidence"
              detail={phase === 'reasoning' ? 'Local Qwen 3:4B (offline)' : undefined}
            />
            <StageRow
              state={diagnosis ? 'done' : 'pending'}
              label="Building recommendation"
            />
          </ul>

          {phase === 'reasoning' && leadingCase && (
            <div className="border-t border-em-line bg-em-paper px-4 py-3">
              <span className="tech-label">Retrieved evidence — awaiting model evaluation</span>
              <p className="mt-1 text-xs leading-relaxed text-em-steel">
                Closest recorded case <span className="font-mono text-em-graphite">{leadingCase.case_id}</span> ·{' '}
                {leadingCase.component} / {leadingCase.failure_mode}. The model has not yet confirmed a
                conclusion.
              </p>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-fault" />
            <div>
              <span className="tech-label text-em-fault">Diagnosis unavailable</span>
              <p className="mt-1 text-xs text-em-graphite">{error}</p>
            </div>
          </div>
        </div>
      )}

      {phase === 'evidence_only' && (
        <div className="panel border-l-2 border-l-em-warning p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-warning" />
            <div>
              <span className="tech-label text-em-warning">AI reasoning service unavailable</span>
              <p className="mt-1 text-xs leading-relaxed text-em-graphite">
                Evidence retrieval completed. The retrieved historical cases, manual passages and condition
                evidence are shown below — review them against the approved service procedure. No diagnosis
                has been generated.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ==================== LEVEL 1 — FINAL DECISION ==================== */}
      {diagnosis && (
        <>
          <section className="panel border-t-2 border-t-em-amber">
            <div className="flex flex-col gap-3 border-b border-em-line bg-em-panelDeep px-4 py-3 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-3">
                <span className="tech-label">Final diagnosis</span>
                <span className={sufficient.cls}>{sufficient.label}</span>
                {diagnosis.reasoning_status === 'ai_engine_unavailable' && (
                  <span className="chip-fault">Model unavailable</span>
                )}
              </div>
              <span className="tech-value">
                {machineId} · {machine?.machine_model}
              </span>
            </div>

            <div className="p-5">
              {diagnosis.evidence_sufficiency === 'insufficient' ? (
                <div>
                  <h2 className="text-xl font-bold tracking-tight text-em-graphite">
                    Insufficient evidence for a supported diagnosis
                  </h2>
                  <p className="mt-2 max-w-3xl text-xs leading-relaxed text-em-steel">
                    The retrieved engineering memory does not support a confident conclusion for these
                    symptoms. No cause has been fabricated. Perform the inspections below and record the
                    findings.
                  </p>
                </div>
              ) : (
                <>
                  <span className="tech-label">Likely cause</span>
                  <h2 className="mt-1 text-2xl font-bold leading-tight tracking-tight text-em-graphite">
                    {bestCause?.cause || 'No supported cause'}
                  </h2>
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <span className="text-sm text-em-steel">
                      Affected component:{' '}
                      <span className="font-semibold text-em-graphite">
                        {diagnosis.affected_component}
                      </span>
                    </span>
                    {diagnosis.confidence_score != null && (
                      <span className="chip-neutral">
                        Model confidence {(diagnosis.confidence_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </>
              )}

              {/* Decision-critical fields, in the order the technician needs them */}
              <div className="mt-5 grid grid-cols-1 gap-5 border-t border-em-line pt-5 lg:grid-cols-3">
                <div>
                  <span className="tech-label">Recommended inspection</span>
                  <ol className="mt-2 space-y-2">
                    {(diagnosis.recommended_inspection || []).map((step, i) => (
                      <li key={step} className="flex items-start gap-2 text-xs leading-relaxed text-em-graphite">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center bg-em-graphite font-mono text-2xs font-bold text-em-amber">
                          {i + 1}
                        </span>
                        {step}
                      </li>
                    ))}
                    {!diagnosis.recommended_inspection?.length && (
                      <li className="text-xs text-em-muted">No inspection steps returned.</li>
                    )}
                  </ol>
                </div>

                <div>
                  <span className="tech-label">Previous successful resolution</span>
                  <p className="mt-2 text-xs leading-relaxed text-em-graphite">
                    {diagnosis.previous_successful_resolution || 'No prior verified resolution recorded.'}
                  </p>
                </div>

                <div>
                  <span className="tech-label">Safety requirements</span>
                  <ul className="mt-2 space-y-1.5">
                    {(diagnosis.safety_notes || []).map((note) => (
                      <li key={note} className="flex items-start gap-1.5 text-2xs leading-relaxed text-em-steel">
                        <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0 text-em-warning" />
                        {note}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {bestCause?.reason && (
                <div className="mt-5 border-t border-em-line pt-4">
                  <span className="tech-label">Why this diagnosis</span>
                  <p className="mt-1.5 max-w-4xl text-xs leading-relaxed text-em-steel">{bestCause.reason}</p>
                </div>
              )}

              <div className="mt-5 flex items-center justify-between border-t border-em-line pt-4">
                <p className="max-w-xl text-2xs leading-relaxed text-em-muted">
                  Decision support only. Confirm the finding against the approved service procedure before
                  replacing any component.
                </p>
                <button onClick={() => setShowConfirm(true)} className="btn-dark shrink-0">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Record verified repair
                </button>
              </div>
            </div>
          </section>

          {/* ==================== LEVEL 3 — EVIDENCE ==================== */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <div className="panel">
              <div className="panel-head">
                <span className="tech-label flex items-center gap-2">
                  <Database className="h-3.5 w-3.5 text-em-steel" />
                  Historical engineering evidence
                </span>
                <span className="tech-value tnum">{diagnosis.historical_evidence?.length || 0}</span>
              </div>
              <ul className="divide-y divide-em-line">
                {(diagnosis.historical_evidence || []).map((c) => (
                  <li key={c.case_id} className="p-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-em-graphite">{c.case_id}</span>
                      <div className="flex items-center gap-2">
                        <ProvenanceTag source={c.source_type} />
                        <span className="tech-value tnum">Similarity {c.similarity}</span>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-em-graphite">
                      <span className="text-em-steel">Failure: </span>
                      {c.failure_mode} <span className="text-em-steel">({c.component})</span>
                    </p>
                    <p className="mt-1 text-2xs leading-relaxed text-em-steel">
                      <span className="tech-label">Symptoms </span>
                      {c.symptom}
                    </p>
                    <p className="mt-1 text-2xs leading-relaxed text-em-steel">
                      <span className="tech-label">Inspection </span>
                      {c.inspection}
                    </p>
                    <p className="mt-1 text-2xs leading-relaxed text-em-success">
                      <span className="tech-label">Repair </span>
                      {c.repair}
                    </p>
                  </li>
                ))}
                {!diagnosis.historical_evidence?.length && (
                  <li className="p-4 text-xs text-em-muted">No comparable historical cases retrieved.</li>
                )}
              </ul>
            </div>

            <div className="space-y-5">
              <div className="panel">
                <div className="panel-head">
                  <span className="tech-label flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-em-steel" />
                    Document evidence
                  </span>
                  <span className="tech-value tnum">{diagnosis.document_evidence?.length || 0}</span>
                </div>
                <ul className="divide-y divide-em-line">
                  {(diagnosis.document_evidence || []).map((d) => (
                    <li key={d.chunk_id} className="p-3.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-em-graphite">{d.document_name}</span>
                        <span className="tech-value">
                          Page {d.page_number} · {d.section_heading}
                        </span>
                      </div>
                      <p className="mt-2 border-l-2 border-em-line pl-2.5 text-2xs leading-relaxed text-em-steel">
                        {d.chunk_text?.slice(0, 300)}
                        {d.chunk_text?.length > 300 ? '…' : ''}
                      </p>
                    </li>
                  ))}
                  {!diagnosis.document_evidence?.length && (
                    <li className="p-4 text-xs text-em-muted">No manual passages retrieved.</li>
                  )}
                </ul>
              </div>

              {diagnosis.sensor_evidence && (
                <div className="panel">
                  <div className="panel-head">
                    <span className="tech-label flex items-center gap-2">
                      <Activity className="h-3.5 w-3.5 text-em-steel" />
                      Condition evidence
                    </span>
                    <span className="chip-neutral">Test-rig dataset</span>
                  </div>
                  <div className="p-3.5">
                    <p className="text-2xs leading-relaxed text-em-steel">
                      {diagnosis.sensor_evidence.dataset_source}
                    </p>
                    <dl className="mt-3 grid grid-cols-2 gap-3">
                      <div>
                        <dt className="tech-label">Pump leakage condition</dt>
                        <dd className="tech-value mt-0.5">
                          {diagnosis.sensor_evidence.pump_leakage_condition}
                        </dd>
                      </div>
                      <div>
                        <dt className="tech-label">Cooler condition</dt>
                        <dd className="tech-value mt-0.5">{diagnosis.sensor_evidence.cooler_condition}</dd>
                      </div>
                      <div>
                        <dt className="tech-label">Accumulator</dt>
                        <dd className="tech-value mt-0.5">
                          {diagnosis.sensor_evidence.accumulator_condition}
                        </dd>
                      </div>
                      <div>
                        <dt className="tech-label">Classification confidence</dt>
                        <dd className="tech-value tnum mt-0.5">
                          {diagnosis.sensor_evidence.confidence_score}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ========= LEVEL 4 — technical detail (engineer / admin only) ========= */}
          {isEngineer && diagnosis.timings && (
            <div className="panel">
              <div className="panel-head">
                <span className="tech-label">Retrieval and processing detail</span>
                <span className="tech-value">Engineering role</span>
              </div>
              <dl className="grid grid-cols-2 gap-3 p-4 md:grid-cols-4 xl:grid-cols-8">
                {[
                  ['Total', diagnosis.timings.total_ms],
                  ['Retrieval', diagnosis.timings.retrieval_total_ms],
                  ['Embedding', diagnosis.timings.embedding_ms],
                  ['Index search', diagnosis.timings.faiss_retrieval_ms],
                  ['Sensor model', diagnosis.timings.sensor_ml_ms],
                  ['Local model', diagnosis.timings.llm_ms],
                  ['Database', diagnosis.timings.mysql_ms],
                  ['Prompt size', diagnosis.timings.prompt_chars],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="tech-label">{label}</dt>
                    <dd className="tech-value tnum mt-0.5">
                      {value == null ? '—' : label === 'Prompt size' ? `${value} chars` : `${value} ms`}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="border-t border-em-line px-4 py-2.5 text-2xs text-em-steel">
                Retrieval is served from the local index and is effectively instant; the local language model
                dominates total time on CPU-only hardware.
              </p>
            </div>
          )}
        </>
      )}

      {/* ==================== VERIFICATION (knowledge loop) ==================== */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-em-graphite/50 p-4">
          <div className="panel w-full max-w-lg">
            <div className="panel-head">
              <span className="tech-label">Record verified repair</span>
              <button onClick={() => setShowConfirm(false)} className="text-em-muted hover:text-em-graphite">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-4 p-4">
              <p className="text-2xs leading-relaxed text-em-steel">
                What you record here is what future diagnoses retrieve. Confirm the actual finding, not the
                suggested one — if they differ, record what you actually found.
              </p>
              <div>
                <label htmlFor="finding" className="tech-label mb-1.5 block">
                  Actual inspection finding
                </label>
                <input
                  id="finding"
                  value={finding}
                  onChange={(e) => setFinding(e.target.value)}
                  className="field"
                  placeholder="e.g. pump swashplate scored, internal leakage measured"
                />
              </div>
              <div>
                <label htmlFor="repair" className="tech-label mb-1.5 block">
                  Actual repair performed
                </label>
                <input
                  id="repair"
                  value={repair}
                  onChange={(e) => setRepair(e.target.value)}
                  className="field"
                  placeholder="e.g. replaced pump rotating group and seals"
                />
              </div>
              {confirmMsg && (
                <p className="border-l-2 border-em-success bg-em-successSoft px-3 py-2 text-2xs text-em-success">
                  {confirmMsg}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setShowConfirm(false)} className="btn-outline">
                  Cancel
                </button>
                <button onClick={submitVerification} className="btn-amber">
                  Record
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
