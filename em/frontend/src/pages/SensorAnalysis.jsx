import React, { useEffect, useState } from 'react';
import { Activity, Thermometer, Gauge, FlaskConical, AlertTriangle } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';
import api from '../services/api';

const BAR_COLORS = ['#55745F', '#C58B2A', '#A94D45', '#8A9298', '#596168'];

export default function SensorAnalysis() {
  const [machineId, setMachineId] = useState('');
  const [machines, setMachines] = useState([]);
  const [oilTemp, setOilTemp] = useState('');
  const [pressure, setPressure] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get('/machines')
      .then((res) => {
        const list = res.machines || [];
        setMachines(list);
        setMachineId((current) => current || (list[0]?.machine_id ?? ''));
      })
      .catch(() => setError('Engineering database unavailable.'));
  }, []);

  const run = async () => {
    if (!machineId) return;
    setBusy(true);
    setError(null);
    try {
      const params = {};
      if (oilTemp !== '') params.oil_temp = oilTemp;
      if (pressure !== '') params.pressure = pressure;
      const res = await api.get(`/sensors/${machineId}`, { params });
      setData(res);
    } catch (err) {
      setError('Condition analysis service unavailable.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machineId]);

  const analysis = data?.analysis;
  const profile = data?.reference_profile;

  return (
    <div className="space-y-5">
      {/* Provenance is stated up front: this is a published dataset, not live data */}
      <div className="panel border-l-2 border-l-em-amber p-4">
        <div className="flex items-start gap-2">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-em-amber" />
          <div>
            <span className="tech-label text-em-amberDark">Hydraulic test-rig condition monitoring</span>
            <p className="mt-1 max-w-4xl text-xs leading-relaxed text-em-graphite">
              {data?.provenance?.statement ||
                'The platform has no live connection to any machine, so no simulated sensor trace is shown. '}
              The classifier assessment below reflects the measurements you enter, and the reference figures
              are measured statistics of the dataset the model was trained on.
            </p>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label">Assessment inputs</span>
          <span className="tech-value">Measurements are optional</span>
        </div>
        <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-4">
          <div>
            <label htmlFor="unit" className="tech-label mb-1.5 block">
              Machine
            </label>
            <select
              id="unit"
              value={machineId}
              onChange={(e) => setMachineId(e.target.value)}
              className="field font-mono text-xs"
            >
              {machines.map((m) => (
                <option key={m.machine_id} value={m.machine_id}>
                  {m.machine_id} · {m.machine_model}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ot" className="tech-label mb-1.5 flex items-center gap-1.5">
              <Thermometer className="h-3 w-3 text-em-amber" />
              Oil temperature (°C)
            </label>
            <input
              id="ot"
              type="number"
              value={oilTemp}
              onChange={(e) => setOilTemp(e.target.value)}
              placeholder="Not measured"
              className="field font-mono text-xs"
            />
          </div>
          <div>
            <label htmlFor="pr" className="tech-label mb-1.5 flex items-center gap-1.5">
              <Gauge className="h-3 w-3 text-em-success" />
              Main line pressure (bar)
            </label>
            <input
              id="pr"
              type="number"
              value={pressure}
              onChange={(e) => setPressure(e.target.value)}
              placeholder="Not measured"
              className="field font-mono text-xs"
            />
          </div>
          <div className="flex items-end">
            <button onClick={run} disabled={busy || !machineId} className="btn-amber w-full">
              {busy ? 'Assessing…' : 'Assess condition'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-fault" />
            <p className="text-xs text-em-graphite">{error}</p>
          </div>
        </div>
      )}

      {analysis && (
        <>
          {!analysis.measurements_supplied && analysis.note && (
            <p className="border-l-2 border-em-warning bg-em-amberSoft px-3 py-2 text-2xs text-em-amberDark">
              {analysis.note}
            </p>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            {[
              ['Pump leakage condition', analysis.pump_leakage_condition, `model confidence ${analysis.confidence_score}`],
              ['Cooler condition', analysis.cooler_condition, `oil temperature ${analysis.measurements_recorded.hydraulic_oil_temperature_c} °C`],
              ['Accumulator', analysis.accumulator_condition, `pressure ${analysis.measurements_recorded.main_line_pressure_bar} bar`],
              ['Inference time', `${analysis.inference_ms} ms`, 'Random Forest classifier'],
            ].map(([label, value, detail]) => (
              <div key={label} className="panel p-4">
                <span className="tech-label">{label}</span>
                <span className="mt-1.5 block text-sm font-bold text-em-graphite">{value}</span>
                <span className="tech-value mt-0.5 block">{detail}</span>
              </div>
            ))}
          </div>

          {/* Measured condition-class distribution of the training dataset */}
          {profile?.distributions?.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <span className="tech-label flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5 text-em-steel" />
                  Reference dataset condition classes
                </span>
                <span className="tech-value tnum">{profile.cycles.toLocaleString()} cycles measured</span>
              </div>
              <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
                {profile.distributions.slice(0, 4).map((dist) => (
                  <div key={dist.field}>
                    <span className="tech-label">{dist.field.replace(/_/g, ' ')}</span>
                    <div className="mt-2 h-32">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={dist.samples} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
                          <XAxis
                            dataKey="code"
                            tick={{ fill: '#596168', fontSize: 10 }}
                            stroke="#D6D5CF"
                          />
                          <YAxis tick={{ fill: '#596168', fontSize: 10 }} stroke="#D6D5CF" />
                          <Tooltip
                            contentStyle={{
                              background: '#FFFFFF',
                              border: '1px solid #D6D5CF',
                              borderRadius: 2,
                              fontSize: 11,
                            }}
                            formatter={(value, _n, item) => [value, item?.payload?.label || '']}
                          />
                          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                            {dist.samples.map((s, i) => (
                              <Cell key={s.code} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <p className="mt-1 text-2xs text-em-muted">
                      {dist.samples.map((s) => `${s.label}: ${s.count}`).join(' · ')}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Measured feature statistics of the dataset */}
          {data?.reference_statistics?.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <span className="tech-label">Measured dataset statistics</span>
                <span className="tech-value">Aggregated, not machine-specific</span>
              </div>
              <table className="w-full text-left text-xs">
                <thead className="bg-em-panelDeep">
                  <tr>
                    {['Metric', 'Unit', 'Minimum', 'Mean', 'Maximum'].map((h) => (
                      <th key={h} className="tech-label px-3 py-2 font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-em-line">
                  {data.reference_statistics.map((s) => (
                    <tr key={s.field}>
                      <td className="px-3 py-2 text-em-graphite">{s.label}</td>
                      <td className="px-3 py-2 text-em-steel">{s.unit}</td>
                      <td className="px-3 py-2 font-mono tnum text-em-steel">{s.min}</td>
                      <td className="px-3 py-2 font-mono tnum font-semibold text-em-graphite">{s.mean}</td>
                      <td className="px-3 py-2 font-mono tnum text-em-steel">{s.max}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
