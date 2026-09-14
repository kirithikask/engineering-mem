import React from 'react';
import { useLocation } from 'react-router-dom';
import { ShieldAlert, CircleAlert } from 'lucide-react';
import TopNav from './TopNav';
import useSystemStatus from '../../hooks/useSystemStatus';

/** Page title strip: every workstation page states where the operator is. */
function PageHeading({ title, purpose, actions }) {
  return (
    <div className="flex flex-col gap-3 border-b border-em-line pb-3 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <h1 className="text-lg font-bold uppercase tracking-[0.12em] text-em-graphite">{title}</h1>
        {purpose && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-em-steel">{purpose}</p>}
      </div>
      {actions}
    </div>
  );
}

const PAGE_META = {
  '/diagnose': {
    title: 'Diagnosis Workstation',
    purpose:
      'Report every observed symptom. The system retrieves comparable historical repairs, engineering documentation and condition evidence, then states the most likely cause and what to inspect next.',
  },
  '/machines': {
    title: 'Machine Overview',
    purpose: 'Fleet registry with recorded operating hours, service status and accumulated maintenance history.',
  },
  '/engineering-memory': {
    title: 'Engineering Memory',
    purpose:
      'Semantic search across the accumulated maintenance case archive and indexed engineering documentation.',
  },
  '/cases': {
    title: 'Historical Cases',
    purpose: 'Dense archive of recorded maintenance interventions, including provenance of every record.',
  },
  '/evidence': {
    title: 'Evidence / Manuals',
    purpose: 'Indexed engineering documents and the passages retrieved to support a diagnosis.',
  },
  '/sensors': {
    title: 'Condition Analysis',
    purpose:
      'Hydraulic test-rig condition classification. This is a public condition-monitoring dataset used as supporting evidence and is not live machine telemetry.',
  },
  '/benchmark': {
    title: 'Retrieval Benchmark',
    purpose: 'Measured retrieval accuracy and latency for the local engineering-memory index.',
  },
  '/admin': {
    title: 'Administration',
    purpose: 'Operators, document ingestion and platform state.',
  },
};

export default function AppShell({ children }) {
  const location = useLocation();
  const { warnings } = useSystemStatus();
  const meta = PAGE_META[location.pathname] || {};
  const isMachineDetail = location.pathname.startsWith('/machines/');

  return (
    <div className="flex min-h-screen flex-col bg-em-paper">
      <TopNav />

      {warnings.length > 0 && (
        <div className="border-b border-em-line bg-em-faultSoft">
          <div className="mx-auto flex max-w-[1500px] items-center gap-2 px-4 py-2 lg:px-6">
            <CircleAlert className="h-3.5 w-3.5 shrink-0 text-em-fault" />
            <span className="text-2xs font-semibold uppercase tracking-wider text-em-fault">
              {warnings.join(' ')}
            </span>
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-5 lg:px-6">
        {!isMachineDetail && meta.title && (
          <div className="mb-5">
            <PageHeading title={meta.title} purpose={meta.purpose} />
          </div>
        )}
        {children}
      </main>

      <footer className="border-t border-em-line bg-em-surface">
        <div className="mx-auto flex max-w-[1500px] flex-col gap-2 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div className="flex items-start gap-2">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-warning" />
            <p className="text-2xs leading-relaxed text-em-steel">
              <span className="font-semibold uppercase tracking-label text-em-ink">Safety advisory — </span>
              Engineering decision support only. Verify every diagnosis against the approved OEM service
              procedure and apply lockout/tagout before any physical intervention.
            </p>
          </div>
          <p className="text-2xs uppercase tracking-label text-em-muted">
            Runs entirely on this machine · No cloud services
          </p>
        </div>
      </footer>
    </div>
  );
}
