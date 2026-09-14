import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { HOME_BY_ROLE } from '../config/navigation';
import ExcavatorBlueprint from '../components/landing/ExcavatorBlueprint';

const ROLE_OPTIONS = [
  {
    value: 'TECHNICIAN',
    title: 'Field technician',
    detail: 'Diagnosis workstation and machine history.',
  },
  {
    value: 'ENGINEER',
    title: 'Maintenance engineer',
    detail: 'Adds engineering memory, evidence and condition analysis.',
  },
  {
    value: 'ADMIN',
    title: 'Administrator',
    detail: 'Full platform access including ingestion and operators.',
  },
];

export default function Signup() {
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    username: '',
    password: '',
    role: 'TECHNICIAN',
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await signup(form);
      navigate(HOME_BY_ROLE[user.role] || '/diagnose', { replace: true });
    } catch (err) {
      const detail = err?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Account could not be created. Confirm the platform services are running and try again.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
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
            Passwords are stored only as salted PBKDF2 hashes. Credentials never leave this host.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center bg-em-paper px-5 py-10">
        <div className="w-full max-w-md">
          <span className="tech-label">New operator</span>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-em-graphite">Create account</h1>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="fullName" className="tech-label mb-1.5 block">
                  Full name
                </label>
                <input
                  id="fullName"
                  type="text"
                  value={form.fullName}
                  onChange={update('fullName')}
                  className="field"
                  required
                />
              </div>
              <div>
                <label htmlFor="username" className="tech-label mb-1.5 block">
                  Operator ID
                </label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={form.username}
                  onChange={update('username')}
                  className="field"
                  placeholder="3-32 characters"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="email" className="tech-label mb-1.5 block">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={update('email')}
                className="field"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="tech-label mb-1.5 block">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={update('password')}
                className="field"
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
            </div>

            <fieldset>
              <legend className="tech-label mb-2">Role</legend>
              <div className="space-y-2">
                {ROLE_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={`flex cursor-pointer items-start gap-3 border p-3 transition-colors ${
                      form.role === opt.value
                        ? 'border-em-amber bg-em-amberSoft/40'
                        : 'border-em-line bg-em-surface hover:border-em-steel'
                    }`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={opt.value}
                      checked={form.role === opt.value}
                      onChange={update('role')}
                      className="mt-1 accent-[#C58B2A]"
                    />
                    <span>
                      <span className="block text-xs font-semibold uppercase tracking-wider text-em-graphite">
                        {opt.title}
                      </span>
                      <span className="mt-0.5 block text-2xs leading-relaxed text-em-steel">{opt.detail}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {error && (
              <div className="flex items-start gap-2 border-l-2 border-em-fault bg-em-faultSoft px-3 py-2">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-em-fault" />
                <p className="text-2xs leading-relaxed text-em-fault">{error}</p>
              </div>
            )}

            <button type="submit" disabled={busy} className="btn-amber w-full py-2.5">
              {busy ? 'Creating…' : 'Create account'}
              {!busy && <ArrowRight className="h-3.5 w-3.5" />}
            </button>
          </form>

          <p className="mt-5 text-2xs text-em-steel">
            Already registered?{' '}
            <Link to="/login" className="font-semibold text-em-amberDark hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
