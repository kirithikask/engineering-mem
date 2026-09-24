import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { QrCode, Truck, Wrench } from 'lucide-react';
import api from '../services/api';
import { Notice } from '../components/common/Evidence';
import { formatHours, orNotRecorded } from '../utils/format';

/**
 * Landing route for a scanned machine code (/m/<token>).
 *
 * The token is resolved by the backend to a real machine id — a QR code that does
 * not map to a machine produces an explicit failure rather than a decorative page.
 * This route is intentionally not behind the sign-in guard so a phone can read a
 * machine tag; opening the workstation itself still requires a session.
 */
export default function ScanLanding() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get(`/machines/scan/${token}`)
      .then((res) => setData(res))
      .catch((err) => setError(err?.detail || 'This machine code did not resolve to a machine in the registry.'))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <p className="p-6 text-xs text-em-steel">Resolving machine code {token}…</p>;

  if (error) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Notice tone="fault" title="Unknown machine code">
          <span className="block font-mono">{token}</span>
          {error}
          <span className="mt-2 block">
            Register the machine access code from its passport page, or open the fleet registry.
          </span>
        </Notice>
        <div className="mt-4 flex gap-2">
          <button className="btn-outline" onClick={() => navigate('/passport')}>Fleet passports</button>
        </div>
      </div>
    );
  }

  const machine = data.machine || {};
  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      <div className="panel p-5">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center bg-em-navy">
            <QrCode className="h-6 w-6 text-em-amber" />
          </span>
          <div>
            <p className="font-mono text-xl font-bold text-em-graphite">{data.machine_id}</p>
            <p className="text-2xs uppercase tracking-label text-em-muted">machine access code resolved</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 text-2xs">
          <div className="border border-em-line p-2">
            <span className="tech-label block">Model</span>
            {orNotRecorded(machine.machine_model)}
          </div>
          <div className="border border-em-line p-2">
            <span className="tech-label block">Operating hours</span>
            {formatHours(machine.operating_hours)}
          </div>
          <div className="border border-em-line p-2">
            <span className="tech-label block">Status</span>
            {orNotRecorded(machine.status)}
          </div>
          <div className="border border-em-line p-2">
            <span className="tech-label block">Open investigations</span>
            {(data.open_investigations || []).length}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Link to={`/machines/${data.machine_id}/passport`} className="btn-amber">
            <Truck className="h-3.5 w-3.5" />
            Open machine passport
          </Link>
          <Link to={`/investigations`} className="btn-outline">
            <Wrench className="h-3.5 w-3.5" />
            Start diagnosis
          </Link>
        </div>

        {(data.recent_cases || []).length > 0 && (
          <div className="mt-4">
            <p className="tech-label">Recent recorded failures</p>
            {(data.recent_cases || []).map((row) => (
              <p key={row.case_id} className="text-2xs text-em-steel">
                <span className="font-mono text-em-navy">{row.case_id}</span> · {row.component} · {row.failure_mode}
              </p>
            ))}
          </div>
        )}
      </div>
      <p className="text-center text-2xs text-em-muted">
        This page is read-only access to the machine's basic record. Diagnosis and evidence entry require signing in.
      </p>
    </div>
  );
}
