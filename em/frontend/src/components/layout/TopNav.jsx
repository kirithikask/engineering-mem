import React, { useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { LogOut, ChevronDown, HardHat, Wrench } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { navFor } from '../../config/navigation';
import useSystemStatus from '../../hooks/useSystemStatus';

function StatusPip({ ok, label, detail }) {
  return (
    <div className="flex items-center gap-1.5" title={detail}>
      <span
        className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-em-success' : 'bg-em-fault'}`}
        aria-hidden="true"
      />
      <span className="text-2xs font-semibold uppercase tracking-label text-em-steel">{label}</span>
    </div>
  );
}

export default function TopNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { status, databaseOnline, aiEngineOnline, retrievalOnline, vectorCount } = useSystemStatus();

  const items = navFor(user?.role);

  const handleSignOut = () => {
    logout();
    navigate('/');
  };

  return (
    <header className="sticky top-0 z-30 bg-em-surface border-b border-em-line">
      {/* Brand + platform identity */}
      <div className="flex items-stretch justify-between gap-4 px-4 lg:px-6 h-14">
        <Link to="/" className="flex items-center gap-3 min-w-0">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center bg-em-navy text-em-amber font-mono text-xs font-bold">
            EM
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold uppercase tracking-[0.18em] text-em-graphite">
              Engineering Memory
            </span>
            <span className="block truncate text-2xs uppercase tracking-label text-em-muted">
              Industrial Diagnosis Workstation
            </span>
          </span>
        </Link>

        <div className="flex items-center gap-3 lg:gap-5">
          {/* Real platform state, reported by the backend */}
          <div className="hidden xl:flex items-center gap-4 border-r border-em-line pr-5">
            <StatusPip
              ok={databaseOnline}
              label={status?.database?.includes('MySQL') ? 'MySQL' : 'Local DB'}
              detail={status?.database || 'Database status unknown'}
            />
            <StatusPip
              ok={retrievalOnline}
              label={vectorCount ? `Index ${vectorCount.toLocaleString()}` : 'Index'}
              detail="Engineering memory retrieval index"
            />
            <StatusPip ok={aiEngineOnline} label="Local AI" detail="Qwen 3:4B via Ollama" />
            <StatusPip ok label="Offline" detail="No cloud services are used during diagnosis" />
          </div>

          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 border border-em-line px-2.5 py-1.5 text-left hover:border-em-steel transition-colors"
            >
              <HardHat className="h-3.5 w-3.5 text-em-amber" />
              <span className="hidden sm:block">
                <span className="block text-2xs font-semibold uppercase tracking-wider text-em-graphite">
                  {user?.full_name || user?.username}
                </span>
                <span className="block text-2xs uppercase tracking-label text-em-muted">{user?.role}</span>
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-em-muted" />
            </button>

            {menuOpen && (
              <div className="absolute right-0 mt-1 w-52 panel shadow-lift py-1">
                <div className="px-3 py-2 border-b border-em-line">
                  <span className="tech-label block">Operator</span>
                  <span className="text-xs text-em-graphite">{user?.username}</span>
                </div>
                <button
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2 px-3 py-2 text-xs text-em-steel hover:bg-em-panel hover:text-em-graphite"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Role-scoped command bar */}
      <nav className="flex items-center gap-0 overflow-x-auto border-t border-em-lineSoft px-2 lg:px-4">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `relative flex shrink-0 items-center gap-2 px-3 lg:px-4 py-2.5 text-2xs font-semibold uppercase tracking-label transition-colors ${
                  isActive ? 'text-em-navy' : 'text-em-steel hover:text-em-graphite'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`h-3.5 w-3.5 ${isActive ? 'text-em-amber' : 'text-em-muted'}`} />
                  <span>{item.label}</span>
                  {isActive && <span className="absolute inset-x-2 bottom-0 h-0.5 bg-em-amber" />}
                </>
              )}
            </NavLink>
          );
        })}

        <Link
          to="/diagnose"
          className="ml-auto hidden shrink-0 items-center gap-1.5 px-3 py-2.5 text-2xs font-semibold uppercase tracking-label text-em-amberDark hover:text-em-graphite md:flex"
        >
          <Wrench className="h-3.5 w-3.5" />
          New diagnosis
        </Link>
      </nav>
    </header>
  );
}
