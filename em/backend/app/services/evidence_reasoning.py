"""
Evidence-grounded reasoning for investigations (brief §5, §27).

This module is ADDITIVE: the original one-shot diagnosis path
(``reasoning_service.ReasoningEngine.diagnose``) is untouched and still serves
``/api/diagnose``. What is added here is the investigation-grade reasoning pass,
which differs in three ways the brief requires:

1. Every piece of evidence handed to Qwen carries its provenance: source title,
   page/section, revision, document status, knowledge quality level and whether
   the record is demo/synthetic data.
2. Qwen is instructed to cite the evidence ids it used, and citations are then
   validated against the evidence set actually retrieved. Citations that do not
   exist are dropped and reported as ``unverified_citations`` — the model cannot
   manufacture support.
3. If the evidence is not sufficient, the model is not called at all. The caller
   receives a structured "insufficient evidence" response plus what to collect
   next, rather than a speculative cause.

The same local Ollama endpoint and the same bounded-generation settings are used,
so behaviour and latency characteristics stay consistent with the existing path.
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from backend.app.services.reasoning_service import (
    MAX_OUTPUT_TOKENS,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
    MODEL_NAME,
    extract_json_object,
)

# Evidence below this effective score is treated as background reading only and
# is not presented to the model as support for a cause.
SUPPORT_THRESHOLD = 0.40
MIN_SUPPORTING_SOURCES = 1

# Cosine similarity alone is not sufficient on a corpus of near-duplicate
# historical cases: unrelated text can score in the 0.6-0.7 band simply because
# the corpus is homogeneous. Support therefore also requires that the retrieved
# source actually shares the vocabulary of what was reported. Measured on this
# corpus, a real multi-symptom technician report overlaps a supporting case by
# 0.4-0.8 of its content terms; an unrelated/nonsense report overlaps by ~0.0.
MIN_LEXICAL_OVERLAP = 0.25

STOPWORDS = {
    "about", "after", "again", "against", "almost", "along", "also", "always", "another", "because",
    "before", "being", "between", "both", "cannot", "could", "during", "each", "every", "from",
    "fuel", "have", "having", "into", "itself", "just", "like", "made", "make", "many", "more",
    "most", "much", "must", "near", "need", "only", "other", "over", "same", "should", "some",
    "such", "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "very", "what", "when", "where", "which", "while", "with",
    "without", "would", "your", "reported", "operator", "machine", "still", "seems",
}


def _terms(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {word for word in words if len(word) > 3 and word not in STOPWORDS}


def _evidence_text(item: Dict[str, Any]) -> str:
    return " ".join(
        str(item.get(field) or "")
        for field in ("symptom", "failure_mode", "component", "inspection", "repair", "chunk_text", "title", "section_heading")
    )
MAX_EVIDENCE_IN_PROMPT = 6
MAX_EVIDENCE_CHARS = 700

DEMO_SOURCE_TYPES = {"tata_industry_demo", "synthetic", "synthetic_demo", "prototype"}


def _clip(value: Any, limit: int = MAX_EVIDENCE_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _quality_of(item: Dict[str, Any]) -> str:
    return str(item.get("quality_level") or "UNVERIFIED").upper()


def format_evidence(evidence: List[Dict[str, Any]]) -> str:
    """Render retrieved evidence with the provenance the brief requires."""
    lines: List[str] = []
    for index, item in enumerate(evidence[:MAX_EVIDENCE_IN_PROMPT], start=1):
        ref = f"E{index}"
        kind = item.get("evidence_type")
        if kind == "chunk":
            header = (
                f"[{ref}] SOURCE: {item.get('document_name')} | Page {item.get('page_number')} "
                f"| Section {item.get('section_heading') or 'n/a'} | Revision {item.get('revision') or 'n/a'} "
                f"| Document status: {item.get('document_status')} | Quality: {_quality_of(item)} "
                f"| Kind: {item.get('chunk_kind')} | Similarity {item.get('similarity')}"
            )
            body = _clip(item.get("chunk_text"))
        else:
            demo = " | PROVENANCE: DEMO/SYNTHETIC RECORD" if item.get("demo_data") else ""
            header = (
                f"[{ref}] SOURCE: {item.get('title')} | Component: {item.get('component')} "
                f"| Failure mode: {item.get('failure_mode')} | Quality: {_quality_of(item)} "
                f"| Status: {item.get('document_status')} | Similarity {item.get('similarity')}{demo}"
            )
            body = (
                f"symptom: {_clip(item.get('symptom'), 220)} | inspection finding: {_clip(item.get('inspection'), 240)} "
                f"| repair: {_clip(item.get('repair'), 240)} | outcome: {_clip(item.get('outcome'), 80)}"
            )
        lines.append(f"{header}\n    {body}")
    return "\n".join(lines)


def format_attempts(attempts: List[Dict[str, Any]]) -> str:
    if not attempts:
        return "none recorded"
    out = []
    for attempt in attempts[:6]:
        out.append(
            f"- {_clip(attempt.get('action_taken'), 140)} -> result: {attempt.get('result')} "
            f"(machine {attempt.get('machine_id') or 'n/a'}, {attempt.get('created_at')})"
        )
    return "\n".join(out)


def format_findings(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "none recorded yet"
    out = []
    for finding in findings[:10]:
        value = f" = {finding.get('value')} {finding.get('unit') or ''}" if finding.get("value") else ""
        out.append(
            f"- [{finding.get('kind')}] {_clip(finding.get('title'), 120)}{value} → {finding.get('ruling')}"
        )
    return "\n".join(out)


class EvidenceReasoning:
    def __init__(self) -> None:
        self.url = OLLAMA_URL
        self.model = os.getenv("OLLAMA_MODEL", MODEL_NAME)

    # ------------------------------------------------------------------
    def assess_sufficiency(self, evidence: List[Dict[str, Any]], query: str = "") -> Dict[str, Any]:
        """Decide whether the retrieved evidence can support a cause.

        Two independent conditions are required for a source to count as support:
        it must clear the similarity threshold, AND it must share the vocabulary of
        what was actually reported. The second condition is what stops a dense
        corpus of similar historical cases from "supporting" a symptom report that
        describes something unrelated.
        """
        query_terms = _terms(query)
        top = max([float(item.get("effective_score") or 0) for item in evidence] or [0.0])

        scored: List[Tuple[Dict[str, Any], float, float]] = []
        for item in evidence:
            score = float(item.get("effective_score") or 0)
            overlap = (
                len(query_terms & _terms(_evidence_text(item))) / len(query_terms) if query_terms else 1.0
            )
            scored.append((item, score, round(overlap, 3)))

        for item, _score, overlap in scored:
            item["lexical_overlap"] = overlap

        supporting = [
            item
            for item, score, overlap in scored
            if score >= SUPPORT_THRESHOLD and overlap >= MIN_LEXICAL_OVERLAP
        ]
        overlapping_terms: set = set()
        for item in supporting:
            overlapping_terms |= query_terms & _terms(_evidence_text(item))
        unmatched_terms = sorted(query_terms - overlapping_terms)

        if not evidence:
            level = "insufficient"
            reason = "Nothing relevant was retrieved from the engineering memory for this evidence set."
        elif not supporting and query_terms:
            level = "insufficient"
            reason = (
                "The retrieved sources do not share the vocabulary of the reported symptom set "
                f"(unmatched terms: {', '.join(unmatched_terms[:8]) or 'none'}). "
                "Similarity scores alone are not treated as support."
            )
        elif not supporting:
            level = "insufficient"
            reason = (
                f"The best match scored {top:.3f}, below the {SUPPORT_THRESHOLD:.2f} support threshold. "
                "No source is strong enough to support a cause."
            )
        elif len(supporting) <= 2 or top < 0.60:
            level = "partial"
            reason = (
                f"{len(supporting)} source(s) clear both the similarity threshold and the vocabulary check; "
                f"strongest match {top:.3f}."
            )
        else:
            level = "sufficient"
            reason = (
                f"{len(supporting)} sources clear both the similarity threshold and the vocabulary check; "
                f"strongest match {top:.3f}."
            )

        return {
            "level": level,
            "supporting_count": len(supporting),
            "supporting": supporting,
            "top_score": round(top, 4),
            "reason": reason,
            "threshold": SUPPORT_THRESHOLD,
            "lexical_overlap_threshold": MIN_LEXICAL_OVERLAP,
            "query_terms": sorted(query_terms)[:40],
            "unmatched_terms": unmatched_terms[:20],
        }

    def insufficient_response(
        self,
        *,
        machine_id: str,
        investigation_id: Optional[str],
        symptoms: List[str],
        evidence: List[Dict[str, Any]],
        machine: Dict[str, Any],
        findings: List[Dict[str, Any]],
        assessment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Refuse to invent a cause and state exactly what to collect instead."""
        what_to_collect = []
        checked_components = {  # type: ignore[var-annotated]
            (finding.get("component") or "").lower() for finding in findings if finding.get("component")
        }
        for item in evidence[:4]:
            component = (item.get("component") or "").lower()
            if component and component not in checked_components:
                what_to_collect.append(
                    f"Record measured values for {item.get('component')} (the closest retrieved source concerns it)"
                )
        assessment = assessment or {}
        what_to_collect.extend(
            [
                "Record hydraulic oil temperature at operating temperature (steady, after 20+ minutes of work)",
                "Record main relief pressure and pump delivery pressure at operating temperature",
                "Record fault codes currently active on the machine display",
                "State whether the symptom changes between cold and hot hydraulic oil",
            ]
        )

        return {
            "machine_id": machine_id,
            "investigation_id": investigation_id,
            "reasoning_status": "insufficient_evidence",
            "evidence_sufficiency": "insufficient",
            "sufficiency_reason": assessment.get("reason"),
            "unmatched_terms": assessment.get("unmatched_terms", []),
            "symptoms_analyzed": symptoms,
            "likely_causes": [],
            "affected_component": None,
            "confidence": "none",
            "reasoning": (
                "Insufficient evidence. "
                + (assessment.get("reason") or "")
                + " No cause is asserted, and no repair is recommended until the missing evidence is collected."
            ),
            "recommended_next_inspection": [],
            "already_checked": [finding.get("title") for finding in findings],
            "previous_failed_attempts": [],
            "previous_successful_resolutions": [],
            "supporting_evidence": evidence[:4],
            "conflicting_evidence": [],
            "safety_notes": [],
            "what_to_collect_next": what_to_collect,
            "grounding": {
                "machine_model": machine.get("machine_model"),                    "support_threshold": SUPPORT_THRESHOLD,
                    "lexical_overlap_threshold": MIN_LEXICAL_OVERLAP,
                    "evidence_considered": len(evidence),
                    "local_model_called": False,
                },
            "timings": {"llm_ms": 0.0, "prompt_chars": 0},
        }

    # ------------------------------------------------------------------
    def reason(
        self,
        *,
        machine_id: str,
        investigation_id: Optional[str],
        symptoms: List[str],
        observations: Dict[str, Any],
        evidence: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        failed_attempts: List[Dict[str, Any]],
        successful_resolutions: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        machine: Dict[str, Any],
        sensor_findings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started = time.time()
        query_text = " ".join(
            list(symptoms) + [f"{f.get('title')} {f.get('detail') or ''}" for f in findings]
        )
        assessment = self.assess_sufficiency(evidence, query=query_text)

        if assessment["level"] == "insufficient":
            return self.insufficient_response(
                machine_id=machine_id,
                investigation_id=investigation_id,
                symptoms=symptoms,
                evidence=evidence,
                machine=machine,
                findings=findings,
                assessment=assessment,
            )

        prompt = self._build_prompt(
            machine_id=machine_id,
            symptoms=symptoms,
            observations=observations,
            evidence=evidence,
            findings=findings,
            failed_attempts=failed_attempts,
            successful_resolutions=successful_resolutions,
            conflicts=conflicts,
            machine=machine,
            sensor_findings=sensor_findings,
            sufficiency=assessment["level"],
        )

        llm_started = time.time()
        reasoning_status = "evidence_grounded_llm"
        parsed: Dict[str, Any] = {}
        error: Optional[str] = None
        try:
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {"temperature": 0.1, "num_predict": MAX_OUTPUT_TOKENS},
                },
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            parsed = extract_json_object(response.json().get("response", ""))
        except Exception as exc:
            error = str(exc)
            reasoning_status = "ai_engine_unavailable"
            print(f"[EvidenceReasoning] Local AI engine unavailable ({exc}).")
        llm_ms = (time.time() - llm_started) * 1000

        valid_ids = {f"E{index}" for index in range(1, min(len(evidence), MAX_EVIDENCE_IN_PROMPT) + 1)}
        by_ref = {ref: evidence[int(ref[1:]) - 1] for ref in valid_ids}

        causes = []
        unverified_citations: List[str] = []
        for cause in parsed.get("likely_causes", []) or []:
            refs = [str(r).upper() for r in (cause.get("evidence") or cause.get("evidence_ids") or [])]
            supported = [ref for ref in refs if ref in valid_ids]
            unverified_citations.extend([ref for ref in refs if ref not in valid_ids])
            if not supported:
                # A cause with no citation in the retrieved set is not grounded,
                # so it is not reported as a cause.
                continue
            causes.append(
                {
                    "cause": cause.get("cause") or cause.get("failure_mode") or "Unspecified",
                    "component": cause.get("component") or "",
                    "confidence": float(cause.get("confidence") or 0.0),
                    "reason": cause.get("reason") or cause.get("reasoning") or "",
                    "evidence_refs": supported,
                    "evidence": [
                        {
                            "id": by_ref[ref]["id"],
                            "title": by_ref[ref].get("title") or by_ref[ref].get("document_name"),
                            "quality_level": by_ref[ref].get("quality_level"),
                            "document_status": by_ref[ref].get("document_status"),
                            "revision": by_ref[ref].get("revision"),
                        }
                        for ref in supported
                    ],
                }
            )

        if reasoning_status == "ai_engine_unavailable" or not causes:
            # Never present a synthesised conclusion as an answer. The caller gets
            # the retrieved evidence plus an explicit statement of what failed.
            return {
                "machine_id": machine_id,
                "investigation_id": investigation_id,
                "reasoning_status": reasoning_status,
                "evidence_sufficiency": assessment["level"],
                "symptoms_analyzed": symptoms,
                "likely_causes": [],
                "affected_component": None,
                "confidence": "none",
                "reasoning": (
                    "The local reasoning engine did not return a grounded answer"
                    + (f" ({error})" if error else "")
                    + ". Retrieved evidence is shown unchanged and no cause is asserted."
                ),
                "recommended_next_inspection": parsed.get("recommended_next_inspection", []) or [],
                "already_checked": [finding.get("title") for finding in findings],
                "previous_failed_attempts": failed_attempts,
                "previous_successful_resolutions": successful_resolutions,
                "supporting_evidence": assessment["supporting"][:5],
                "conflicting_evidence": conflicts,
                "safety_notes": parsed.get("safety_notes", []) or [],
                "what_to_collect_next": [
                    "Re-run the reasoning step once the local AI engine is reachable",
                    "Add measured findings so the evidence set becomes decisive",
                ],
                "grounding": {
                    "machine_model": machine.get("machine_model"),
                    "support_threshold": SUPPORT_THRESHOLD,
                    "evidence_considered": len(evidence),
                    "local_model_called": reasoning_status == "evidence_grounded_llm",
                    "error": error,
                },
                "timings": {"llm_ms": round(llm_ms, 2), "prompt_chars": len(prompt)},
            }

        confidence = "low"
        top_conf = max(cause["confidence"] for cause in causes)
        if assessment["level"] == "sufficient" and top_conf >= 0.7:
            confidence = "medium" if top_conf < 0.85 else "high"
        elif assessment["level"] == "partial" and top_conf >= 0.6:
            confidence = "low"

        return {
            "machine_id": machine_id,
            "investigation_id": investigation_id,
            "reasoning_status": reasoning_status,
            "evidence_sufficiency": assessment["level"],
            "sufficiency_reason": assessment["reason"],
            "symptoms_analyzed": symptoms,
            "likely_causes": causes[:4],
            "affected_component": causes[0]["component"] or None,
            "confidence": confidence,
            "confidence_float": round(top_conf, 3),
            "reasoning": parsed.get("reasoning", "") or "",
            "recommended_next_inspection": parsed.get("recommended_next_inspection", []) or [],
            "already_checked": [finding.get("title") for finding in findings],
            "previous_failed_attempts": failed_attempts,
            "previous_successful_resolutions": successful_resolutions,
            "supporting_evidence": assessment["supporting"][:5],
            "conflicting_evidence": conflicts,
            "safety_notes": parsed.get("safety_notes", []) or [],
            "exact_machine_history": bool(
                [item for item in evidence if (item.get("machine_id") or "") == machine_id]
            ),
            "similar_machine_inference_note": (
                None
                if any((item.get("machine_id") or "") == machine_id for item in evidence)
                else "No recorded history exists for this machine; the matching evidence comes from other "
                     "machines with comparable symptoms and is labelled as such."
            ),
            "unverified_citations": sorted(set(unverified_citations)),
            "what_to_collect_next": parsed.get("what_to_collect_next", []) or [],
            "grounding": {
                "machine_model": machine.get("machine_model"),
                "support_threshold": SUPPORT_THRESHOLD,
                "evidence_considered": len(evidence),
                "evidence_in_prompt": min(len(evidence), MAX_EVIDENCE_IN_PROMPT),
                "local_model_called": True,
                "model": self.model,
            },
            "timings": {"llm_ms": round(llm_ms, 2), "total_ms": round((time.time() - started) * 1000, 2), "prompt_chars": len(prompt)},
        }

    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        *,
        machine_id: str,
        symptoms: List[str],
        observations: Dict[str, Any],
        evidence: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        failed_attempts: List[Dict[str, Any]],
        successful_resolutions: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        machine: Dict[str, Any],
        sensor_findings: Optional[Dict[str, Any]],
        sufficiency: str,
    ) -> str:
        conflict_text = "none detected in the retrieved evidence"
        if conflicts:
            conflict_text = "\n".join(
                f"- {c['topic']} ({c['unit']}): " + " vs ".join(f"{s['value']} from {s['id']}" for s in c["sources"])
                for c in conflicts[:4]
            )
        sensor_text = ""
        if sensor_findings:
            sensor_text = (
                "\nCONDITION MONITORING (public hydraulic test-rig dataset, NOT live excavator telemetry): "
                + json.dumps(sensor_findings)
            )

        return f"""/no_think
You are the diagnostic reasoning stage of an industrial engineering workstation for hydraulic excavators.
You are NOT a chatbot. Your output is consumed by a maintenance engineer.

MACHINE: {machine_id} ({machine.get('machine_model') or 'model not recorded'})
REPORTED SYMPTOMS: {json.dumps(symptoms)}
MEASUREMENTS / OBSERVATIONS ALREADY RECORDED: {json.dumps(observations)}
FINDINGS RECORDED SO FAR:
{format_findings(findings)}
PREVIOUS REPAIR ATTEMPTS (may include failed attempts):
{format_attempts(failed_attempts)}
PREVIOUS SUCCESSFUL RESOLUTIONS:
{format_attempts(successful_resolutions)}
EVIDENCE SUFFICIENCY: {sufficiency}
CONFLICTING INFORMATION DETECTED:
{conflict_text}
{sensor_text}

RETRIEVED ENGINEERING EVIDENCE (the ONLY engineering knowledge you may use):
{format_evidence(evidence)}

RULES — these override any other consideration:
1. Use ONLY the retrieved evidence above. Do not invent historical cases, manual sections, measurements, repairs, part numbers or sources.
2. Every likely cause MUST cite the evidence ids that support it, in "evidence": ["E1","E4"]. A cause with no citation is invalid.
3. If sources state conflicting values, say so explicitly in "reasoning" instead of choosing one silently.
4. If a cited source is marked SUPERSEDED, say so and prefer CURRENT/APPROVED sources.
5. If the evidence concerns other machines only, state that the inference is from similar machines and is not this machine's own history.
6. Return JSON only, matching this exact shape:
{{
  "likely_causes": [
    {{"cause": "failure mode in engineering terms", "component": "component name", "confidence": 0.0,
      "reason": "2 sentences tying the recorded symptoms/findings to the cited evidence", "evidence": ["E1"]}}
  ],
  "reasoning": "3 sentences maximum. State what the evidence supports, and state explicitly what it does NOT establish.",
  "recommended_next_inspection": ["specific measurable inspection with value, unit and operating condition"],
  "what_to_collect_next": ["information that is still missing"],
  "safety_notes": ["precaution required before the recommended inspection"]
}}
Be concise. Do not restate the evidence list."""


evidence_reasoning = EvidenceReasoning()
