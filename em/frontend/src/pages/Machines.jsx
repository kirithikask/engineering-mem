import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ArrowRight, Truck, AlertTriangle } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';
import { formatHours } from '../utils/format';
import api from '../services/api';

const STATUS_CLS = {
  Operational: 'chip-success',
  Maintenance: 'chip-amber',
};

export default function Machines() {
  const [machines, setMachines] = useState([]);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [mRes, sRes] = await Promise.all([api.get('/machines'), api.get('/stats')]);
        if (cancelled) return;
        setMachines(mRes.machines || []);
        setStats(sRes);
      } catch (err) {
        if (!cancelled) setError('Engineering database unavailable. Fleet registry could not be loaded.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return machines;
    return machines.filter(
      (m) =>
        m.machine_id.toLowerCase().includes(q) ||
        String(m.machine_model || '').toLowerCase().includes(q) ||
        String(m.machine_type || '').toLowerCase().includes(q) ||
        String(m.manufacturer || '').toLowerCase().includes(q)
    );
  }, [machines, search]);

  const dist = stats?.cases?.failure_distribution || [];
  const statusCount = (name) =>
    stats?.machines?.by_status?.find((s) => s.status === name)?.count || 0;

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

      {/* Real fleet aggregates, reported by the database */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ['Machines on record', stats ? stats.machines.total.toLocaleString() : '—'],
          ['Operational', stats ? statusCount('Operational').toLocaleString() : '—'],
          ['Under maintenance', stats ? statusCount('Maintenance').toLocaleString() : '—'],
          ['Recorded interventions', stats ? stats.cases.total.toLocaleString() : '—'],
        ].map(([label, value]) => (
          <div key={label} className="panel p-3.5">
            <span className="tech-label">{label}</span>
            <span className="tech-value tnum mt-1.5 block text-xl">{value}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Real component failure distribution across the case archive */}
        <div className="panel lg:col-span-5">
          <div className="panel-head">
            <span className="tech-label">Recorded cases by component</span>
            <span className="tech-value tnum">{dist.length}</span>
          </div>
          <div className="h-64 p-3">
            {dist.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dist} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 34 }}>
                  <XAxis type="number" tick={{ fill: '#596168', fontSize: 10 }} stroke="#D6D5CF" />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={96}
                    tick={{ fill: '#596168', fontSize: 10 }}
                    stroke="#D6D5CF"
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#FFFFFF',
                      border: '1px solid #D6D5CF',
                      borderRadius: 2,
                      fontSize: 11,
                    }}
                  />
                  <Bar dataKey="count" radius={[0, 2, 2, 0]}>
                    {dist.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="p-3 text-xs text-em-muted">Data not available.</p>
            )}
          </div>
          <p className="border-t border-em-line px-3 py-2 text-2xs text-em-muted">
            Aggregated from every indexed maintenance record, including clearly-labelled demo data.
          </p>
        </div>

        {/* Registry */}
        <div className="panel lg:col-span-7">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <Truck className="h-3.5 w-3.5 text-em-steel" />
              Fleet registry
            </span>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-em-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by ID, model, type or manufacturer"
                className="field w-64 py-1.5 pl-8 text-xs"
              />
            </div>
          </div>

          <div className="max-h-[26rem] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-em-panelDeep">
                <tr>
                  {['Machine', 'Model', 'Type', 'Hours', 'Status', ''].map((h) => (
                    <th key={h} className="tech-label px-3 py-2 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-em-line">
                {filtered.slice(0, 300).map((m) => (
                  <tr key={m.machine_id} className="hover:bg-em-paper">
                    <td className="px-3 py-2 font-mono font-bold text-em-graphite">{m.machine_id}</td>
                    <td className="px-3 py-2 text-em-graphite">{m.machine_model}</td>
                    <td className="px-3 py-2 text-em-steel">{m.machine_type}</td>
                    <td className="px-3 py-2 font-mono tnum text-em-steel">
                      {formatHours(m.operating_hours)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={STATUS_CLS[m.status] || 'chip-neutral'}>{m.status}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Link
                        to={`/machines/${m.machine_id}`}
                        className="inline-flex items-center gap-1 font-semibold text-em-amberDark hover:underline"
                      >
                        Open
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
                {!loading && filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-xs text-em-muted">
                      No machines match the current filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {filtered.length > 300 && (
            <p className="border-t border-em-line px-3 py-2 text-2xs text-em-muted">
              Showing first 300 of {filtered.length.toLocaleString()} matching machines — narrow the filter to
              see others.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
