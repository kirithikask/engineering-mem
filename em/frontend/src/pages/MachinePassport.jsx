import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  BookOpen,
  ClipboardList,
  FileText,
  Gauge,
  QrCode,
  Radar,
  Settings2,
  Truck,
  Wrench,
} from 'lucide-react';
import api from '../services/api';
import MachineScene from '../components/3d/MachineScene';
import { DemoChip, EmptyState, Notice, QualityChip } from '../components/common/Evidence';
import { formatHours, orNotRecorded } from '../utils/format';

const TABS = [
  { key: 'overview', label: 'Overview', Icon: Truck },
  { key: 'failures', label: 'Failures', Icon: AlertTriangle },
  { key: 'maintenance', label: 'Maintenance', Icon: Wrench },
  { key: 'documents', label: 'Documents', Icon: FileText },
  { key: 'components', label: 'Components', Icon: Settings2 },
  { key: 'investigations', label: 'Investigations', Icon: Radar },
];

function Field({ label, value }) {
  return (
    <div className="border-b border-em-lineSoft py-1.5 last:border-b-0">
      <span className="tech-label block">{label}</span>
      <span className="block text-xs text-em-graphite">{value}</span>
    </div>
  );
}

export default function MachinePassport() {
  const { machineId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    api
      .get(`/machines/${machineId}/passport`)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err) => setError(err?.detail || 'Machine passport could not be loaded.'));
  }, [machineId]);

  const scan = async () => {
    setScanning(true);
    try {
      const res = await api.post(`/machines/${machineId}/scan`, {});
      setData((prev) => ({ ...(prev || {}), qr: res.qr || prev?.qr }));
    } catch (err) {
      setError(err?.detail || 'Machine access code could not be created.');
    } finally {
      setScanning(false);
    }
  };

  if (error) {
    return (
      <Notice tone="fault" title="Passport unavailable">
        {error}
      </Notice>
    );
  }
  if (!data?.machine) return <p className="text-xs text-em-steel">Loading machine passport…</p>;

  const { machine, qr, failure_history: failures, repair_history: repairs, investigations, documents, components, sensor_history: sensors, maintenance_schedule: schedule, subsystem_history: subsystems } = data;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="panel lg:col-span-8">
          <div className="flex flex-wrap items-start justify-between gap-4 p-4">
            <div>
              <p className="font-mono text-2xl font-bold tracking-tight text-em-graphite">{machine.machine_id}</p>
              <p className="mt-1 text-sm text-em-steel">
                {orNotRecorded(machine.machine_model)} · {orNotRecorded(machine.machine_type)} · {orNotRecorded(machine.manufacturer)}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={`chip-${machine.status === 'Operational' ? 'success' : 'amber'}`}>{machine.status}</span>
                <span className="chip-neutral">{formatHours(machine.operating_hours)} operating hours</span>
                <span className="chip-navy">last maintenance {orNotRecorded(machine.last_maintenance)}</span>
                <DemoChip show={(failures || []).some((row) => String(row.source_type || '').includes('demo'))} />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Link to={`/investigations`} className="btn-dark">
                <Radar className="h-3.5 w-3.5" />
                Open investigations ({(data.open_investigations || []).length})
              </Link>
              <button className="btn-outline" onClick={scan} disabled={scanning}>
                <QrCode className="h-3.5 w-3.5" />
                {scanning ? 'Reading code…' : 'Scan machine access code'}
              </button>
            </div>
          </div>
          <MachineScene
            machineLabel={`${machine.machine_id} reference assembly`}
            machineState={(data.open_investigations || []).length ? 'faulted' : 'normal'}
            className="h-72 w-full"
            autoRotate
          />
        </div>

        <div className="panel lg:col-span-4">
          <div className="panel-head">
            <span className="tech-label flex items-center gap-2">
              <QrCode className="h-3.5 w-3.5 text-em-steel" />
              Machine access code
            </span>
            <span className="tech-value">{qr?.scan_count ?? 0} scans</span>
          </div>
          <div className="space-y-3 p-3.5">
            {qr?.image_data_uri ? (
              <img src={qr.image_data_uri} alt={`QR code for ${machine.machine_id}`} className="mx-auto h-44 w-44 border border-em-line bg-white p-2" />
            ) : (
              <EmptyState title="QR image unavailable" detail="The local QR generator did not produce an image." />
            )}
            <p className="break-all font-mono text-2xs text-em-steel">{qr?.target_url}</p>
            <p className="text-2xs leading-relaxed text-em-muted">
              Generated locally with the {qr?.generator}. Scanning it resolves through the API to this machine id and opens
              the passport — the token is stored in the machine_qr_tokens table.
            </p>
            <div>
              <Field label="Open investigations" value={(data.open_investigations || []).length} />
              <Field label="Recorded failures" value={(failures || []).length} />
              <Field label="Repair attempts recorded" value={(repairs || []).length} />
              <Field
                label="Repair success rate"
                value={
                  data.repair_success_rate
                    ? `${(data.repair_success_rate.rate * 100).toFixed(0)}% of ${data.repair_success_rate.recorded_attempts} attempts`
                    : 'no attempts recorded'
                }
              />
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="flex flex-wrap items-center gap-0 border-b border-em-line px-2">
          {TABS.map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-3 py-2.5 text-2xs font-semibold uppercase tracking-label ${
                tab === key ? 'text-em-navy' : 'text-em-steel hover:text-em-graphite'
              }`}
            >
              <Icon className={`h-3.5 w-3.5 ${tab === key ? 'text-em-amber' : 'text-em-muted'}`} />
              {label}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div className="grid grid-cols-1 gap-4 p-3.5 lg:grid-cols-3">
            <div>
              <p className="tech-label">Machine record</p>
              <Field label="Manufacturer" value={orNotRecorded(machine.manufacturer)} />
              <Field label="Type" value={orNotRecorded(machine.machine_type)} />
              <Field label="Model" value={orNotRecorded(machine.machine_model)} />
              <Field label="Operating hours" value={formatHours(machine.operating_hours)} />
            </div>
            <div>
              <p className="tech-label">Subsystem history</p>
              {(subsystems || []).length === 0 && <p className="text-2xs text-em-muted">No case history recorded for this machine.</p>}
              {(subsystems || []).map((entry) => (
                <div key={entry.subsystem} className="mt-1 border border-em-line p-2">
                  <p className="text-2xs font-semibold text-em-graphite">
                    {entry.subsystem} — {entry.cases} case(s)
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {entry.components.slice(0, 4).map((component) => (
                      <span key={component.component} className="chip-neutral">
                        {component.component} ({component.cases})
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div>
              <p className="tech-label">Maintenance schedule</p>
              <Field label="Records used" value={schedule?.records_used ?? 0} />
              <Field
                label="Average interval"
                value={schedule?.average_interval_hours ? `${schedule.average_interval_hours} h` : 'not derivable'}
              />
              <p className="mt-1 text-2xs leading-relaxed text-em-muted">{schedule?.note}</p>
            </div>
          </div>
        )}

        {tab === 'failures' && (
          <ul className="divide-y divide-em-line">
            {(failures || []).map((row) => (
              <li key={row.case_id} className="px-3.5 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-2xs font-bold text-em-graphite">{row.case_id}</span>
                  <span className="chip-navy">{row.component}</span>
                  <span className="chip-neutral">{row.failure_mode}</span>
                  <DemoChip show={String(row.source_type || '').includes('demo')} />
                  <span className="ml-auto font-mono text-2xs text-em-muted">{row.operating_hours ? `${row.operating_hours} h` : ''}</span>
                </div>
                <p className="mt-1 text-2xs text-em-steel">Symptom: {row.symptom}</p>
                <p className="text-2xs text-em-steel">Inspection: {row.inspection_finding}</p>
                <p className="text-2xs text-em-steel">Repair: {row.repair_action} → {row.outcome}</p>
              </li>
            ))}
            {(failures || []).length === 0 && (
              <li className="p-4"><EmptyState title="No failure history" detail="No maintenance cases recorded for this machine." /></li>
            )}
          </ul>
        )}

        {tab === 'maintenance' && (
          <ul className="divide-y divide-em-line">
            {(repairs || []).map((row) => (
              <li key={row.attempt_id} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
                <span className="font-mono text-2xs text-em-muted">{row.attempt_id}</span>
                <span className="min-w-0 flex-1 text-2xs text-em-graphite">{row.action_taken}</span>
                <span className="chip-neutral">{row.component}</span>
                <span className={`chip-${row.was_successful ? 'success' : 'fault'}`}>{row.result}</span>
                <span className="font-mono text-2xs text-em-muted">{row.created_at}</span>
              </li>
            ))}
            {(repairs || []).length === 0 && (
              <li className="p-4">
                <EmptyState title="No repair attempts recorded" detail="Attempts recorded in investigations appear here, including failed ones." />
              </li>
            )}
          </ul>
        )}

        {tab === 'documents' && (
          <ul className="divide-y divide-em-line">
            {(documents || []).map((row) => (
              <li key={`${row.document_id}-${row.revision}`} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
                <BookOpen className="h-3.5 w-3.5 text-em-steel" />
                <span className="min-w-0 flex-1 truncate text-2xs text-em-graphite">{row.document_name}</span>
                <span className="chip-neutral">{row.document_type}</span>
                {row.revision && <span className="chip-navy">rev {row.revision}</span>}
                <span className={`chip-${row.version_status === 'CURRENT' || row.version_status === 'APPROVED' ? 'success' : row.version_status === 'SUPERSEDED' ? 'fault' : 'amber'}`}>
                  {(row.version_status || row.status || '').toLowerCase()}
                </span>
                {row.extraction_confidence > 0 && (
                  <span className="font-mono text-2xs text-em-muted tnum">confidence {(row.extraction_confidence * 100).toFixed(0)}%</span>
                )}
              </li>
            ))}
            {(documents || []).length === 0 && (
              <li className="p-4"><EmptyState title="No documents indexed" detail="Upload manuals and service bulletins from the ingestion centre." /></li>
            )}
          </ul>
        )}

        {tab === 'components' && (
          <div className="grid grid-cols-1 gap-2 p-3.5 md:grid-cols-2">
            {(components || []).map((row) => (
              <div key={row.component_id} className="border border-em-line p-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-em-graphite">{row.component_name}</span>
                  <span className="chip-neutral">{row.subsystem}</span>
                </div>
                <p className="mt-1 text-2xs text-em-steel">{row.description}</p>
                <p className="mt-1 font-mono text-2xs text-em-muted">3D reference id: {row.mesh_name || 'not mapped'}</p>
              </div>
            ))}
            {(components || []).length === 0 && <EmptyState title="No components registered" />}
          </div>
        )}

        {tab === 'investigations' && (
          <ul className="divide-y divide-em-line">
            {(investigations || []).map((row) => (
              <li key={row.investigation_id}>
                <Link to={`/investigations/${row.investigation_id}`} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5 hover:bg-em-paper">
                  <span className="font-mono text-2xs font-bold text-em-navy">{row.investigation_id}</span>
                  <span className="min-w-0 flex-1 truncate text-2xs text-em-graphite">{row.title}</span>
                  {row.knowledge_id && <span className="chip-success">knowledge {row.knowledge_id}</span>}
                  <span className="chip-neutral">{row.status}</span>
                </Link>
              </li>
            ))}
            {(investigations || []).length === 0 && (
              <li className="p-4">
                <EmptyState
                  title="No investigations for this machine"
                  detail="Start one from the investigations page to begin retrieving evidence for a reported fault."
                />
              </li>
            )}
          </ul>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="tech-label flex items-center gap-2">
            <Gauge className="h-3.5 w-3.5 text-em-steel" />
            Condition monitoring
          </span>
          <span className="tech-value">{sensors?.length ?? 0} recorded cycles</span>
        </div>
        <div className="p-3.5">
          <Notice tone="warning" title="Data provenance">
            {data.sensor_source_label}
          </Notice>
          {(sensors || []).length > 0 && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-2xs">
                <thead>
                  <tr className="border-b border-em-line text-left">
                    {['timestamp', 'ps1', 'ps2', 'ps3', 'ts1', 'ts2', 'cooler', 'valve', 'pump leakage', 'accumulator'].map((header) => (
                      <th key={header} className="py-1.5 pr-3 font-semibold uppercase tracking-label text-em-muted">{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="font-mono tnum">
                  {sensors.slice(0, 8).map((row) => (
                    <tr key={row.record_id} className="border-b border-em-lineSoft">
                      <td className="py-1 pr-3">{row.timestamp}</td>
                      <td className="pr-3">{row.ps1_mean?.toFixed?.(1) ?? row.ps1_mean}</td>
                      <td className="pr-3">{row.ps2_mean?.toFixed?.(1) ?? row.ps2_mean}</td>
                      <td className="pr-3">{row.ps3_mean?.toFixed?.(1) ?? row.ps3_mean}</td>
                      <td className="pr-3">{row.ts1_mean?.toFixed?.(1) ?? row.ts1_mean}</td>
                      <td className="pr-3">{row.ts2_mean?.toFixed?.(1) ?? row.ts2_mean}</td>
                      <td className="pr-3">{row.cooler_condition}</td>
                      <td className="pr-3">{row.valve_condition}</td>
                      <td className="pr-3">{row.pump_leakage}</td>
                      <td className="pr-3">{row.accumulator_pressure}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3">
            <p className="tech-label">Knowledge recorded for this machine</p>
            {(data.knowledge || []).length === 0 && (
              <p className="text-2xs text-em-muted">No approved engineering memory is linked to this machine yet.</p>
            )}
            {(data.knowledge || []).map((row) => (
              <div key={row.knowledge_id} className="mt-1 flex items-center gap-2 border border-em-line px-2 py-1.5">
                <span className="font-mono text-2xs text-em-navy">{row.knowledge_id}</span>
                <span className="min-w-0 flex-1 truncate text-2xs text-em-graphite">{row.title}</span>
                <QualityChip level={row.quality_level} compact />
                <span className="chip-neutral">{row.status}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button className="btn-outline" onClick={() => navigate(`/diagnose?machine=${machine.machine_id}`)}>
              <ClipboardList className="h-3.5 w-3.5" />
              One-shot diagnosis (existing workstation)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
