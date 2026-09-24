import React from 'react';
import { FlaskConical, ShieldCheck, UserCheck, FileWarning, Archive, CircleDot } from 'lucide-react';

/**
 * Evidence provenance components.
 *
 * The brief requires that evidence quality is never presented as uniform. These
 * chips render the four knowledge quality levels, the document version status and
 * the demo/synthetic marker, all from backend values — nothing here is inferred
 * on the client.
 */

const QUALITY_STYLES = {
  VERIFIED: { cls: 'chip-success', label: 'Verified', Icon: ShieldCheck, hint: 'Approved engineering knowledge' },
  ENGINEER_REVIEWED: { cls: 'chip-navy', label: 'Engineer reviewed', Icon: UserCheck, hint: 'Checked by an engineer, not manufacturer-approved' },
  TECHNICIAN_SUBMITTED: { cls: 'chip-amber', label: 'Technician submitted', Icon: CircleDot, hint: 'Field record, not yet reviewed by an engineer' },
  UNVERIFIED: { cls: 'chip-neutral', label: 'Unverified', Icon: FileWarning, hint: 'Captured, not checked by anyone' },
};

const STATUS_STYLES = {
  CURRENT: 'chip-success',
  APPROVED: 'chip-success',
  PENDING_REVIEW: 'chip-amber',
  DRAFT: 'chip-neutral',
  SUPERSEDED: 'chip-fault',
  ARCHIVED: 'chip-neutral',
  REJECTED: 'chip-fault',
};

export function QualityChip({ level, compact = false }) {
  if (!level) return null;
  const style = QUALITY_STYLES[String(level).toUpperCase()] || QUALITY_STYLES.UNVERIFIED;
  const { Icon } = style;
  return (
    <span className={style.cls} title={style.hint}>
      <Icon className="h-2.5 w-2.5" />
      {compact ? style.label.split(' ')[0] : style.label}
    </span>
  );
}

export function StatusChip({ status, revision }) {
  if (!status) return null;
  const cls = STATUS_STYLES[String(status).toUpperCase()] || 'chip-neutral';
  return (
    <span className={cls} title="Document revision status">
      {String(status).replace('_', ' ').toLowerCase()}
      {revision ? ` · rev ${revision}` : ''}
    </span>
  );
}

export function DemoChip({ show }) {
  if (!show) return null;
  return (
    <span className="chip-amber" title="Prototype/synthetic record, not verified engineering content">
      <FlaskConical className="h-2.5 w-2.5" />
      Demo / synthetic data
    </span>
  );
}

export function SupersededChip({ show }) {
  if (!show) return null;
  return (
    <span className="chip-fault" title="Retained as engineering history; a current revision takes priority">
      <Archive className="h-2.5 w-2.5" />
      Superseded
    </span>
  );
}

/** Confidence bar. The value must come from a backend measurement. */
export function ConfidenceMeter({ value, label = 'Extraction confidence', basis }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0)) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="tech-label">{label}</span>
        <span className="tech-value tnum">{pct.toFixed(0)}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full bg-em-panelDeep">
        <div
          className={`h-full ${pct >= 75 ? 'bg-em-success' : pct >= 45 ? 'bg-em-amber' : 'bg-em-fault'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {basis && <p className="mt-1 text-2xs leading-relaxed text-em-muted">{basis}</p>}
    </div>
  );
}

/** Consistent empty state so a page never implies data that is not there. */
export function EmptyState({ title, detail }) {
  return (
    <div className="border border-dashed border-em-line px-4 py-6 text-center">
      <p className="text-xs font-semibold uppercase tracking-label text-em-steel">{title}</p>
      {detail && <p className="mx-auto mt-1 max-w-xl text-2xs leading-relaxed text-em-muted">{detail}</p>}
    </div>
  );
}

export function Notice({ tone = 'info', title, children }) {
  const tones = {
    info: 'border-l-em-steel bg-em-surface',
    warning: 'border-l-em-warning bg-em-amberSoft/40',
    fault: 'border-l-em-fault bg-em-faultSoft/50',
    success: 'border-l-em-success bg-em-successSoft/50',
  };
  return (
    <div className={`border border-em-line border-l-2 ${tones[tone]} p-3`}>
      {title && <p className="text-2xs font-bold uppercase tracking-label text-em-graphite">{title}</p>}
      <div className="mt-1 text-2xs leading-relaxed text-em-steel">{children}</div>
    </div>
  );
}
