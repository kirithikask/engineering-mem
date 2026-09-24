import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ClipboardList, Plus, Radar, Wrench } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { EmptyState, Notice } from '../components/common/Evidence';
import { formatHours } from '../utils/format';

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

const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export default function Investigations() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [investigations, setInvestigations] = useState([]);
  const [machines, setMachines] = useState([]);
  const [status, setStatus] = useState('');
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    machine_id: '',
    title: '',
    problem_statement: '',
    symptoms: ['Slow boom movement', 'Weak digging force'],
    subsystem: 'Hydraulic System',
    severity: 'MEDIUM',
  });

  const load = useCallback(async () => {
    try {
      const [inv, mach] = await Promise.all([
        api.get('/investigations', { params: status ? { status } : {} }),
        api.get('/machines'),
      ]);
      setInvestigations(inv.investigations || []);
      setMachines(mach.machines || []);
      setError(null);
    } catch (err) {
      setError('Investigations could not be loaded.');
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleSymptom = (symptom) => {
    setForm((prev) => ({
      ...prev,
      symptoms: prev.symptoms.includes(symptom)
        ? prev.symptoms.filter((item) => item !== symptom)
        : [...prev.symptoms, symptom],
    }));
  };

  const create = async (event) => {
    event.preventDefault();
    if (!form.machine_id || form.symptoms.length === 0) {
      setError('Select a machine and at least one symptom.');
      return;
    }
    setCreating(true);
    try {
      const res = await api.post('/investigations', {
        ...form,
        title: form.title || form.symptoms.join(' + '),
        problem_statement: form.problem_statement || form.symptoms.join(' + '),
      });
      navigate(`/investigations/${res.investigation.investigation_id}`);
    } catch (err) {
      setError(err?.detail || 'The investigation could not be created.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Radar className="h-3.5 w-3.5 text-em-steel" />
              Investigations
            </span>
            <select className="field w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="OPEN">Open</option>
              <option value="IN_PROGRESS">In progress</option>
              <option value="VERIFIED">Verified</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>
          <ul className="divide-y divide-em-line">
            {investigations.map((item) => (
              <li key={item.investigation_id}>
                <Link
                  to={`/investigations/${item.investigation_id}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3.5 py-3 hover:bg-em-paper"
                >
                  <span className="font-mono text-xs font-bold text-em-navy">{item.investigation_id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-em-graphite">{item.title}</span>
                    <span className="tech-value block truncate">
                      {item.machine_id} · {item.subsystem} · opened {item.opened_at} by {item.opened_by_name || 'unknown'}
                    </span>
                  </span>
                  {item.failed_attempt_count > 0 && (
                    <span className="chip-fault">{item.failed_attempt_count} failed attempts</span>
                  )}
                  <span className={`chip-${item.status === 'CLOSED' || item.status === 'VERIFIED' ? 'success' : item.status === 'OPEN' ? 'amber' : 'navy'}`}>
                    {item.status.replace('_', ' ').toLowerCase()}
                  </span>
                </Link>
              </li>
            ))}
            {investigations.length === 0 && (
              <li className="p-4">
                <EmptyState
                  title="No investigations recorded"
                  detail="Create one from a reported fault. Every finding, repair attempt and re-evaluation is stored against it."
                />
              </li>
            )}
          </ul>
        </div>

        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Wrench className="h-3.5 w-3.5 text-em-steel" />
              Open a new investigation
            </span>
          </div>
          <form className="space-y-3 p-3.5" onSubmit={create}>
            <label className="block">
              <span className="tech-label">Machine</span>
              <select
                className="field mt-1"
                value={form.machine_id}
                onChange={(e) => setForm({ ...form, machine_id: e.target.value })}
                required
              >
                <option value="">Select machine…</option>
                {machines.map((machine) => (
                  <option key={machine.machine_id} value={machine.machine_id}>
                    {machine.machine_id} — {machine.machine_model} ({formatHours(machine.operating_hours)} h)
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="tech-label">Reported fault</span>
              <input
                className="field mt-1"
                placeholder="Slow boom + weak digging force"
                value={form.problem_statement}
                onChange={(e) => setForm({ ...form, problem_statement: e.target.value, title: e.target.value })}
              />
            </label>

            <div>
              <span className="tech-label">Symptoms</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {PRESET_SYMPTOMS.map((symptom) => (
                  <button
                    type="button"
                    key={symptom}
                    onClick={() => toggleSymptom(symptom)}
                    className={`border px-2 py-1 text-2xs transition-colors ${
                      form.symptoms.includes(symptom)
                        ? 'border-em-amber bg-em-amberSoft text-em-amberDark'
                        : 'border-em-line text-em-steel hover:border-em-steel'
                    }`}
                  >
                    {symptom}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="tech-label">Subsystem</span>
                <input className="field mt-1" value={form.subsystem} onChange={(e) => setForm({ ...form, subsystem: e.target.value })} />
              </label>
              <label className="block">
                <span className="tech-label">Severity</span>
                <select className="field mt-1" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
                  {SEVERITIES.map((severity) => (
                    <option key={severity} value={severity}>{severity}</option>
                  ))}
                </select>
              </label>
            </div>

            <button className="btn-amber w-full justify-center" type="submit" disabled={creating}>
              <Plus className="h-3.5 w-3.5" />
              {creating ? 'Opening investigation…' : 'Open investigation'}
            </button>
            {error && <Notice tone="fault" title="Action failed">{error}</Notice>}
            <p className="text-2xs leading-relaxed text-em-muted">
              Opened by {user?.full_name || user?.username}. The investigation becomes the container for findings, failed
              attempts, verification and the engineering case that is preserved at the end.
            </p>
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <ClipboardList className="h-3.5 w-3.5 text-em-steel" />
            How an investigation runs
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 p-3.5 text-2xs text-em-steel md:grid-cols-6">
          {['Machine', 'Symptoms', 'Evidence retrieval', 'Inspection', 'Finding', 'Re-evaluation', 'Root cause', 'Repair', 'Verification', 'New engineering knowledge'].map(
            (step, index) => (
              <div key={step} className="border border-em-line bg-em-surface px-2 py-1.5">
                <span className="block font-mono text-em-muted">{String(index + 1).padStart(2, '0')}</span>
                <span className="block font-semibold uppercase tracking-label text-em-graphite">{step}</span>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
