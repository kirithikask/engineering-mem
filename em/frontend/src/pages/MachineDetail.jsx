import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Wrench, AlertTriangle, ClipboardList, Activity } from 'lucide-react';
import api from '../services/api';
import MachineScene from '../components/3d/MachineScene';
import { formatHours, orNotRecorded } from '../utils/format';

export default function MachineDetail() {
  const { machineId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get(`/machines/${machineId}`)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setError('Machine record could not be loaded.');
      });
    return () => {
      cancelled = true;
    };
  }, [machineId]);

  const machine = data?.machine;
  const cases = data?.recent_cases || [];
  const diagnoses = data?.recent_diagnoses || [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-em-line pb-3">
        <div className="flex items-center gap-3">
          <Link to="/machines" className="btn-ghost px-2 py-1 text-2xs">
            <ArrowLeft className="h-3.5 w-3.5" />
            Fleet
          </Link>
          <div>
            <h1 className="font-mono text-lg font-bold tracking-tight text-em-graphite">
              {machineId}
            </h1>
            <span className="block text-2xs uppercase tracking-label text-em-muted">
              {machine ? `${machine.machine_model} · ${machine.machine_type} · ${machine.manufacturer}` : 'Loading machine record'}
            </span>
          </div>
        </div>
        <Link to="/diagnose" className="btn-amber">
          <Wrench className="h-3.5 w-3.5" />
          Diagnose this machine
        </Link>
      </div>

      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-fault" />
            <p className="text-xs text-em-graphite">{error}</p>
          </div>
        </div>
      )}

      {machine && (
        <dl className="grid grid-cols-2 gap-4 border border-em-line bg-em-surface p-4 md:grid-cols-5">
          {[
            ['Machine model', machine.machine_model],
            ['Type', machine.machine_type],
            ['Manufacturer', orNotRecorded(machine.manufacturer)],
            ['Operating hours', formatHours(machine.operating_hours)],
            ['Last maintenance', orNotRecorded(machine.last_maintenance)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="tech-label">{label}</dt>
              <dd className="tech-value tnum mt-1 normal-case tracking-normal text-sm text-em-graphite">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <div className="overflow-hidden border border-em-navy/15">
            <div className="flex items-center justify-between border-b border-em-navy/20 bg-em-navyTint px-4 py-2">
              <span className="font-mono text-2xs font-bold uppercase tracking-[0.18em] text-em-navy">
                {machine ? `${machine.machine_id} · ${machine.machine_model}` : machineId}
              </span>
              <span className="tech-value">{selected ? 'Component selected' : 'Interactive'}</span>
            </div>
            <MachineScene
              selectedComponentId={selected}
              onSelectComponent={(id) => setSelected(id)}
              machineState="normal"
              className="h-[560px] w-full"
            />
            <p className="border-t border-em-navy/15 bg-em-navyTint/40 px-3 py-2.5 text-2xs leading-relaxed text-em-steel">
              Select an assembly to review its recorded failures and history below. The same component ids are
              used by the diagnosis engine, so a diagnosis focuses this machine automatically.
            </p>
          </div>
        </div>

        <div className="xl:col-span-4 space-y-5">
          <div className="panel">
            <div className="panel-head">
              <span className="tech-label flex items-center gap-2">
                <ClipboardList className="h-3.5 w-3.5 text-em-steel" />
                Recorded maintenance history
              </span>
              <span className="tech-value tnum">{cases.length}</span>
            </div>
            <ul className="max-h-72 divide-y divide-em-line overflow-y-auto">
              {cases.map((c) => (
                <li key={c.case_id} className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-bold text-em-graphite">{c.case_id}</span>
                    <span className="tech-value tnum">
                      {c.operating_hours != null ? `${Number(c.operating_hours).toLocaleString()} h` : '—'}
                    </span>
                  </div>
                  <p className="mt-1 text-2xs text-em-steel">
                    {c.component} — {c.failure_mode}
                  </p>
                  <p className="mt-0.5 text-2xs leading-relaxed text-em-muted">{c.symptom}</p>
                </li>
              ))}
              {cases.length === 0 && (
                <li className="p-4 text-xs text-em-muted">No maintenance history recorded for this machine.</li>
              )}
            </ul>
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="tech-label flex items-center gap-2">
                <Activity className="h-3.5 w-3.5 text-em-steel" />
                Recent diagnoses
              </span>
              <span className="tech-value tnum">{diagnoses.length}</span>
            </div>
            <ul className="max-h-64 divide-y divide-em-line overflow-y-auto">
              {diagnoses.map((d) => (
                <li key={d.diagnosis_id} className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-2xs text-em-steel">{d.diagnosis_id}</span>
                    <span className="chip-neutral">{d.evidence_sufficiency}</span>
                  </div>
                  <p className="mt-1 text-xs text-em-graphite">
                    {d.likely_cause} <span className="text-em-steel">({d.affected_component})</span>
                  </p>
                  <p className="mt-0.5 text-2xs text-em-muted">{d.timestamp}</p>
                </li>
              ))}
              {diagnoses.length === 0 && (
                <li className="p-4 text-xs text-em-muted">No diagnoses recorded for this machine yet.</li>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
