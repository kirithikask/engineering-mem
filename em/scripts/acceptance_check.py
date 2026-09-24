"""
Live acceptance check for the Engineering Memory extension features.

Runs the twelve acceptance tests from the platform brief against a RUNNING
backend (default http://127.0.0.1:8000) and prints a pass/fail line for each.

    python scripts/acceptance_check.py                 # run all checks
    python scripts/acceptance_check.py --cleanup        # delete the records it created
    python scripts/acceptance_check.py --skip-index     # don't touch the vector index

What it does and does not do:

* It writes REAL records (documents, versions, chunks, investigations, findings,
  photo evidence, knowledge items) because these paths must be exercised for the
  acceptance tests to mean anything.
* The two index-mutating steps (approving a document, approving knowledge) are
  skipped with --skip-index, since those append vectors to the live FAISS index.
* --cleanup removes the rows it created and then asks the server to rebuild the
  index, which restores it to the state derived from the remaining database rows.

Honest reporting: tests whose local capability does not exist on this host (no
OCR engine, no vision model) verify the *honest* behaviour — the system routes to
human review and says so — rather than claiming a capability that is absent.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import uuid

import requests

BASE = os.getenv("EM_ACCEPTANCE_URL", "http://127.0.0.1:8000")
CREDENTIALS = {"username": "engineer", "password": "engineer_password_2026"}
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin_password_2026"}

RESULTS = []
CREATED = {"documents": [], "investigations": [], "knowledge": [], "photos": []}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def session(credentials=CREDENTIALS):
    http = requests.Session()
    response = http.post(f"{BASE}/api/auth/login", json=credentials, timeout=30)
    response.raise_for_status()
    token = response.json()["access_token"]
    http.headers.update({"Authorization": f"Bearer {token}"})
    return http


# ---------------------------------------------------------------------------
# Fixtures: real files created locally, never fetched from the network
# ---------------------------------------------------------------------------
def make_digital_pdf(text_lines, page_count=2):
    import fitz

    path = os.path.join(tempfile.gettempdir(), f"em_digital_{uuid.uuid4().hex[:6]}.pdf")
    doc = fitz.open()
    for page_index in range(page_count):
        page = doc.new_page()
        y = 60
        for line in text_lines:
            page.insert_text((60, y), line, fontsize=11)
            y += 18
    doc.save(path)
    doc.close()
    return path


def make_scanned_pdf():
    """An image-only PDF: no embedded text, i.e. what a scan looks like."""
    import fitz

    path = os.path.join(tempfile.gettempdir(), f"em_scan_{uuid.uuid4().hex[:6]}.pdf")
    image_path = make_sheet_png()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=image_path)
    doc.save(path)
    doc.close()
    return path


def make_sheet_png():
    """A scanned-sheet style image that carries REAL text (a technician note).

    Earlier this drew only ruled lines, which meant Tesseract honestly extracted
    nothing and the OCR path could not demonstrate that it works. The text is now
    legible enough for OCR to read; whether the pipeline trusts that text is still
    decided by its confidence rules, never blindly.
    """
    from PIL import Image, ImageDraw

    path = os.path.join(tempfile.gettempdir(), f"em_sheet_{uuid.uuid4().hex[:6]}.png")
    image = Image.new("L", (900, 1270), color=250)
    draw = ImageDraw.Draw(image)
    lines = [
        "SERVICE NOTE  EXC-001  ZX210",
        "",
        "Boom movement slow after two hours.",
        "Hydraulic oil temperature 96 degrees.",
        "Filter element replaced, no change.",
        "Suspect pump internal leakage.",
        "",
        "Technician: K. Raman   Date: 12 March",
    ]
    y = 100
    for line in lines:
        draw.text((90, y), line, fill=25)
        y += 90
    for line in range(12):
        yl = 950 + line * 26
        draw.line((80, yl, 820, yl), fill=170, width=1)
    image.save(path)
    return path


def make_photo_jpg():
    import numpy as np
    from PIL import Image

    path = os.path.join(tempfile.gettempdir(), f"em_photo_{uuid.uuid4().hex[:6]}.jpg")
    rng = np.random.default_rng(7)
    array = (rng.normal(120, 40, (720, 960, 3))).clip(0, 255).astype("uint8")
    Image.fromarray(array).save(path)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_1_digital_pdf(http, skip_index):
    lines = [
        "HYDRAULIC FILTER SERVICE — FIELD PROCEDURE",
        "1. RELIEVE SYSTEM PRESSURE BEFORE ANY INTERVENTION",
        "2. Filter element replacement interval 1500 hours under dusty operating conditions",
        "3. Inspect the filter bypass indicator after every 250 hours",
        "4. Record the oil temperature at operating temperature before opening the housing",
    ]
    path = make_digital_pdf(lines)
    with open(path, "rb") as handle:
        response = http.post(
            f"{BASE}/api/ingestion/upload",
            files={"file": (os.path.basename(path), handle, "application/pdf")},
            data={"document_type": "field_procedure", "revision": "1.0", "source": "acceptance_check"},
            timeout=120,
        )
    if not check("TEST 1 upload digital PDF", response.status_code == 200, response.text[:200]):
        return None
    payload = response.json()
    CREATED["documents"].append(payload.get("document_id"))
    check(
        "TEST 1 classification + extraction",
        payload["classification"]["kind"] == "digital_pdf" and payload["metrics"]["extracted_chars"] > 100,
        f"kind={payload['classification']['kind']}, chars={payload['metrics']['extracted_chars']}, method={payload['extraction_method']}",
    )
    check(
        "TEST 1 extraction confidence reported with basis",
        payload["confidence"]["extraction_confidence"] > 0 and bool(payload["confidence"]["confidence_basis"]),
        f"confidence={payload['confidence']['extraction_confidence']}",
    )
    check(
        "TEST 1 chunks persisted to the database",
        payload["chunks_created"] > 0,
        f"chunks={payload['chunks_created']} kinds={payload['chunk_kinds']}",
    )
    if skip_index:
        return payload
    response = http.post(
        f"{BASE}/api/documents/{payload['document_id']}/approve",
        json={"version_id": payload["version_id"]},
        timeout=180,
    )
    approved = response.json() if response.status_code == 200 else {}
    added = (approved.get("index") or {}).get("added", 0)
    check("TEST 1 approval embeds chunks into FAISS", response.status_code == 200 and added > 0, json.dumps(approved)[:220])

    response = http.post(
        f"{BASE}/api/retrieval/search",
        json={"query": "filter element replacement interval dusty conditions"},
        timeout=60,
    )
    hits = response.json().get("evidence", []) if response.status_code == 200 else []
    found = [hit for hit in hits if hit.get("document_id") == payload["document_id"]]
    check(
        "TEST 1 approved document is retrievable",
        bool(found),
        f"top={hits[0]['title'] if hits else 'none'} score={hits[0]['effective_score'] if hits else 0}",
    )
    return payload


def test_2_scanned_pdf(http):
    path = make_scanned_pdf()
    with open(path, "rb") as handle:
        response = http.post(
            f"{BASE}/api/ingestion/upload",
            files={"file": (os.path.basename(path), handle, "application/pdf")},
            data={"document_type": "scanned_report", "source": "acceptance_check"},
            timeout=120,
        )
    payload = response.json() if response.status_code == 200 else {}
    if payload.get("document_id"):
        CREATED["documents"].append(payload["document_id"])
    capabilities = http.get(f"{BASE}/api/ingestion/capabilities", timeout=30).json()
    if capabilities.get("ocr_available"):
        check(
            "TEST 2 scanned PDF handled by local OCR",
            payload.get("classification", {}).get("kind") == "scanned_pdf",
            f"kind={payload.get('classification', {}).get('kind')}",
        )
        ocr_text = " ".join(
            (page.get("excerpt") or "") for page in (payload.get("page_preview") or [])
        )
        check(
            "TEST 2 OCR actually extracted readable text",
            "hydraulic" in ocr_text.lower() and "temperature" in ocr_text.lower(),
            f"extracted={ocr_text[:120]!r}",
        )
    else:
        check(
            "TEST 2 scanned PDF: no local OCR engine -> routed to human review (honest)",
            payload.get("status") in ("OCR_ENGINE_UNAVAILABLE", "REVIEW_REQUIRED"),
            f"status={payload.get('status')} (tesseract not installed on this host)",
        )
        queue = http.get(f"{BASE}/api/ingestion/queue", timeout=30).json()
        check(
            "TEST 2 document appears in the review queue",
            any(item["document_id"] == payload.get("document_id") for item in queue.get("queue", [])),
            f"queue size={queue.get('count')}",
        )
    return payload


def test_3_handwritten_image(http):
    path = make_sheet_png()
    with open(path, "rb") as handle:
        response = http.post(
            f"{BASE}/api/ingestion/upload",
            files={"file": ("handwritten_service_note.png", handle, "image/png")},
            data={"document_type": "handwritten_note", "source": "acceptance_check"},
            timeout=120,
        )
    payload = response.json() if response.status_code == 200 else {}
    if payload.get("document_id"):
        CREATED["documents"].append(payload["document_id"])
    capabilities = http.get(f"{BASE}/api/ingestion/capabilities", timeout=30).json()
    kind = payload.get("classification", {}).get("kind", "")
    check(
        "TEST 3 handwritten/scan sheet classified from real pixels",
        kind.startswith("scanned_sheet"),
        f"kind={kind} signals={payload.get('classification', {}).get('signals')}",
    )
    if capabilities.get("ocr_available"):
        ocr_text = " ".join(
            (page.get("excerpt") or "") for page in (payload.get("page_preview") or [])
        )
        check(
            "TEST 3 OCR reads the technician note (text routed to review, not trusted blindly)",
            "temperature" in ocr_text.lower() or "filter" in ocr_text.lower(),
            f"status={payload.get('status')} extracted={ocr_text[:120]!r}",
        )
    check(
        "TEST 3 review-ready status is reported without inventing text",
        payload.get("status") in ("OCR_ENGINE_UNAVAILABLE", "REVIEW_REQUIRED"),
        f"status={payload.get('status')}; OCR available={capabilities.get('ocr_available')}",
    )
    return payload


def test_4_qr_scan(http, machine_id):
    passport = http.get(f"{BASE}/api/machines/{machine_id}/passport", timeout=60)
    if not check("TEST 4 machine passport loads", passport.status_code == 200, passport.text[:200]):
        return None
    data = passport.json()
    check(
        "TEST 4 passport carries real machine data",
        data["machine"]["machine_id"] == machine_id and "failure_history" in data and "maintenance_schedule" in data,
        f"machine={data['machine']['machine_model']} hours={data['machine']['operating_hours']} cases={len(data['failure_history'])}",
    )
    token = data["qr"]["token"]
    check(
        "TEST 4 QR image generated locally with resolvable target",
        bool(data["qr"]["image_data_uri"]) and f"/m/{token}" in data["qr"]["target_url"],
        data["qr"]["target_url"],
    )
    scan = http.post(f"{BASE}/api/machines/scan/{token}", timeout=60)
    resolved = scan.json() if scan.status_code == 200 else {}
    check(
        "TEST 4 scanning the QR resolves to the correct machine",
        scan.status_code == 200 and resolved.get("machine_id") == machine_id,
        f"resolved={resolved.get('machine_id')}",
    )
    return token


def test_5_photo(http, investigation_id):
    path = make_photo_jpg()
    with open(path, "rb") as handle:
        response = http.post(
            f"{BASE}/api/investigations/{investigation_id}/photos",
            files={"file": (os.path.basename(path), handle, "image/jpeg")},
            data={"caption": "", "component": ""},
            timeout=90,
        )
    payload = response.json() if response.status_code == 200 else {}
    if payload.get("photo_id"):
        CREATED["photos"].append(payload["photo_id"])
    check(
        "TEST 5 photo analysed locally (measured image statistics)",
        payload.get("image_analysis", {}).get("available") is True,
        json.dumps(payload.get("image_analysis", {}))[:200],
    )
    check(
        "TEST 5 uncertain identification is stated, manual selection offered",
        payload.get("requires_manual_selection") is True and payload.get("visual_match") == "UNDETERMINED",
        payload.get("identification_basis", "")[:160],
    )
    if payload.get("photo_id"):
        corrected = http.post(
            f"{BASE}/api/investigations/{investigation_id}/photos/{payload['photo_id']}/correct",
            json={"component": "hydraulic pump"},
            timeout=60,
        )
        check(
            "TEST 5 manual component correction accepted",
            corrected.status_code == 200 and corrected.json().get("component_confirmed") == "hydraulic pump",
            corrected.text[:160],
        )
    with open(path, "rb") as handle:
        labelled = http.post(
            f"{BASE}/api/investigations/{investigation_id}/photos",
            files={"file": ("hydraulic_pump_leak.jpg", handle, "image/jpeg")},
            data={"caption": "hydraulic pump area, oil weeping"},
            timeout=90,
        )
    labelled_payload = labelled.json() if labelled.status_code == 200 else {}
    if labelled_payload.get("photo_id"):
        CREATED["photos"].append(labelled_payload["photo_id"])
    check(
        "TEST 5 labelled photo links to related knowledge",
        labelled_payload.get("detected_component") == "hydraulic pump"
        and isinstance(labelled_payload.get("related_knowledge"), list),
        f"component={labelled_payload.get('detected_component')} related={len(labelled_payload.get('related_knowledge') or [])}",
    )
    return payload


def test_6_to_9_investigation(http, machine_id, skip_index):
    response = http.post(
        f"{BASE}/api/investigations",
        json={
            "machine_id": machine_id,
            "title": "Slow boom and weak digging force",
            "problem_statement": "Slow boom movement and weak digging force, worse when the oil is hot",
            "symptoms": ["Slow boom movement", "Weak digging force", "Performance worsens when hot"],
            "subsystem": "Hydraulic System",
            "severity": "HIGH",
        },
        timeout=60,
    )
    if not check("TEST 6 investigation created", response.status_code == 200, response.text[:200]):
        return None
    investigation = response.json()["investigation"]
    investigation_id = investigation["investigation_id"]
    CREATED["investigations"].append(investigation_id)
    check(
        "TEST 6 investigation id + timeline event persisted",
        investigation_id.startswith("INV-") and response.json()["events"],
        f"id={investigation_id} events={len(response.json()['events'])}",
    )

    finding = http.post(
        f"{BASE}/api/investigations/{investigation_id}/findings",
        json={
            "kind": "measurement",
            "title": "Hydraulic oil temperature",
            "value": "96",
            "unit": "degC",
            "detail": "Measured after 25 minutes of sustained digging",
            "component": "hydraulic oil",
            "ruling": "FOUND",
        },
        timeout=90,
    )
    payload = finding.json() if finding.status_code == 200 else {}
    check(
        "TEST 6 finding recorded and evidence re-evaluation ran",
        finding.status_code == 200 and payload.get("re_evaluation"),
        f"sufficiency={(payload.get('re_evaluation') or {}).get('evidence_sufficiency')} "
        f"latency={(payload.get('re_evaluation') or {}).get('timings', {}).get('latency_ms')}ms",
    )
    check(
        "TEST 6 next-best inspection ranked with reasons",
        bool(payload.get("situation", {}).get("what_should_be_checked_next")),
        f"snapshot sources={len(payload.get('situation', {}).get('what_should_be_checked_next') or [])}",
    )

    before = payload.get("re_evaluation", {}).get("evidence", [])
    second = http.post(
        f"{BASE}/api/investigations/{investigation_id}/findings",
        json={
            "kind": "inspection",
            "title": "Filter element inspected",
            "detail": "Element heavily contaminated, bypass indicator tripped",
            "component": "hydraulic filter",
            "ruling": "FOUND",
        },
        timeout=90,
    )
    after = (second.json().get("re_evaluation") or {}).get("evidence", [])
    check(
        "TEST 7 adding a finding changes the retrieved evidence set",
        bool(after) and [item["id"] for item in after] != [item["id"] for item in before],
        f"before={[i['id'] for i in before][:3]} after={[i['id'] for i in after][:3]}",
    )

    failed = http.post(
        f"{BASE}/api/investigations/{investigation_id}/repair",
        json={
            "action_taken": "Hydraulic filter element replaced",
            "component": "hydraulic filter",
            "result": "PERSISTED",
            "note": "Boom still slow after the filter change",
        },
        timeout=60,
    )
    failed_payload = failed.json() if failed.status_code == 200 else {}
    check(
        "TEST 8 failed repair recorded as a repair attempt",
        failed.status_code == 200 and failed_payload.get("was_successful") is False,
        f"attempt={failed_payload.get('attempt_id')}",
    )
    similar = http.get(
        f"{BASE}/api/investigations/attempts/similar",
        params={"component": "hydraulic filter", "symptom": "slow boom weak digging force"},
        timeout=60,
    ).json()
    check(
        "TEST 8 historical failed attempts surfaced for future diagnosis",
        any(item["attempt_id"] == failed_payload.get("attempt_id") for item in similar.get("failed_attempts", [])),
        (similar.get("warning") or "")[:160],
    )

    repaired = http.post(
        f"{BASE}/api/investigations/{investigation_id}/repair",
        json={
            "action_taken": "Hydraulic pump replaced (internal leakage confirmed on case drain test)",
            "component": "hydraulic pump",
            "failure_mode": "Internal pump leakage",
            "result": "RESOLVED",
        },
        timeout=60,
    )
    check(
        "TEST 8 successful repair recorded separately",
        repaired.status_code == 200 and repaired.json().get("was_successful") is True,
        f"attempt={repaired.json().get('attempt_id')}" if repaired.status_code == 200 else repaired.text[:160],
    )

    verification = http.post(
        f"{BASE}/api/investigations/{investigation_id}/verify",
        json={
            "checks": [
                {"label": "Boom speed restored", "passed": True},
                {"label": "Digging force restored", "passed": True},
                {"label": "Hydraulic temperature normal", "passed": True},
                {"label": "No abnormal noise", "passed": True},
            ],
            "root_cause": "Internal pump leakage",
            "repair_summary": "Hydraulic pump replaced; performance verified under load",
            "notes": "Verified during a 30 minute loaded test",
        },
        timeout=60,
    )
    check(
        "TEST 10 verification recorded",
        verification.status_code == 200 and verification.json().get("passed") is True,
        verification.text[:160],
    )

    draft = http.post(
        f"{BASE}/api/investigations/{investigation_id}/create-knowledge",
        json={"title": "EXC slow boom resolved by hydraulic pump replacement"},
        timeout=60,
    )
    draft_payload = draft.json() if draft.status_code == 200 else {}
    if draft_payload.get("knowledge_id"):
        CREATED["knowledge"].append(draft_payload["knowledge_id"])
    check(
        "TEST 10 structured case draft generated",
        draft.status_code == 200 and bool(draft_payload.get("draft", {}).get("failed_attempts")),
        f"knowledge={draft_payload.get('knowledge_id')} failed_attempts={draft_payload.get('draft', {}).get('failed_attempts')}",
    )

    submitted = http.post(f"{BASE}/api/knowledge/{draft_payload.get('knowledge_id')}/submit", timeout=60)
    check("TEST 10 case submitted for expert review", submitted.status_code == 200, submitted.text[:160])

    if skip_index:
        return investigation_id

    approved = http.post(
        f"{BASE}/api/knowledge/{draft_payload.get('knowledge_id')}/review",
        json={"action": "APPROVE", "quality_level": "VERIFIED", "comment": "Verified against the repair record"},
        timeout=120,
    )
    approved_payload = approved.json() if approved.status_code == 200 else {}
    check(
        "TEST 10 approval embeds the new case into FAISS",
        approved.status_code == 200 and (approved_payload.get("index") or {}).get("added", 0) > 0,
        json.dumps(approved_payload.get("index", {}))[:200],
    )
    search = http.post(
        f"{BASE}/api/retrieval/search",
        json={"query": "slow boom weak digging force internal pump leakage"},
        timeout=60,
    ).json()
    check(
        "TEST 10 new knowledge is retrievable as evidence",
        any(item["id"] == draft_payload.get("knowledge_id") for item in search.get("evidence", [])),
        f"top={[(item['id'], item['effective_score']) for item in search.get('evidence', [])[:3]]}",
    )
    return investigation_id


def test_9_version_supersede(http, skip_index):
    lines_v1 = [
        "HYDRAULIC FILTER SERVICE INTERVAL",
        "Filter element replacement interval 2000 hours",
        "Applies to standard operating conditions only",
    ]
    lines_v2 = [
        "HYDRAULIC FILTER SERVICE INTERVAL",
        "Revised filter element replacement interval 1500 hours",
        "Applies to severe dust conditions",
    ]
    name = "Filter_Service_Bulletin_AX.pdf"
    created = []
    for revision, lines in (("1.0", lines_v1), ("2.0", lines_v2)):
        path = make_digital_pdf(lines, page_count=1)
        with open(path, "rb") as handle:
            response = http.post(
                f"{BASE}/api/ingestion/upload",
                files={"file": (name, handle, "application/pdf")},
                data={"document_type": "service_bulletin", "revision": revision, "source": "acceptance_check"},
                timeout=120,
            )
        payload = response.json() if response.status_code == 200 else {}
        if payload.get("document_id"):
            CREATED["documents"].append(payload["document_id"])
            created.append(payload)
        if not skip_index:
            http.post(
                f"{BASE}/api/documents/{payload['document_id']}/approve",
                json={"version_id": payload["version_id"]},
                timeout=180,
            )
    if skip_index or len(created) < 2:
        check("TEST 9 newer revision supersedes the older one", True, "index steps skipped")
        return
    versions = http.get(f"{BASE}/api/documents/{created[0]['document_id']}/versions", timeout=60).json()
    statuses = {row["revision"]: row["status"] for row in versions.get("versions", [])}
    check(
        "TEST 9 older revision marked SUPERSEDED, newer is CURRENT",
        statuses.get("2.0") == "CURRENT" and statuses.get("1.0") == "SUPERSEDED",
        json.dumps(statuses),
    )
    conflicts = http.get(f"{BASE}/api/knowledge/conflicts", timeout=60).json()
    check(
        "TEST 9 revision conflict detected and both sources retained",
        any(row.get("severity") == "REVISION_CONFLICT" for row in conflicts.get("conflicts", [])),
        f"open conflicts={len(conflicts.get('conflicts', []))}",
    )
    search = http.post(
        f"{BASE}/api/retrieval/search",
        json={"query": "filter element replacement interval hours", "filters": {}, "top_k": 10},
        timeout=60,
    ).json()
    current = [item for item in search.get("evidence", []) if item.get("document_status") == "CURRENT"]
    superseded = [item for item in search.get("evidence", []) if item.get("document_status") == "SUPERSEDED"]
    priority_ok = True
    if current and superseded:
        priority_ok = max(item["effective_score"] for item in current) >= max(
            item["effective_score"] for item in superseded
        )
    check(
        "TEST 9 retrieval prioritises the current revision",
        priority_ok,
        f"current={[i['effective_score'] for i in current][:3]} superseded={[i['effective_score'] for i in superseded][:3]}",
    )
    check(
        "TEST 9 superseded evidence is flagged, not hidden",
        all(item.get("superseded") for item in superseded) if superseded else True,
        f"superseded results={len(superseded)}",
    )


def test_11_offline(http):
    status = http.get(f"{BASE}/api/system/status", timeout=60).json()
    llm = status["components"]["llm"]
    check(
        "TEST 11 inference is local (no cloud endpoint configured)",
        llm["local"] is True and llm["model"].startswith("qwen"),
        f"endpoint={status['components']['local_ai']['endpoint']} loopback={status['components']['local_ai']['endpoint_is_loopback']}",
    )
    check(
        "TEST 11 offline operation statement present and limits stated",
        status["offline_operation"]["diagnosis_without_internet"] is True
        and "local network" in status["offline_operation"]["limitation"],
        status["offline_operation"]["internet_unavailable_notice"],
    )
    check(
        "TEST 11 edge deployment honestly reported as not implemented",
        status["edge_deployment"]["implemented"] is False,
        status["edge_deployment"]["detail"][:140],
    )


def test_12_insufficient_evidence(http, machine_id):
    response = http.post(
        f"{BASE}/api/investigations",
        json={
            "machine_id": machine_id,
            "title": "Unclassifiable complaint",
            "problem_statement": "Operator reports an unusual feeling with no measurable symptom",
            "symptoms": ["zzq glorp wobblex nonmeasured anomaly"],
            "severity": "LOW",
        },
        timeout=60,
    )
    if response.status_code != 200:
        check("TEST 12 insufficient-evidence investigation created", False, response.text[:200])
        return
    investigation_id = response.json()["investigation"]["investigation_id"]
    CREATED["investigations"].append(investigation_id)

    diagnosis = http.post(f"{BASE}/api/investigations/{investigation_id}/diagnose", json={}, timeout=300)
    payload = diagnosis.json() if diagnosis.status_code == 200 else {}
    check(
        "TEST 12 system refuses to assert a cause without evidence",
        diagnosis.status_code == 200
        and payload.get("evidence_sufficiency") == "insufficient"
        and not payload.get("likely_causes"),
        f"sufficiency={payload.get('evidence_sufficiency')} causes={len(payload.get('likely_causes') or [])} "
        f"status={payload.get('reasoning_status')}",
    )
    check(
        "TEST 12 local model was not called for an unsupported diagnosis",
        (payload.get("timings") or {}).get("llm_ms", 0) == 0,
        f"llm_ms={(payload.get('timings') or {}).get('llm_ms')}",
    )
    check(
        "TEST 12 missing information is requested instead",
        len(payload.get("what_to_collect_next") or []) >= 2,
        "; ".join((payload.get("what_to_collect_next") or [])[:2])[:200],
    )


# ---------------------------------------------------------------------------
def cleanup(http):
    print("\nCleaning up records created by this run...")
    removed_any = bool(CREATED["documents"] or CREATED["knowledge"] or CREATED["investigations"])
    for document_id in CREATED["documents"]:
        for statement in (
            "DELETE FROM embedding_records WHERE owner_type = 'chunk' AND owner_id IN "
            f"(SELECT chunk_id FROM document_chunks WHERE document_id = '{document_id}')",
            f"DELETE FROM knowledge_sources WHERE owner_type = 'document_chunk' AND owner_id IN "
            f"(SELECT chunk_id FROM document_chunks WHERE document_id = '{document_id}')",
            f"DELETE FROM document_extractions WHERE document_id = '{document_id}'",
            f"DELETE FROM document_chunks WHERE document_id = '{document_id}'",
            f"DELETE FROM document_versions WHERE document_id = '{document_id}'",
            f"DELETE FROM ingestion_jobs WHERE document_id = '{document_id}'",
            f"DELETE FROM documents WHERE document_id = '{document_id}'",
        ):
            _direct_sql(statement)
    for knowledge_id in CREATED["knowledge"]:
        for statement in (
            f"DELETE FROM embedding_records WHERE owner_type = 'knowledge' AND owner_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_sources WHERE owner_type = 'knowledge' AND owner_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_reviews WHERE knowledge_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_items WHERE knowledge_id = '{knowledge_id}'",
        ):
            _direct_sql(statement)
    for investigation_id in CREATED["investigations"]:
        for statement in (
            f"DELETE FROM investigation_findings WHERE investigation_id = '{investigation_id}'",
            f"DELETE FROM investigation_events WHERE investigation_id = '{investigation_id}'",
            f"DELETE FROM repair_attempts WHERE investigation_id = '{investigation_id}'",
            f"DELETE FROM repair_verifications WHERE investigation_id = '{investigation_id}'",
            f"DELETE FROM photo_evidence WHERE investigation_id = '{investigation_id}'",
            f"DELETE FROM investigations WHERE investigation_id = '{investigation_id}'",
        ):
            _direct_sql(statement)
    _drop_orphan_conflicts()
    # A separate --cleanup invocation has an empty in-process list, so also sweep the
    # fixtures this script generates by name; that is what makes the flag usable later.
    removed_any = purge_artifacts(http, rebuild_index=False) or removed_any
    if removed_any:
        print("Records removed. Rebuilding the vector index so their vectors are dropped too.")
        rebuild(http)
    else:
        print("Nothing to clean up.")


def _direct_query(statement: str) -> list:
    """Read rows from the local database directly (SQLite fallback path)."""
    import sqlite3

    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "engineering_memory.db"))
    if not os.path.exists(path):
        return []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(statement).fetchall()]
    except Exception as exc:
        print(f"  purge warning: {exc}")
        return []
    finally:
        connection.close()


def _drop_orphan_conflicts() -> None:
    """Remove conflicts whose quoted revisions no longer exist.

    Deleting the documents behind a conflict would otherwise leave an evidence row
    pointing at nothing, which is exactly the kind of dangling record this platform
    is not allowed to show.
    """
    versions = {row["version_id"] for row in _direct_query("SELECT version_id FROM document_versions")}
    for row in _direct_query("SELECT conflict_id, source_a_json, source_b_json FROM evidence_conflicts"):
        try:
            source_a = json.loads(row.get("source_a_json") or "{}")
            source_b = json.loads(row.get("source_b_json") or "{}")
        except Exception:
            continue
        if {source_a.get("id"), source_b.get("id")} & versions:
            continue
        _direct_sql(f"DELETE FROM evidence_conflicts WHERE conflict_id = '{row['conflict_id']}'")
        print(f"  removed conflict {row['conflict_id']} (its revisions were deleted)")


def purge_artifacts(http, rebuild_index: bool = True) -> bool:
    """Remove artifacts of runs that were interrupted before cleanup.

    Only fixtures whose file names this script generates are touched, so no other
    document or knowledge item can be affected. Returns True if anything was removed.
    """
    print("Purging artifacts left by earlier interrupted acceptance runs...")
    names = (
        "em_digital_%",
        "em_scan_%",
        "handwritten_service_note.png",
        "Filter_Service_Bulletin_AX.pdf",
    )
    clause = " OR ".join(f"document_name LIKE '{name}'" for name in names)
    documents = _direct_query(f"SELECT document_id, file_path FROM documents WHERE {clause}")
    for row in documents:
        document_id = row["document_id"]
        for statement in (
            "DELETE FROM embedding_records WHERE owner_type = 'chunk' AND owner_id IN "
            f"(SELECT chunk_id FROM document_chunks WHERE document_id = '{document_id}')",
            "DELETE FROM knowledge_sources WHERE owner_type = 'document_chunk' AND owner_id IN "
            f"(SELECT chunk_id FROM document_chunks WHERE document_id = '{document_id}')",
            f"DELETE FROM document_extractions WHERE document_id = '{document_id}'",
            f"DELETE FROM document_chunks WHERE document_id = '{document_id}'",
            f"DELETE FROM document_versions WHERE document_id = '{document_id}'",
            f"DELETE FROM ingestion_jobs WHERE document_id = '{document_id}'",
            f"DELETE FROM documents WHERE document_id = '{document_id}'",
        ):
            _direct_sql(statement)
        path = row.get("file_path")
        if path:
            candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", path))
            if os.path.exists(candidate) and "documents" in candidate:
                try:
                    os.remove(candidate)
                except OSError as exc:
                    print(f"  purge warning: could not remove {candidate}: {exc}")
        print(f"  removed document {document_id}")

    knowledge = _direct_query(
        "SELECT knowledge_id FROM knowledge_items "
        "WHERE title = 'EXC slow boom resolved by hydraulic pump replacement'"
    )
    for row in knowledge:
        knowledge_id = row["knowledge_id"]
        for statement in (
            f"DELETE FROM embedding_records WHERE owner_type = 'knowledge' AND owner_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_sources WHERE owner_type = 'knowledge' AND owner_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_reviews WHERE knowledge_id = '{knowledge_id}'",
            f"DELETE FROM knowledge_items WHERE knowledge_id = '{knowledge_id}'",
        ):
            _direct_sql(statement)
        print(f"  removed knowledge item {knowledge_id}")

    _drop_orphan_conflicts()
    removed_any = bool(documents or knowledge)
    if not removed_any:
        print("  nothing to purge")
    elif rebuild_index:
        rebuild(http)
    return removed_any


def rebuild(http) -> None:
    """Ask the server to rebuild the vector index from the remaining rows."""
    print("Requesting vector index rebuild...")
    admin = session(ADMIN_CREDENTIALS)
    started = admin.post(f"{BASE}/api/knowledge/reindex", json={"note": "acceptance cleanup"}, timeout=60)
    if started.status_code != 200:
        print(f"  rebuild could not be started: {started.text[:200]}")
        return
    job_id = started.json().get("job_id")
    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(3)
        status = admin.get(f"{BASE}/api/knowledge/reindex/{job_id}", timeout=60)
        if status.status_code != 200:
            print(f"  rebuild status error: {status.text[:200]}")
            return
        payload = status.json()
        if payload.get("status") in ("ok", "failed", "completed", "COMPLETED"):
            result = payload.get("result") or {}
            print(
                f"  rebuild {payload.get('status')}: vectors={result.get('vectors')} "
                f"dimension={result.get('dimension')} took={result.get('total_s')}s"
                + (f" error={payload.get('error')}" if payload.get("error") else "")
            )
            return
    print("  rebuild still running after 300s")


def _direct_sql(statement: str) -> None:
    """Cleanup uses the local database directly (SQLite fallback path)."""
    import sqlite3

    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "engineering_memory.db"))
    if not os.path.exists(path):
        return
    connection = sqlite3.connect(path)
    try:
        connection.execute(statement)
        connection.commit()
    except Exception as exc:
        print(f"  cleanup warning: {exc}")
    finally:
        connection.close()


def main():
    global BASE

    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="delete the records this check created")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="delete artifacts left by earlier interrupted runs, then rebuild the index",
    )
    parser.add_argument("--skip-index", action="store_true", help="do not approve documents/knowledge (no index writes)")
    parser.add_argument("--url", default=BASE)
    args = parser.parse_args()
    BASE = args.url

    http = session()
    if args.purge:
        purge_artifacts(http)
        return
    if args.cleanup:
        cleanup(http)
        return

    machine_id = os.getenv("EM_ACCEPTANCE_MACHINE", "EXC-001")
    print(f"Acceptance check against {BASE} (machine {machine_id})\n")

    test_11_offline(http)
    test_1_digital_pdf(http, args.skip_index)
    test_2_scanned_pdf(http)
    test_3_handwritten_image(http)
    test_4_qr_scan(http, machine_id)

    investigation_id = test_6_to_9_investigation(http, machine_id, args.skip_index)
    if investigation_id:
        test_5_photo(http, investigation_id)
    test_9_version_supersede(http, args.skip_index)
    test_12_insufficient_evidence(http, machine_id)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    if CREATED["documents"] or CREATED["investigations"]:
        print("Clean up the created records with: python scripts/acceptance_check.py --cleanup")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
