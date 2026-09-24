"""
Next-best-inspection engine (brief §6).

The workstation never dumps a list of ten possible causes. It ranks what should be
inspected next, and for every recommendation it states why, which retrieved
evidence supports it, what finding is expected, and what history is relevant.

Two candidate sources are combined:

1. Recorded inspections from retrieved historical evidence: what technicians
   actually measured in comparable cases, quoted verbatim as the expected
   finding.
2. The workstation's own inspection catalogue — standard hydraulic extraction
   procedures per component. This is engineering procedure shipped with the
   platform, and it is labelled as such so nobody mistakes it for a retrieved
   document or for machine-specific history.

Ranking uses the effective retrieval score and the source quality level of the
evidence that names each component, and it penalises checks that the recorded
findings already cover. A previous *failed* repair attempt on the same component
does not remove a recommendation — brief §5 requires failed attempts to be shown
as historical evidence, not used to silently suppress a check.
"""

from typing import Any, Dict, List, Optional

# Standard hydraulic-extraction inspection catalogue. Each entry carries the
# component it belongs to, the engineering reason it is worthwhile, the finding
# that would confirm a problem, and the safety task key used to fetch approved
# safety procedures.
INSPECTION_CATALOG: List[Dict[str, Any]] = [
    {
        "component": "hydraulic pump",
        "inspection": "Pump delivery and main relief pressure test at operating temperature (50-60 °C)",
        "expected": "Delivery pressure below specification, or a pressure that falls as oil temperature rises.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "hydraulic pump",
        "inspection": "Pump case drain flow measurement (internal leakage check)",
        "expected": "Case drain flow above the manufacturer's limit, indicating internal leakage past the rotating group.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "hydraulic oil",
        "inspection": "Hydraulic oil temperature measurement after sustained load (20+ minutes)",
        "expected": "Oil temperature well above the normal working band for the ambient conditions.",
        "safety_task": "temperature measurement",
    },
    {
        "component": "hydraulic oil",
        "inspection": "Hydraulic oil sample: viscosity, particle count and aeration",
        "expected": "Viscosity out of grade, high particle count, or entrained air in the sample.",
        "safety_task": "oil sampling",
    },
    {
        "component": "hydraulic filter",
        "inspection": "Hydraulic filter element inspection and bypass/restriction check",
        "expected": "Element loaded with contamination, collapsed pleats, or a filter in bypass.",
        "safety_task": "filter service",
    },
    {
        "component": "main control valve",
        "inspection": "Control valve spool movement and centering check at each function",
        "expected": "Spool not returning to neutral, sticking, or a restricted stroke.",
        "safety_task": "control valve service",
    },
    {
        "component": "main control valve",
        "inspection": "Service-port pressure check per function to locate an internal bypass",
        "expected": "One function measurably weaker than the others at the same relief setting.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "oil cooler",
        "inspection": "Cooler inlet/outlet temperature differential and core restriction check",
        "expected": "Little temperature drop across the cooler, or a blocked core and degraded airflow.",
        "safety_task": "cooling system service",
    },
    {
        "component": "accumulator",
        "inspection": "Accumulator precharge pressure test",
        "expected": "Precharge pressure below specification or zero (lost gas charge).",
        "safety_task": "accumulator service",
    },
    {
        "component": "boom cylinder",
        "inspection": "Boom cylinder drift (hold) test with the attachment raised and the engine off",
        "expected": "Cylinder rod creeping down faster than the hold specification.",
        "safety_task": "cylinder service",
    },
    {
        "component": "arm cylinder",
        "inspection": "Arm cylinder drift (hold) test under load",
        "expected": "Rod drift or an unbalanced circuit on the arm function.",
        "safety_task": "cylinder service",
    },
    {
        "component": "bucket cylinder",
        "inspection": "Bucket cylinder drift and rod seal inspection",
        "expected": "Rod drift, weeping at the wiper seal, or a scored rod surface.",
        "safety_task": "cylinder service",
    },
    {
        "component": "pilot system",
        "inspection": "Pilot pressure measurement at idle and at full throttle",
        "expected": "Pilot pressure outside specification, causing delayed or weak control response.",
        "safety_task": "pilot circuit test",
    },
    {
        "component": "pilot system",
        "inspection": "Pilot filter and pressure-reducing valve inspection",
        "expected": "Restricted pilot filter or a worn reducing valve.",
        "safety_task": "pilot circuit test",
    },
    {
        "component": "swing motor",
        "inspection": "Swing motor case drain flow measurement",
        "expected": "High case drain flow indicating internal leakage.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "travel motor",
        "inspection": "Travel motor case drain flow and brake release pressure check",
        "expected": "High case drain flow or incorrect brake release pressure.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "relief valve",
        "inspection": "Main relief valve set pressure verification at operating temperature",
        "expected": "Relief opening below specification, limiting all functions.",
        "safety_task": "hydraulic pressure test",
    },
    {
        "component": "hydraulic line",
        "inspection": "Hose, fitting and tube inspection for leakage, kinks and swelling under pressure",
        "expected": "Weeping fittings, a hose approaching failure, or a restricted line.",
        "safety_task": "hydraulic pressure test",
    },
]

# Components that describe a subsystem rather than an actionable item.
GENERIC_COMPONENTS = {"hydraulic system", "", "unknown"}


def _known_component(name: Optional[str]) -> Optional[str]:
    value = (name or "").strip().lower()
    return None if value in GENERIC_COMPONENTS else value


class NextInspectionEngine:
    def rank(
        self,
        *,
        evidence: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        failed_attempts: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        checked_terms = self._checked_terms(findings)
        failed_terms = self._checked_terms(failed_attempts, key="action_taken")

        candidates: Dict[str, Dict[str, Any]] = {}

        # --- Source 1: inspections recorded in comparable history ----------
        for item in evidence:
            if item.get("evidence_type") != "case":
                continue
            recorded = (item.get("inspection") or "").strip()
            if not recorded:
                continue
            component = _known_component(item.get("component")) or "hydraulic system"
            key = f"history::{item.get('id')}::{recorded[:60]}"
            candidates[key] = {
                "key": key,
                "inspection": recorded,
                "component": component,
                "expected": recorded,
                "origin": "recorded_historical_inspection",
                "origin_label": f"Recorded inspection in {item.get('id')}",
                "score": float(item.get("effective_score") or 0.0),
                "supporting_evidence": [self._evidence_ref(item)],
                "historical_cases": [item.get("id")],
                "matched_terms": self._matched(checked_terms, f"{component} {recorded}"),
                "failed_attempt_overlap": self._matched(failed_terms, f"{component} {recorded}"),
            }

        # --- Source 2: workstation inspection catalogue --------------------
        by_component: Dict[str, List[Dict[str, Any]]] = {}
        for item in evidence:
            component = _known_component(item.get("component"))
            if component:
                by_component.setdefault(component, []).append(item)

        for entry in INSPECTION_CATALOG:
            component = entry["component"]
            supporters = by_component.get(component, [])
            support_score = sum(float(item.get("effective_score") or 0.0) for item in supporters)
            if not supporters:
                continue
            key = f"catalog::{component}::{entry['inspection']}"
            candidates[key] = {
                "key": key,
                "inspection": entry["inspection"],
                "component": component,
                "expected": entry["expected"],
                "origin": "workstation_inspection_catalog",
                "origin_label": "Standard hydraulic inspection procedure (workstation catalogue)",
                "score": round(support_score, 4),
                "supporting_evidence": [self._evidence_ref(item) for item in supporters[:3]],
                "historical_cases": [item.get("id") for item in supporters if item.get("evidence_type") == "case"],
                "matched_terms": self._matched(checked_terms, entry["inspection"]),
                "failed_attempt_overlap": self._matched(failed_terms, entry["inspection"]),
                "safety_task": entry.get("safety_task"),
            }

        ranked = list(candidates.values())
        for item in ranked:
            # Already-checked inspections are pushed down but not hidden: the
            # operator may need to re-check after a change.
            penalty = 0.45 if item["matched_terms"] else 1.0
            item["rank_score"] = round(item["score"] * penalty, 4)
            item["already_checked"] = bool(item["matched_terms"])
            item["why"] = self._why(item, by_component)

        ranked.sort(key=lambda item: item["rank_score"], reverse=True)
        top = ranked[: max(1, limit)]

        if not top:
            return [
                {
                    "key": "baseline",
                    "inspection": procedure["inspection"],
                    "component": procedure["component"],
                    "expected": procedure["expected"],
                    "origin": "workstation_inspection_catalog",
                    "origin_label": "Standard hydraulic inspection procedure (workstation catalogue)",
                    "score": 0.0,
                    "rank_score": 0.0,
                    "supporting_evidence": [],
                    "historical_cases": [],
                    "already_checked": False,
                    "failed_attempt_overlap": [],
                    "safety_task": procedure.get("safety_task"),
                    "why": (
                        "No retrieved evidence supports a more specific inspection for the recorded symptom set, "
                        "so these are the standard first-line hydraulic checks."
                    ),
                }
                for procedure in INSPECTION_CATALOG
                if procedure["component"] in ("hydraulic oil", "hydraulic filter", "hydraulic pump")
            ][:3]
        return top

    # ------------------------------------------------------------------
    def _evidence_ref(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": item.get("id"),
            "title": item.get("title") or item.get("document_name"),
            "similarity": item.get("similarity"),
            "effective_score": item.get("effective_score"),
            "quality_level": item.get("quality_level"),
            "document_status": item.get("document_status"),
            "revision": item.get("revision"),
            "page_number": item.get("page_number"),
            "demo_data": item.get("demo_data"),
        }

    def _why(self, item: Dict[str, Any], by_component: Dict[str, List[Dict[str, Any]]]) -> str:
        supporters = item.get("supporting_evidence") or []
        if not item.get("historical_cases"):
            base = (
                f"{len(supporters)} retrieved source(s) point at the {item['component']} for the recorded symptoms, "
                "and this is the procedure that isolates it."
            )
        else:
            cases = ", ".join(str(c) for c in item["historical_cases"][:3] if c)
            base = f"{len(supporters)} retrieved source(s) associate this with the {item['component']}"
            if cases:
                base += f" (historical cases: {cases})"
            base += "."
        if item.get("already_checked"):
            base += (
                " Findings already recorded cover this check, so it is ranked lower — re-check only if the "
                "condition may have changed."
            )
        if item.get("failed_attempt_overlap"):
            base += (
                " A previous attempt on this item did not resolve the symptom; treat that as historical evidence, "
                "not as proof the item is healthy."
            )
        return base

    def _checked_terms(self, rows: List[Dict[str, Any]], key: str = "title") -> List[str]:
        terms: List[str] = []
        for row in rows or []:
            text = " ".join(
                str(row.get(field) or "")
                for field in (key, "component", "detail", "value", "unit")
            ).lower()
            for word in ("pump", "filter", "oil", "cooler", "valve", "accumulator", "pilot", "cylinder",
                         "pressure", "temperature", "leak", "swing", "travel", "hose", "relief"):
                if word in text:
                    terms.append(word)
        return sorted(set(terms))

    def _matched(self, terms: List[str], text: str) -> List[str]:
        blob = str(text).lower()
        return [term for term in terms if term in blob]


next_inspection_engine = NextInspectionEngine()
