import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { HOME_BY_ROLE, canAccess } from './config/navigation';

import AppShell from './components/layout/AppShell';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Diagnose from './pages/Diagnose';
import Machines from './pages/Machines';
import MachineDetail from './pages/MachineDetail';
import EngineeringMemory from './pages/EngineeringMemory';
import HistoricalCases from './pages/HistoricalCases';
import EvidenceDocuments from './pages/EvidenceDocuments';
import SensorAnalysis from './pages/SensorAnalysis';
import Benchmark from './pages/Benchmark';
import Admin from './pages/Admin';

// Extension modules (ADDITIVE): investigation memory, machine passport, multimodal
// ingestion, knowledge lifecycle, vector database, data quality and audit trail.
import Investigations from './pages/Investigations';
import Investigation from './pages/Investigation';
import PassportIndex from './pages/PassportIndex';
import MachinePassport from './pages/MachinePassport';
import ScanLanding from './pages/ScanLanding';
import IngestionCenter from './pages/IngestionCenter';
import ReviewQueue from './pages/ReviewQueue';
import KnowledgeCenter from './pages/KnowledgeCenter';
import VectorDatabase from './pages/VectorDatabase';
import DataQuality from './pages/DataQuality';
import AuditLog from './pages/AuditLog';

/** Entry route: public landing, or the operator's own home once signed in. */
function LandingOrHome() {
  const { user } = useAuth();
  if (user) {
    return <Navigate to={HOME_BY_ROLE[user.role] || '/diagnose'} replace />;
  }
  return <Landing />;
}

/**
 * Guarded workstation page.
 *
 * Requires a session, and requires the operator's role to actually own the
 * route. A technician navigating to an engineering or administration route is
 * returned to their own workstation rather than shown the page.
 */
function Protected({ children }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (!canAccess(user.role, location.pathname)) {
    return (
      <Navigate
        to={HOME_BY_ROLE[user.role] || '/diagnose'}
        replace
        state={{ denied: location.pathname }}
      />
    );
  }
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingOrHome />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          <Route path="/diagnose" element={<Protected><Diagnose /></Protected>} />
          <Route path="/machines" element={<Protected><Machines /></Protected>} />
          <Route path="/machines/:machineId" element={<Protected><MachineDetail /></Protected>} />
          <Route path="/engineering-memory" element={<Protected><EngineeringMemory /></Protected>} />
          <Route path="/cases" element={<Protected><HistoricalCases /></Protected>} />
          <Route path="/evidence" element={<Protected><EvidenceDocuments /></Protected>} />
          <Route path="/sensors" element={<Protected><SensorAnalysis /></Protected>} />
          <Route path="/benchmark" element={<Protected><Benchmark /></Protected>} />
          <Route path="/admin" element={<Protected><Admin /></Protected>} />

          {/* Extension routes. Existing routes above are untouched. */}
          <Route path="/investigations" element={<Protected><Investigations /></Protected>} />
          <Route path="/investigations/:investigationId" element={<Protected><Investigation /></Protected>} />
          <Route path="/passport" element={<Protected><PassportIndex /></Protected>} />
          <Route path="/machines/:machineId/passport" element={<Protected><MachinePassport /></Protected>} />
          <Route path="/knowledge" element={<Protected><KnowledgeCenter /></Protected>} />
          <Route path="/review" element={<Protected><ReviewQueue /></Protected>} />
          <Route path="/ingestion" element={<Protected><IngestionCenter /></Protected>} />
          <Route path="/vector-db" element={<Protected><VectorDatabase /></Protected>} />
          <Route path="/data-quality" element={<Protected><DataQuality /></Protected>} />
          <Route path="/audit" element={<Protected><AuditLog /></Protected>} />

          {/* Public machine-code landing: a scanned QR tag resolves to a real
              machine id here. Sign-in is still required for the workstation. */}
          <Route path="/m/:token" element={<ScanLanding />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
