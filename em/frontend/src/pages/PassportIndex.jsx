import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { QrCode, Truck } from 'lucide-react';
import api from '../services/api';
import { EmptyState, Notice } from '../components/common/Evidence';
import { formatHours, orNotRecorded } from '../utils/format';

/**
 * Entry point to the machine passports.
 *
 * The existing fleet page keeps its own layout; this page exists so the passport
 * (identity, QR access, subsystems, history, open investigations) is reachable
 * from the command bar without changing the fleet page.
 */
export default function PassportIndex() {
  const [machines, setMachines] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get('/machines')
      .then((res) => setMachines(res.machines || []))
      .catch(() => setError('The fleet registry could not be read.'));
  }, []);

  return (
    <div className="space-y-5">
      <Notice tone="info" title="Machine passport">
        A passport is the machine's engineering identity: real operating hours, subsystem and failure history, documents in
        scope, open investigations and a scannable access code that resolves to this machine's backend record.
      </Notice>

      {error && <Notice tone="fault" title="Unavailable">{error}</Notice>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {machines.map((machine) => (
          <Link
            key={machine.machine_id}
            to={`/machines/${machine.machine_id}/passport`}
            className="panel flex items-center gap-3 p-3.5 transition-colors hover:border-em-steel"
          >
            <span className="flex h-10 w-10 items-center justify-center bg-em-navy">
              <Truck className="h-5 w-5 text-em-amber" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-mono text-sm font-bold text-em-graphite">{machine.machine_id}</span>
              <span className="block truncate text-2xs text-em-steel">
                {orNotRecorded(machine.machine_model)} · {formatHours(machine.operating_hours)} h · {orNotRecorded(machine.status)}
              </span>
              <span className="block truncate text-2xs text-em-muted">
                last maintenance {orNotRecorded(machine.last_maintenance)}
              </span>
            </span>
            <QrCode className="h-4 w-4 shrink-0 text-em-muted" />
          </Link>
        ))}
        {machines.length === 0 && !error && (
          <div className="md:col-span-2 xl:col-span-3">
            <EmptyState title="No machines registered" detail="Seed the fleet registry before opening passports." />
          </div>
        )}
      </div>
    </div>
  );
}
