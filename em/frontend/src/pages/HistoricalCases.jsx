import React, { useCallback, useEffect, useState } from 'react';
import { Search, Database, CheckCircle2, FlaskConical } from 'lucide-react';
import api from '../services/api';

const PAGE_SIZE = 100;

// Provenance is recorded per case, so synthetic prototype records are never
// presented as verified company maintenance history.
const PROVENANCE = {
  historical: { label: 'Historical record', cls: 'chip-neutral', icon: CheckCircle2 },
  verified_field_diagnosis: { label: 'Technician verified', cls: 'chip-success', icon: CheckCircle2 },
  field_entry: { label: 'Field entry', cls: 'chip-neutral', icon: CheckCircle2 },
  tata_industry_demo: { label: 'Demo / synthetic', cls: 'chip-amber', icon: FlaskConical },
};

const COMPONENT_FILTERS = [
  'All',
  'Hydraulic Pump',
  'Main Control Valve',
  'Hydraulic Cylinder',
  'Boom Cylinder',
  'Arm Cylinder',
  'Bucket Cylinder',
  'Hydraulic Cooler',
  'Oil Cooler',
  'Hydraulic Filter',
  'Accumulator',
  'Pilot System',
  'Swing Motor',
  'Travel Motor',
  'Hydraulic Line',
  'Hydraulic Oil',
];

export default function HistoricalCases() {
  const [cases, setCases] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [component, setComponent] = useState('All');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPage = useCallback(async ({ query, selectedComponent, offset }) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (query) params.set('q', query);
      if (selectedComponent !== 'All') params.set('component', selectedComponent);

      const res = await api.get(`/cases?${params.toString()}`);
      const incoming = res.cases || [];
      setCases((prev) => (offset === 0 ? incoming : [...prev, ...incoming]));
      setTotal(res.total || 0);
    } catch (err) {
      setError('Engineering database unavailable. Historical cases could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(
      () => fetchPage({ query: search.trim(), selectedComponent: component, offset: 0 }),
      search ? 350 : 0
    );
    return () => clearTimeout(timer);
  }, [search, component, fetchPage]);

  return (
    <div className="space-y-5">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center gap-2">
          {COMPONENT_FILTERS.map((c) => (
            <button
              key={c}
              onClick={() => setComponent(c)}
              className={`px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider transition-colors ${
                component === c
                  ? 'bg-em-graphite text-white'
                  : 'border border-em-line text-em-steel hover:border-em-steel hover:text-em-graphite'
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[18rem]">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-em-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search every record by symptom, failure mode, case ID, component or repair"
              className="field pl-9"
            />
          </div>
          <span className="tech-value tnum">
            Showing {cases.length} of {total.toLocaleString()}
          </span>
        </div>
      </div>

      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4 text-xs text-em-graphite">{error}</div>
      )}

      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-em-panelDeep">
              <tr>
                {['Case', 'Machine', 'Component', 'Failure mode', 'Symptoms', 'Repair action', 'Provenance'].map(
                  (h) => (
                    <th key={h} className="tech-label px-3 py-2 font-semibold">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-em-line">
              {cases.map((c) => {
                const prov = PROVENANCE[c.source_type] || PROVENANCE.historical;
                const Icon = prov.icon;
                return (
                  <tr key={c.case_id} className="hover:bg-em-paper">
                    <td className="whitespace-nowrap px-3 py-2 font-mono font-bold text-em-graphite">
                      {c.case_id}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-em-steel">{c.machine_id}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-em-graphite">{c.component}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-em-graphite">{c.failure_mode}</td>
                    <td className="max-w-xs truncate px-3 py-2 text-em-steel" title={c.symptom}>
                      {c.symptom}
                    </td>
                    <td className="max-w-xs truncate px-3 py-2 text-em-success" title={c.repair_action}>
                      {c.repair_action}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span className={prov.cls}>
                        <Icon className="h-2.5 w-2.5" />
                        {prov.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {!loading && cases.length === 0 && !error && (
            <div className="p-10 text-center">
              <Database className="mx-auto h-7 w-7 text-em-line" />
              <p className="mt-2 text-xs text-em-muted">No maintenance cases match the current filter.</p>
            </div>
          )}
        </div>
      </div>

      {cases.length < total && (
        <div className="flex justify-center">
          <button
            onClick={() =>
              fetchPage({ query: search.trim(), selectedComponent: component, offset: cases.length })
            }
            disabled={loading}
            className="btn-outline"
          >
            {loading ? 'Loading…' : `Load ${Math.min(PAGE_SIZE, total - cases.length)} more`}
          </button>
        </div>
      )}
    </div>
  );
}
