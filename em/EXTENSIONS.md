# Engineering Memory — extension modules

This document covers the modules **added** on top of the existing platform. Nothing
in the original stack was rebuilt or replaced: React + Vite + Tailwind frontend,
FastAPI backend, MySQL/SQLite store, BGE embeddings, FAISS index, local Qwen 3:4B
through Ollama and the Random Forest condition model all keep their original code
paths, routes and behaviour.

The extensions are **additive** in five concrete ways:

| Area | What was added |
| --- | --- |
| Database | 22 new tables created idempotently at startup (`backend/app/db/extensions.py`). No existing table, column or row is altered or dropped. |
| Backend | New service modules and new routers mounted on new paths. Existing endpoints (`/api/diagnose`, `/api/machines`, `/api/cases`, `/api/documents`, `/api/memory`, `/api/stats`, `/api/sensors`, `/api/benchmark`, `/api/auth`) are unchanged in behaviour; `POST /api/documents/upload` now runs the real extraction pipeline while keeping its original response contract. |
| Retrieval | `memory_service` and the original diagnosis path are untouched. The new hybrid surface (`retrieval_service`) is used by investigations, the review workflow and the retrieval test bench. |
| Frontend | New pages and nav entries per role. New keys were added to the existing page-title map; existing pages, layout and design language are preserved. |
| Index | The live index is still `models/engineering_memory.faiss` + `models/engineering_memory_mapping.json`. New writes go through `index_service`, which appends and rewrites both files atomically. |

## Extraction pipeline

    UPLOAD → CLASSIFICATION → TEXT/IMAGE/HANDWRITING/TABLE/DIAGRAM DETECTION
    → EXTRACTION → STRUCTURING → VALIDATION (confidence) → CHUNKING → METADATA
    → relational store → human approval → BGE → FAISS

* Digital PDFs are parsed with PyMuPDF; tables are detected with `page.find_tables()`
  and stored with headers preserved; figures are linked to their page, region and
  neighbouring real text.
* DOCX is read directly from the OOXML package (no extra dependency).
* Scanned PDFs / photographs: OCR runs only if a local Tesseract binary exists.
  When it does not, the job is parked as `OCR_ENGINE_UNAVAILABLE` and routed to the
  review queue for a human transcript. No text is invented.
* The extraction confidence is a transparent heuristic score over measured signals
  (text coverage, character density, printable ratio, structure density). The
  breakdown and the measured inputs are stored and shown beside the number.
* Approved documents are embedded with BGE and appended to FAISS; older revisions
  of the same document are marked `SUPERSEDED` with a supersede date, never deleted.

## New API surface

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/ingestion/upload` | Full multimodal pipeline |
| GET | `/api/ingestion/capabilities` | What this host can actually extract (OCR/vision availability) |
| GET | `/api/ingestion/jobs`, `/api/ingestion/jobs/{job_id}` | Ingestion jobs with measured counts |
| GET | `/api/ingestion/queue` | Review queue (engineer/admin) |
| GET/PUT | `/api/ingestion/documents/{id}/extractions`, `/api/ingestion/extractions/{id}` | Per-page extraction records, human transcript editing |
| POST | `/api/ingestion/documents/{id}/rebuild-chunks` | Re-chunk from corrected text |
| GET | `/api/documents/{id}/versions`, `/review-status` | Revision history and pipeline stage |
| POST | `/api/documents/{id}/approve`, `/reject` | Approve (supersede + embed + index) or reject |
| GET/POST | `/api/investigations`, `/api/investigations/{id}` | Investigation sessions |
| POST | `/api/investigations/{id}/findings` | Record a finding and re-run retrieval |
| POST | `/api/investigations/{id}/re-evaluate`, `/diagnose` | Hybrid retrieval / grounded reasoning |
| GET | `/api/investigations/{id}/timeline`, `/next-inspection`, `/safety`, `/case-draft` | Evidence-backed panels |
| POST | `/api/investigations/{id}/photos`, `/photos/{photo_id}/correct` | Photo evidence and manual component correction |
| POST | `/api/investigations/{id}/repair`, `/verify`, `/close`, `/create-knowledge` | Repair attempts (including failures), verification, closed loop |
| GET | `/api/investigations/attempts/similar` | Historical repair attempts for comparable symptoms |
| GET | `/api/machines/{id}/passport`, `/qr`, `/scan/{token}` | Machine passport and QR access code |
| GET | `/api/knowledge`, `/overview`, `/review-queue`, `/conflicts`, `/{id}` | Knowledge lifecycle |
| POST | `/api/knowledge/{id}/submit`, `/{id}/review`, `/reindex`, `/conflicts/{id}/resolve` | Submission, approval, index rebuild |
| POST/GET | `/api/retrieval/search`, `/filters`, `/events`, `/latency` | Hybrid retrieval surface and measured history |
| GET | `/api/system/status`, `/vector-db`, `/safety`, `/audit-summary` | True component state and index internals |
| GET | `/api/audit` | Append-only audit log (admin) |

## Evidence quality and versioning

Every retrieved item carries its quality level
(`UNVERIFIED` → `TECHNICIAN_SUBMITTED` → `ENGINEER_REVIEWED` → `VERIFIED`), its
document status (`CURRENT`, `SUPERSEDED`, `ARCHIVED`, `DRAFT`, `PENDING_REVIEW`),
whether it is demo/synthetic data, and the components of its ranking:

    effective_score = cosine similarity × quality weight × version priority × source priority

Conflicting values are reported from both sources side by side, with the current
approved source listed first. Nothing is merged silently and the language model is
never asked to choose. A cause is only reported when the retrieved evidence both
clears the similarity threshold **and** shares the vocabulary of what was reported;
otherwise the response states "insufficient evidence" and asks for what is missing.
Citations the model produces are validated against the retrieved set — unsupported
citations are dropped and reported.

## Verification

    python scripts/acceptance_check.py                # run the twelve acceptance checks
    python scripts/acceptance_check.py --skip-index   # no writes to the vector index
    python scripts/acceptance_check.py --cleanup      # delete the records it created

The checks cover digital PDF ingestion → indexing → retrieval, scanned and
handwritten intake (verifying the honest review path when no OCR engine is
installed), QR resolution to a real machine, photo evidence with manual
correction, investigation creation, findings that change the evidence set,
failed-repair memory, revision superseding with conflict detection, the closed
loop from repair to approved knowledge to retrieval, offline operation, and the
refusal to diagnose on insufficient evidence.

Where a capability is absent on this host, the platform reports that plainly:
there is no local OCR engine and no vision model in this build, and the system
says so instead of simulating the result. Edge deployment is described as an
architecture option, not as an implemented feature.
