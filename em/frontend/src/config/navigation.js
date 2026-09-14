import {
  Wrench,
  Truck,
  Layers,
  BookOpen,
  FileText,
  Activity,
  Award,
  Settings,
} from 'lucide-react';

/**
 * Role-scoped navigation.
 *
 * A field technician gets a deliberately narrow workstation: diagnose a machine
 * and look up its history. Retrieval internals, index state, corpora and model
 * administration are engineering/administrative concerns and are not shown.
 */
export const ROLES = { TECHNICIAN: 'TECHNICIAN', ENGINEER: 'ENGINEER', ADMIN: 'ADMIN' };

const DIAGNOSE = { to: '/diagnose', label: 'Diagnose', icon: Wrench };
const MACHINES = { to: '/machines', label: 'Machines', icon: Truck };
const MEMORY = { to: '/engineering-memory', label: 'Engineering Memory', icon: Layers };
const CASES = { to: '/cases', label: 'Historical Cases', icon: BookOpen };
const EVIDENCE = { to: '/evidence', label: 'Evidence / Manuals', icon: FileText };
const SENSORS = { to: '/sensors', label: 'Condition Analysis', icon: Activity };
const BENCHMARK = { to: '/benchmark', label: 'Benchmark', icon: Award };
const ADMIN = { to: '/admin', label: 'Administration', icon: Settings };

export const NAV_BY_ROLE = {
  [ROLES.TECHNICIAN]: [DIAGNOSE, MACHINES],
  [ROLES.ENGINEER]: [DIAGNOSE, MACHINES, MEMORY, CASES, EVIDENCE, SENSORS, BENCHMARK],
  [ROLES.ADMIN]: [DIAGNOSE, MACHINES, MEMORY, CASES, EVIDENCE, SENSORS, BENCHMARK, ADMIN],
};

export const ACCESS_BY_ROLE = {
  [ROLES.TECHNICIAN]: ['/diagnose', '/machines'],
  [ROLES.ENGINEER]: ['/diagnose', '/machines', '/engineering-memory', '/cases', '/evidence', '/sensors', '/benchmark'],
  [ROLES.ADMIN]: ['/diagnose', '/machines', '/engineering-memory', '/cases', '/evidence', '/sensors', '/benchmark', '/admin'],
};

/** Landing route once an operator is signed in. */
export const HOME_BY_ROLE = {
  [ROLES.TECHNICIAN]: '/diagnose',
  [ROLES.ENGINEER]: '/diagnose',
  [ROLES.ADMIN]: '/admin',
};

export const canAccess = (role, path) => {
  const allowed = ACCESS_BY_ROLE[role];
  if (!allowed) return false;
  return allowed.some((base) => path === base || path.startsWith(`${base}/`));
};

export const navFor = (role) => NAV_BY_ROLE[role] || [];
