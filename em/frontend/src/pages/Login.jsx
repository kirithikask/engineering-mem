import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, Lock, User, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { HOME_BY_ROLE } from '../config/navigation';
import ExcavatorBlueprint from '../components/landing/ExcavatorBlueprint';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(username.trim(), password);
      const redirect = location.state?.from;
      navigate(redirect || HOME_BY_ROLE[user.role] || '/diagnose', { replace: true });
    } catch (err) {
      const detail = err?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Sign-in failed. Check the operator ID and password, and confirm the platform services are running.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      {/* Machinery side */}
      <div className="relative hidden overflow-hidden border-r border-em-line bg-em-surface lg:block">
        <div className="blueprint absolute inset-0 opacity-70" aria-hidden="true" />
        <div className="relative flex h-full flex-col justify-between p-10">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center bg-em-graphite font-mono text-xs font-bold text-em-amber">
              EM
            </span>
            <span>
              <span className="block text-sm font-bold uppercase tracking-[0.2em] text-em-graphite">
                Engineering Memory
              </span>
              <span className="block text-2xs uppercase tracking-label text-em-muted">
                Industrial Diagnosis Workstation
              </span>
            </span>
          </Link>

          <ExcavatorBlueprint className="w-full" />

          <p className="max-w-md text-2xs leading-relaxed text-em-steel">
            Runs on the local server. Diagnosis, retrieval and reasoning continue with Wi-Fi and Ethernet
            disconnected.
          </p>
        </div>
      </div>

      {/* Auth side */}
      <div className="flex items-center justify-center bg-em-paper px-5 py-10">
        <div className="w-full max-w-sm">
          <Link to="/" className="mb-6 flex items-center gap-3 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center bg-em-graphite font-mono text-2xs font-bold text-em-amber">
              EM
            </span>
            <span className="text-sm font-bold uppercase tracking-[0.2em] text-em-graphite">
              Engineering Memory
            </span>
          </Link>

          <span className="tech-label">Operator access</span>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-em-graphite">Sign in</h1>
          <p className="mt-2 text-xs leading-relaxed text-em-steel">
            Field technicians reach the diagnosis workstation and machine history. Engineering and
            administration roles reach the knowledge and system tools.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="username" className="tech-label mb-1.5 block">
                Operator ID
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-em-muted" />
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="field pl-9"
                  placeholder="e.g. technician"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="tech-label mb-1.5 block">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-em-muted" />
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="field pl-9"
                  required
                />
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 border-l-2 border-em-fault bg-em-faultSoft px-3 py-2">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-fault" />
                <p className="text-2xs leading-relaxed text-em-fault">{error}</p>
              </div>
            )}

            <button type="submit" disabled={busy} className="btn-amber w-full py-2.5">
              {busy ? 'Verifying…' : 'Sign in'}
              {!busy && <ArrowRight className="h-3.5 w-3.5" />}
            </button>
          </form>

          <p className="mt-5 text-2xs text-em-steel">
            No account?{' '}
            <Link to="/signup" className="font-semibold text-em-amberDark hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
