import {
  Wrench,
  Truck,
  Layers,
  BookOpen,
  FileText,
  Activity,
  Award,
  Settings,
  Radar,
  QrCode,
  Upload,
  BookMarked,
  ClipboardCheck,
  Database,
  Gauge,
  ScrollText,
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

// Extension modules (investigation memory, machine passport, ingestion and the
// knowledge lifecycle). Added alongside the original items so the existing
// workstations keep their exact navigation.
const INVESTIGATIONS = { to: '/investigations', label: 'Investigations', icon: Radar };
const PASSPORTS = { to: '/passport', label: 'Machine Passports', icon: QrCode };
const KNOWLEDGE = { to: '/knowledge', label: 'Knowledge Center', icon: BookMarked };
const REVIEW = { to: '/review', label: 'Review Queue', icon: ClipboardCheck };
const INGESTION = { to: '/ingestion', label: 'Ingestion', icon: Upload };
const VECTOR_DB = { to: '/vector-db', label: 'Vector Database', icon: Database };
const DATA_QUALITY = { to: '/data-quality', label: 'Data Quality', icon: Gauge };
const AUDIT = { to: '/audit', label: 'Audit Logs', icon: ScrollText };

export const NAV_BY_ROLE = {
  [ROLES.TECHNICIAN]: [DIAGNOSE, INVESTIGATIONS, MACHINES, PASSPORTS],
  [ROLES.ENGINEER]: [
    DIAGNOSE,
    INVESTIGATIONS,
    MACHINES,
    PASSPORTS,
    KNOWLEDGE,
    REVIEW,
    MEMORY,
    CASES,
    EVIDENCE,
    SENSORS,
    BENCHMARK,
  ],
  [ROLES.ADMIN]: [
    DIAGNOSE,
    INVESTIGATIONS,
    MACHINES,
    PASSPORTS,
    KNOWLEDGE,
    REVIEW,
    INGESTION,
    MEMORY,
    CASES,
    EVIDENCE,
    SENSORS,
    BENCHMARK,
    VECTOR_DB,
    DATA_QUALITY,
    AUDIT,
    ADMIN,
  ],
};

const EXTENSION_TECHNICIAN = ['/investigations', '/passport'];
const EXTENSION_ENGINEER = [...EXTENSION_TECHNICIAN, '/knowledge', '/review'];
const EXTENSION_ADMIN = [...EXTENSION_ENGINEER, '/ingestion', '/vector-db', '/data-quality', '/audit'];

export const ACCESS_BY_ROLE = {
  [ROLES.TECHNICIAN]: ['/diagnose', '/machines', ...EXTENSION_TECHNICIAN],
  [ROLES.ENGINEER]: [
    '/diagnose',
    '/machines',
    '/engineering-memory',
    '/cases',
    '/evidence',
    '/sensors',
    '/benchmark',
    ...EXTENSION_ENGINEER,
  ],
  [ROLES.ADMIN]: [
    '/diagnose',
    '/machines',
    '/engineering-memory',
    '/cases',
    '/evidence',
    '/sensors',
    '/benchmark',
    '/admin',
    ...EXTENSION_ADMIN,
  ],
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
