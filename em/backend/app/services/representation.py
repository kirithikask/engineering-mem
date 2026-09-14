"""
Canonical text representation for Engineering Memory retrieval.

Every string that gets embedded — historical case documents, manual chunk
documents and search queries — is assembled here. The index builder and the
query path both import this module, so the two sides of retrieval cannot drift
apart (they previously did: the case template was duplicated in the index
builder and again in the evaluation script).

Why the shape matters
---------------------
Cases were previously embedded as one long templated paragraph::

    Historical Maintenance Case CASE-0001 | Machine: EXC-001 | Subsystem: ... |
    Component: ... | Symptoms: ... | Failure Mode: ... | Inspection: ... | ...

That skeleton is byte-identical across every case, so it dominated the sentence
embedding. Measured on the 4,008-case corpus, mean pairwise cosine between
unrelated case vectors reached 0.855, which destroys the retrieval signal.
Compact, content-only text restores the discriminative range (the mean width of
the top-100 similarity band roughly doubles, from 0.059 to 0.084).

The specific shape was chosen by measuring BOTH retrieval surfaces, because they
disagree. The 7-query ground-truth suite is single-symptom; the flagship
workflow is a multi-symptom technician report. Recall@1 / Recall@5 / MRR on the
suite, and whether the multi-symptom EXC-001 report retrieves the expected
component:

    legacy verbose template   0.429 / 0.429 / 0.492   multi-symptom: MISS
    tags first, symptom tail  0.714 / 0.857 / 0.797   multi-symptom: MISS
    symptom first, tags tail  0.714 / 0.857 / 0.770   multi-symptom: OK  <- SHIPPED
    symptom text alone        0.571 / 0.571 / 0.590   multi-symptom: OK

Leading with the engineering tags scores best on the suite and yet fails the
real workflow: the suite's expected answers are near-copies of the tag text, so
leading with tags optimises the metric rather than the task, and a multi-symptom
report - whose wording is symptom vocabulary - then matches someone else's
conclusion. Leading with the reported symptom and carrying the conclusion as a
payload is strong on both surfaces, which is also the correct model of the task:
retrieve by the evidence the technician reports, and read the answer off the
retrieved case.

Embedding the symptom text alone is rejected: it drops the engineering vocabulary
that the technician's own wording also uses, and loses ~0.14 Recall@1.

Query assembly matters as much as document assembly. Machine context is NOT put
into the query text: no document contains the machine model, so it contributes
only noise. Measured on the multi-symptom report, appending the model moved the
expected component from rank 1 to rank 2.

The demo/synthetic marker that used to be prefixed to embedded text is gone
from the vector: it was a third constant shared by 3,000 vectors, and provenance
is carried as a structured field (`source_type`) that flows through the index
mapping, the API response and the UI badges.

BGE models are trained for retrieval with an instruction prefix on the *query*
side only, so `embed_query` applies it and documents are embedded bare.
"""

from typing import Any, Iterable, Mapping

# Documented usage for BGE retrieval models: instruction on the query, never on
# the passage. Source: BAAI/bge-small-en-v1.5 model card.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _clean(value: Any) -> str:
    """Normalise a database field to a single-line, whitespace-collapsed string."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def case_document(case: Mapping[str, Any]) -> str:
    """
    The searchable text for one historical maintenance case.

    The reported symptom leads, because that is the evidence a technician brings
    to the search; the engineering conclusion follows as a compact tag payload.
    No repeated boilerplate and no case id (a constant token shared by every
    document compresses the similarity range while carrying no signal).
    """
    symptom = _clean(case.get("symptom"))
    component = _clean(case.get("component"))
    failure = _clean(case.get("failure_mode"))
    subsystem = _clean(case.get("subsystem"))

    tags = " | ".join(t for t in (component, failure, subsystem) if t)
    if symptom and tags:
        return f"symptoms: {symptom} | {tags}"
    if symptom:
        return f"symptoms: {symptom}"
    return tags


def chunk_document(chunk: Mapping[str, Any]) -> str:
    """
    The searchable text for one engineering-document chunk.

    The chunk body already carries the content signal, so it leads; the
    provenance tags follow in a compact form.
    """
    text = _clean(chunk.get("chunk_text"))
    name = _clean(chunk.get("document_name"))
    section = _clean(chunk.get("section_heading"))
    page = chunk.get("page_number")
    component = _clean(chunk.get("component"))

    header = name
    if section:
        header = f"{name} — {section}" if name else section
    tags = []
    if page not in (None, ""):
        tags.append(f"page {page}")
    if component:
        tags.append(f"component: {component}")

    head = header if not tags else f"{header} ({', '.join(tags)})"
    if text and head:
        return f"{head}: {text}"
    return text or head


def query_text(symptoms: Iterable[str]) -> str:
    """
    The search-side text for a diagnosis request.

    Every reported symptom is included, because multi-symptom reports are the
    normal case and no symptom may be silently dropped. Machine context is
    deliberately excluded: case documents carry no machine identity at all, so
    adding the model to the query contributes only noise (measured: it moved the
    expected component from rank 1 to rank 2 on the multi-symptom report).
    Machine context still reaches the reasoning stage through the machine record.
    """
    reported = [_clean(s) for s in symptoms if _clean(s)]
    return "; ".join(reported)


def embed_query(text: str) -> str:
    """Apply the BGE retrieval instruction to a query. Documents are never prefixed."""
    return f"{BGE_QUERY_INSTRUCTION}{text}"


def embed_document(text: str) -> str:
    """Documents are embedded as-is; the BGE instruction belongs on the query only."""
    return text


__all__ = [
    "BGE_QUERY_INSTRUCTION",
    "case_document",
    "chunk_document",
    "query_text",
    "embed_query",
    "embed_document",
]
