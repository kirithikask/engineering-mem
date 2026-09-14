import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  FileText,
  ClipboardList,
  Wrench,
  BookOpen,
  Gauge,
  Cpu,
  Database,
  Layers,
  ShieldAlert,
  CircleDot,
} from 'lucide-react';
import MachineScene from '../components/3d/MachineScene';
import useReveal from '../hooks/useReveal';
import api from '../services/api';

function Reveal({ children, className = '', delay = 0 }) {
  const [ref, visible] = useReveal();
  return (
    <div
      ref={ref}
      className={`reveal ${visible ? 'is-visible' : ''} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

function SectionLabel({ index, children }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <span className="font-mono text-2xs font-bold tracking-label text-em-amber">§{index}</span>
      <span className="h-px w-8 bg-em-line" />
      <span className="tech-label">{children}</span>
    </div>
  );
}

// Engineering callout lines overlaid on the hero machine
const HERO_CALLOUTS = [
  { label: 'HYDRAULIC SYSTEM',  sub: 'Pump · Filter · Lines',   side: 'right', top: '22%' },
  { label: 'POWERTRAIN',        sub: 'Engine · Drive',           side: 'right', top: '42%' },
  { label: 'IMPLEMENT SYSTEM',  sub: 'Lift Arms · Bucket',       side: 'right', top: '62%' },
  { label: 'COOLING',           sub: 'Hydraulic Cooler',         side: 'left',  top: '28%' },
  { label: 'CONTROL SYSTEM',    sub: 'Pilot · Valve Block',      side: 'left',  top: '52%' },
];

const KNOWLEDGE_SOURCES = [
  { icon: BookOpen,      title: 'Engineering manuals',  detail: 'Hydraulic system procedures and specifications' },
  { icon: ClipboardList, title: 'Service reports',      detail: 'Field findings, root causes, parts replaced' },
  { icon: Wrench,        title: 'Maintenance records',  detail: 'Work orders with operating hours and outcomes' },
  { icon: FileText,      title: 'Inspection reports',   detail: 'Measured pressures, temperatures, leak tests' },
  { icon: Gauge,         title: 'Condition data',       detail: 'Hydraulic test-rig condition classification' },
];

const PIPELINE = [
  { label: 'Symptoms reported',            detail: 'Every stated symptom, parsed into a structured representation' },
  { label: 'Machine context',              detail: 'Model, subsystem and recorded operating hours' },
  { label: 'Historical cases retrieved',   detail: 'Comparable past failures and their resolutions' },
  { label: 'Document evidence retrieved',  detail: 'Manual sections relevant to the symptoms' },
  { label: 'Condition evidence assessed',  detail: 'Condition classification where measurements exist' },
  { label: 'Local reasoning',              detail: 'Qwen 3:4B reasons only over the retrieved evidence' },
  { label: 'Actionable diagnosis',         detail: 'Likely cause, why, what to inspect next, prior fix' },
];

const DEMO_STAGES = [
  'Symptoms parsed',
  'Engineering memory searched',
  'Historical repairs retrieved',
  'Manual evidence retrieved',
  'Likely cause determined',
  'Component located on machine',
];

export default function Landing() {
  const [stats, setStats]           = useState(null);
  const [health, setHealth]         = useState(null);
  const [activeStage, setActiveStage] = useState(0);
  const [highlight, setHighlight]   = useState('comp_pump');
  const [heroState, setHeroState]   = useState('normal');

  useEffect(() => {
    api.get('/stats').then(setStats).catch(() => setStats(null));
    api.get('/health').then(setHealth).catch(() => setHealth(null));
  }, []);

  // Cycle demo stages
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStage((s) => (s + 1) % (DEMO_STAGES.length + 1));
    }, 1400);
    return () => clearInterval(timer);
  }, []);

  // Hero machine state cycles: normal → scanning → faulted → normal
  useEffect(() => {
    const seq = ['normal', 'scanning', 'faulted', 'normal'];
    let i = 0;
    const timer = setInterval(() => {
      i = (i + 1) % seq.length;
      setHeroState(seq[i]);
    }, 4200);
    return () => clearInterval(timer);
  }, []);

  const capability = [
    { icon: Database,  label: 'Machines on record',      value: stats ? stats.machines.total.toLocaleString() : null },
    { icon: Layers,    label: 'Maintenance cases',        value: stats ? stats.cases.total.toLocaleString() : null },
    { icon: CircleDot, label: 'Indexed memory vectors',   value: stats?.index?.vectors != null ? stats.index.vectors.toLocaleString() : null },
    { icon: Cpu,       label: 'Local reasoning model',    value: health?.models_loaded?.qwen_ollama ? 'Qwen 3:4B · online' : 'Unavailable' },
  ];

  return (
    <div className="min-h-screen bg-em-paper">

      {/* ================================================================
          HERO — large reference assembly as dominant visual
          ================================================================ */}
      <header className="relative overflow-hidden border-b border-em-line bg-em-surface">
        {/* Layer 1: navy technical grid */}
        <div className="blueprint-navy absolute inset-0 opacity-60" aria-hidden="true" />
        {/* Layer 2: warm amber top gradient */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-em-amber/[0.06] to-transparent" aria-hidden="true" />

        <div className="relative mx-auto max-w-[1600px] px-4 pt-6 lg:px-8">
          {/* Top bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center bg-em-navy font-mono text-xs font-bold text-em-amber">
                EM
              </span>
              <span>
                <span className="block text-sm font-bold uppercase tracking-[0.2em] text-em-graphite">
                  Engineering Memory
                </span>
                <span className="block text-2xs uppercase tracking-label text-em-muted">
                  Industrial Engineering Knowledge &amp; Diagnosis Platform
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Link to="/login"  className="btn-outline">Sign in</Link>
              <Link to="/signup" className="btn-amber">Create account</Link>
            </div>
          </div>

          {/* Hero composition: text left, large machine right */}
          <div className="grid grid-cols-1 gap-0 py-8 lg:grid-cols-12 lg:py-10">

            {/* Left: copy + stats */}
            <div className="flex flex-col justify-center lg:col-span-4 lg:pr-8">
              <span className="tech-label text-em-navy">Heavy machinery · Hydraulics</span>
              <h1 className="mt-3 text-3xl font-bold leading-[1.08] tracking-tight text-em-graphite lg:text-[2.6rem]">
                Turn industrial history into
                <span className="text-em-amberDark"> faster diagnosis.</span>
              </h1>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-em-steel">
                Evidence-backed troubleshooting for heavy machinery — connecting machine symptoms,
                historical repairs, engineering documentation and condition data into one engineering memory.
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Link to="/login"  className="btn-amber px-5 py-2.5">
                  Sign in <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                <Link to="/signup" className="btn-outline px-5 py-2.5">
                  Create account
                </Link>
              </div>

              <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-em-line pt-5">
                {capability.map(({ icon: Icon, label, value }) => (
                  <div key={label} className="flex items-start gap-2">
                    <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-amber" />
                    <div>
                      <dt className="tech-label">{label}</dt>
                      <dd className="tech-value tnum mt-0.5 text-sm text-em-graphite">
                        {value ?? 'Data not available'}
                      </dd>
                    </div>
                  </div>
                ))}
              </dl>
            </div>

            {/* Right: LARGE machine — extends beyond normal grid */}
            <div className="relative lg:col-span-8 lg:-mr-8">
              {/* Engineering callout lines — left side */}
              <div className="pointer-events-none absolute inset-y-0 left-0 z-10 hidden w-36 lg:block">
                {HERO_CALLOUTS.filter((c) => c.side === 'left').map((c) => (
                  <div
                    key={c.label}
                    className="absolute right-0 flex items-center gap-0 animate-calloutFade"
                    style={{ top: c.top }}
                  >
                    <div className="text-right">
                      <span className="block font-mono text-2xs font-bold uppercase tracking-[0.14em] text-em-navy">
                        {c.label}
                      </span>
                      <span className="block text-2xs text-em-steel">{c.sub}</span>
                    </div>
                    {/* Callout line */}
                    <svg width="32" height="2" className="shrink-0">
                      <line x1="0" y1="1" x2="32" y2="1" stroke="#C58B2A" strokeWidth="1" strokeDasharray="3 2" />
                    </svg>
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-em-amber" />
                  </div>
                ))}
              </div>

              {/* The machine */}
              <div className="relative overflow-hidden border border-em-navy/15 bg-em-navyTint shadow-lift animate-machineReveal">
  

                <MachineScene
                  highlightedComponentId={heroState === 'faulted' ? 'comp_pump' : null}
                  machineState={heroState}
                  autoRotate={false}
                  idleDrift={true}
                  showSubsystemBar={false}
                  className="h-[520px] w-full lg:h-[580px]"
                />


              </div>

              {/* Engineering callout lines — right side */}
              <div className="pointer-events-none absolute inset-y-0 right-0 z-10 hidden w-40 lg:block">
                {HERO_CALLOUTS.filter((c) => c.side === 'right').map((c) => (
                  <div
                    key={c.label}
                    className="absolute left-0 flex items-center gap-0 animate-calloutFade"
                    style={{ top: c.top }}
                  >
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-em-amber" />
                    <svg width="32" height="2" className="shrink-0">
                      <line x1="0" y1="1" x2="32" y2="1" stroke="#C58B2A" strokeWidth="1" strokeDasharray="3 2" />
                    </svg>
                    <div>
                      <span className="block font-mono text-2xs font-bold uppercase tracking-[0.14em] text-em-navy">
                        {c.label}
                      </span>
                      <span className="block text-2xs text-em-steel">{c.sub}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ========================= THE PROBLEM ========================= */}
      <section className="border-b border-em-line bg-em-paper">
        <div className="mx-auto max-w-[1500px] px-4 py-14 lg:px-6">
          <Reveal>
            <SectionLabel index="01">The problem</SectionLabel>
            <h2 className="max-w-3xl text-2xl font-bold tracking-tight text-em-navy">
              When a machine fails, the knowledge of how it was fixed last time is not where the
              technician is.
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-em-steel">
              Service history sits in work orders. Procedures sit in manuals. Condition findings sit in
              inspection reports. The technician at the machine has minutes, not hours, to find them.
            </p>
          </Reveal>

          <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-12">
            <Reveal className="lg:col-span-7" delay={80}>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {KNOWLEDGE_SOURCES.map(({ icon: Icon, title, detail }) => (
                  <div key={title} className="panel flex items-start gap-3 p-3.5">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-em-steel" />
                    <div>
                      <span className="block text-xs font-semibold uppercase tracking-wider text-em-graphite">
                        {title}
                      </span>
                      <span className="mt-0.5 block text-2xs leading-relaxed text-em-steel">{detail}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>

            <Reveal className="lg:col-span-5" delay={160}>
              <div className="panel h-full overflow-hidden">
                <div className="panel-head bg-em-navyTint">
                  <span className="tech-label text-em-navy">Consolidated into one memory</span>
                </div>
                <div className="scan-track">
                  <div className="p-5">
                    <span className="tech-label text-em-navy">Engineering Memory</span>
                    <p className="mt-2 text-xs leading-relaxed text-em-steel">
                      Every source is indexed against the same component model, so a symptom reported at
                      the machine reaches the historical repair, the manual section and the condition
                      evidence at once.
                    </p>
                    <dl className="mt-4 space-y-2 border-t border-em-line pt-4">
                      <div className="flex items-center justify-between">
                        <dt className="tech-label">Sources indexed</dt>
                        <dd className="tech-value tnum">{stats ? stats.cases.total.toLocaleString() : '—'}</dd>
                      </div>
                      <div className="flex items-center justify-between">
                        <dt className="tech-label">Manual passages</dt>
                        <dd className="tech-value tnum">
                          {stats ? stats.document_chunks.toLocaleString() : '—'}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between">
                        <dt className="tech-label">Retrieval</dt>
                        <dd className="tech-value">Local vector index</dd>
                      </div>
                    </dl>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ======================== HOW IT WORKS ======================== */}
      <section className="border-b border-em-line bg-em-surface">
        <div className="mx-auto max-w-[1500px] px-4 py-14 lg:px-6">
          <Reveal>
            <SectionLabel index="02">How it works</SectionLabel>
            <h2 className="text-2xl font-bold tracking-tight text-em-navy">
              A retrieval pipeline, not a chatbot.
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-em-steel">
              Each stage has one job. Retrieval finds comparable evidence; the local model reasons only
              over that evidence and must state when it is not sufficient.
            </p>
          </Reveal>

          <ol className="mt-8 grid grid-cols-1 gap-x-8 gap-y-0 md:grid-cols-2 lg:grid-cols-4">
            {PIPELINE.map((step, i) => (
              <Reveal key={step.label} delay={i * 70}>
                <li className="relative flex gap-3 pb-6">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center bg-em-navy font-mono text-2xs font-bold text-em-amber">
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold uppercase tracking-wider text-em-graphite">
                      {step.label}
                    </span>
                    <span className="mt-1 block text-2xs leading-relaxed text-em-steel">{step.detail}</span>
                  </span>
                  {i < PIPELINE.length - 1 && (
                    <span
                      className="absolute left-3 top-7 hidden h-[calc(100%-1.75rem)] w-px bg-em-line md:block"
                      aria-hidden="true"
                    />
                  )}
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* ==================== DIAGNOSIS EXPERIENCE ==================== */}
      <section className="border-b border-em-line bg-em-paper">
        <div className="mx-auto max-w-[1500px] px-4 py-14 lg:px-6">
          <Reveal>
            <SectionLabel index="03">The diagnosis experience</SectionLabel>
            <h2 className="text-2xl font-bold tracking-tight text-em-navy">
              What the technician actually receives.
            </h2>
          </Reveal>

          <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-12">
            <Reveal className="lg:col-span-4" delay={80}>
              <div className="panel p-4">
                <span className="tech-label">Reported symptoms</span>
                <ul className="mt-3 space-y-2">
                  {[
                    'Slow boom movement',
                    'Weak digging force',
                    'Worsens as hydraulic oil temperature rises',
                    'High hydraulic oil temperature',
                  ].map((s) => (
                    <li key={s} className="flex items-start gap-2 text-xs text-em-graphite">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-em-amber" />
                      {s}
                    </li>
                  ))}
                </ul>
                <div className="mt-4 border-t border-em-line pt-3">
                  <span className="tech-label">Machine</span>
                  <span className="tech-value mt-1 block">EXC-001 · ZX210</span>
                </div>
              </div>

              <div className="panel mt-3 p-4">
                <span className="tech-label">Analysis sequence</span>
                <ul className="mt-3 space-y-2">
                  {DEMO_STAGES.map((stage, i) => {
                    const done    = i < activeStage;
                    const current = i === activeStage;
                    return (
                      <li key={stage} className="flex items-center gap-2 text-2xs">
                        <span
                          className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center border ${
                            done    ? 'border-em-success bg-em-success text-white'
                            : current ? 'border-em-amber bg-em-amberSoft'
                            : 'border-em-line'
                          }`}
                        >
                          {done && '✓'}
                        </span>
                        <span className={done ? 'text-em-steel' : current ? 'font-semibold text-em-graphite' : 'text-em-muted'}>
                          {stage}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </Reveal>

            <Reveal className="lg:col-span-8" delay={160}>
              <div className="panel overflow-hidden">
                <div className="panel-head bg-em-navyTint">
                  <span className="tech-label text-em-navy">Final diagnosis</span>
                  <span className="chip-amber">Evidence sufficient</span>
                </div>
                <div className="p-5">
                  <span className="tech-label">Likely cause</span>
                  <p className="mt-1 text-xl font-bold tracking-tight text-em-graphite">
                    Hydraulic pump internal leakage
                  </p>
                  <div className="mt-4 grid grid-cols-1 gap-4 border-t border-em-line pt-4 sm:grid-cols-2">
                    <div>
                      <span className="tech-label">Recommended inspection</span>
                      <p className="mt-1 text-xs leading-relaxed text-em-graphite">
                        Measure pump delivery flow and main relief pressure at operating temperature.
                      </p>
                    </div>
                    <div>
                      <span className="tech-label">Previous successful resolution</span>
                      <p className="mt-1 text-xs leading-relaxed text-em-graphite">
                        Hydraulic pump replaced; performance restored.
                      </p>
                    </div>
                    <div>
                      <span className="tech-label">Affected component</span>
                      <p className="tech-value mt-1">Hydraulic Pump</p>
                    </div>
                    <div>
                      <span className="tech-label">Evidence sufficiency</span>
                      <p className="mt-1 text-xs font-semibold uppercase tracking-wider text-em-success">
                        Sufficient
                      </p>
                    </div>
                  </div>
                  <div className="mt-5 border-t border-em-line pt-4">
                    <span className="tech-label">Why this diagnosis</span>
                    <p className="mt-1 text-xs leading-relaxed text-em-steel">
                      Slow boom and arm movement with weak digging force that degrades as oil temperature
                      rises matches recorded historical cases where pump pressure fell with increasing
                      temperature and hydraulic performance was restored after pump replacement.
                    </p>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ========================= 3D MACHINE ========================= */}
      <section className="border-b border-em-line bg-em-surface">
        <div className="mx-auto max-w-[1500px] px-4 py-14 lg:px-6">
          <Reveal>
            <SectionLabel index="04">Machine visualisation</SectionLabel>
            <h2 className="text-2xl font-bold tracking-tight text-em-navy">
              The diagnosed component, located on the machine.
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-em-steel">
              Select a component to inspect it, or let a diagnosis focus the machine on the suspected
              assembly automatically.
            </p>
          </Reveal>

          <Reveal className="mt-6" delay={80}>
            <div className="flex flex-wrap items-center gap-2">
              {[
                ['comp_pump',     'Hydraulic pump'],
                ['comp_valve',    'Control valve'],
                ['comp_cooler',   'Hydraulic cooler'],
                ['comp_lift_arm', 'Lift arms'],
                ['comp_travel',   'Undercarriage'],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setHighlight(id)}
                  className={`px-3 py-1.5 text-2xs font-semibold uppercase tracking-wider transition-colors ${
                    highlight === id
                      ? 'bg-em-navy text-white'
                      : 'border border-em-line text-em-steel hover:border-em-navy hover:text-em-navy'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </Reveal>

          <Reveal className="mt-4" delay={120}>
            <div className="overflow-hidden border border-em-navy/15">
              <MachineScene
                highlightedComponentId={highlight}
                autoRotate
                machineState="normal"
                className="h-[500px] w-full"
              />
            </div>
          </Reveal>
        </div>
      </section>

      {/* =========================== CLOSING =========================== */}
      <section className="bg-em-paper">
        <div className="mx-auto max-w-[1500px] px-4 py-14 lg:px-6">
          <Reveal>
            <div className="panel flex flex-col items-start justify-between gap-5 p-6 md:flex-row md:items-center">
              <div>
                <h2 className="text-xl font-bold tracking-tight text-em-navy">
                  Preserve the knowledge your team already has.
                </h2>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-em-steel">
                  Every verified repair becomes retrievable engineering memory for the next technician.
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Link to="/login"  className="btn-amber px-5 py-2.5">
                  Sign in <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                <Link to="/signup" className="btn-outline px-5 py-2.5">
                  Create account
                </Link>
              </div>
            </div>

            <div className="mt-6 flex items-start gap-2">
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-warning" />
              <p className="text-2xs leading-relaxed text-em-steel">
                Engineering decision support only. Verify every diagnosis against the approved OEM service
                procedure and apply lockout/tagout before any physical intervention.
              </p>
            </div>
          </Reveal>
        </div>
      </section>
    </div>
  );
}
