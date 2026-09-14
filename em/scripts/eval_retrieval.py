"""
Offline retrieval evaluation harness.

Ranks the ground-truth suite used by /api/benchmark against candidate memory
representations built in memory, so a representation change can be measured
before the FAISS index is rebuilt. Nothing here writes to the index or database.

    venv/Scripts/python.exe scripts/eval_retrieval.py

The shipped representation is IMPORTED from backend.app.services.representation
rather than re-typed here. An earlier version of this harness hand-copied the
production template, which is exactly how the index side and the query side were
able to drift apart unnoticed.

Every number printed comes from an actual ranking run over the live corpus.
"""

import os
import sys
import time
from typing import Callable, Dict, List, Tuple

import faiss
import numpy as np

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from sentence_transformers import SentenceTransformer

from backend.app.api.benchmark import BENCHMARK_TEST_SUITE
from backend.app.db.mysql_client import db
from backend.app.services.representation import case_document, embed_query, query_text

MODEL_NAME = "BAAI/bge-small-en-v1.5"


def load_cases() -> List[Dict]:
    query = (
        "SELECT case_id, machine_id, subsystem, component, failure_mode, symptom, "
        "inspection_finding, repair_action, outcome, source_type "
        "FROM maintenance_cases WHERE is_verified = 1"
    )
    return db.execute_query(query)


# ---------------------------------------------------------------------------
# Candidate representations.
#
# `case_document` is the shipped representation, imported. The others exist only
# to justify or reject a design choice, and are kept so the decision can be
# re-checked if the corpus changes.
# ---------------------------------------------------------------------------
def legacy_verbose(c: Dict) -> str:
    """The text the index used BEFORE this change. Kept as the 'before' baseline."""
    source = c.get("source_type") or "historical"
    label = "" if source == "historical" else "[DEMO/SYNTHETIC DATA] "
    return (
        f"{label}Historical Maintenance Case {c['case_id']} | Machine: {c['machine_id']} | "
        f"Subsystem: {c.get('subsystem', 'Hydraulic')} | Component: {c['component']} | "
        f"Symptoms: {c['symptom']} | Failure Mode: {c['failure_mode']} | "
        f"Inspection: {c.get('inspection_finding', '')} | Repair: {c.get('repair_action', '')} | "
        f"Outcome: {c.get('outcome', '')}"
    )


def tags_first(c: Dict) -> str:
    """
    Rejected alternative: the engineering conclusion leads and the symptom tails.

    It scores highest on the benchmark suite and still fails the flagship
    multi-symptom workflow, because the suite's expected answers are near-copies of
    the tag text. Kept as a standing warning against tuning to the suite.
    """
    tags = " | ".join(
        t for t in (c["component"], c["failure_mode"], c.get("subsystem", "")) if t
    )
    return f"{tags} | symptoms: {c['symptom']}"


def symptom_only(c: Dict) -> str:
    """Rejected alternative: only the technician-reported symptom, nothing else."""
    return f"{c['symptom']}"


CANDIDATES: List[Tuple[str, Callable[[Dict], str]]] = [
    ("before: legacy verbose", legacy_verbose),
    ("after: case_document (shipped)", case_document),
    ("rejected: tags first", tags_first),
    ("rejected: symptom only", symptom_only),
]

# ---------------------------------------------------------------------------
# Product path.
#
# The benchmark suite is single-symptom, but the flagship workflow is a
# MULTI-symptom report (spec: every reported symptom must be analysed). The two
# are not equivalent, and a representation can improve one while regressing the
# other. This check exists so that cannot happen silently again.
# ---------------------------------------------------------------------------
PRODUCT_MACHINE = {"machine_id": "EXC-001", "machine_model": "ZX210"}
PRODUCT_SYMPTOMS = [
    "Slow boom movement",
    "Weak digging force",
    "Performance worsens when hot",
]
PRODUCT_EXPECTED_COMPONENTS = ("hydraulic pump",)
PRODUCT_EXPECTED_FAILURES = ("internal pump leakage",)


def query_variants_for_product() -> List[Tuple[str, str]]:
    """Candidate ways to assemble the multi-symptom report into search text."""
    joined = "; ".join(PRODUCT_SYMPTOMS)
    machine_id = PRODUCT_MACHINE["machine_id"]
    model = PRODUCT_MACHINE["machine_model"]
    return [
        ("shipped query_text()", query_text(PRODUCT_SYMPTOMS)),
        ("symptoms only", joined),
        ("symptoms + sentence", ", ".join(PRODUCT_SYMPTOMS)),
        ("legacy 'Machine: id model | Symptoms:'",
         f"Machine: {machine_id} {model} | Symptoms: {joined}"),
    ]


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def rank_cases(index: faiss.Index, query_vec: np.ndarray, limit: int) -> List[int]:
    """Case indices ordered by descending cosine similarity."""
    _, ids = index.search(query_vec, limit)
    return [int(i) for i in ids[0] if i != -1]


def match_rank(cases: List[Dict], item: Dict, order: List[int]) -> int:
    """Rank at which the expected component or failure mode first appears."""
    for rank, case_idx in enumerate(order, start=1):
        c = cases[case_idx]
        if (item["expected_component"].lower() in c["component"].lower()
                or item["expected_failure"].lower() in c["failure_mode"].lower()):
            return rank
    return None


def top_band(index: faiss.Index, query_vec: np.ndarray, width: int = 100) -> float:
    """
    Width of the similarity band occupied by the top `width` hits.

    A collapsed representation returns a very narrow band (all hits nearly equally
    similar, so ranking is close to arbitrary); a healthy one spreads.
    """
    scores, _ = index.search(query_vec, width)
    finite = scores[0][scores[0] != -1]
    return float(finite.max() - finite.min()) if finite.size else 0.0


def main() -> None:
    cases = load_cases()
    total = len(cases)
    print(f"[eval] cases: {total}")

    embedder = SentenceTransformer(MODEL_NAME)

    # Embed every candidate's documents once. Documents are embedded bare: the
    # BGE instruction belongs on the query side only.
    texts_by_candidate: Dict[str, List[str]] = {}
    for label, builder in CANDIDATES:
        texts_by_candidate[label] = [builder(c) for c in cases]

    flat = [t for label, _ in CANDIDATES for t in texts_by_candidate[label]]
    print(f"[eval] embedding {len(flat)} candidate documents...")
    t0 = time.time()
    emb = embedder.encode(flat, normalize_embeddings=True, batch_size=64,
                          show_progress_bar=False).astype("float32")
    print(f"[eval] embedded {len(flat)} texts in {time.time() - t0:.0f}s")

    indexes: Dict[str, faiss.Index] = {}
    offset = 0
    for label, _ in CANDIDATES:
        block = emb[offset:offset + total]
        offset += total
        idx = faiss.IndexFlatIP(block.shape[1])
        idx.add(block)
        indexes[label] = idx

    # Query variants. Production applies the BGE instruction (see memory_service),
    # so that is the variant that reflects the shipped path.
    plain_queries = [i["query"] for i in BENCHMARK_TEST_SUITE]
    prefixed_queries = [embed_query(q) for q in plain_queries]

    def encode(queries: List[str]) -> List[np.ndarray]:
        vecs = embedder.encode(queries, normalize_embeddings=True).astype("float32")
        return [vecs[n:n + 1] for n in range(len(queries))]

    query_variants = [
        ("plain query", encode(plain_queries)),
        ("BGE query instruction (shipped)", encode(prefixed_queries)),
    ]

    print()
    print("=" * 104)
    print(f"{'SCHEME':46s} {'R@1':>6s} {'R@3':>6s} {'R@5':>6s} {'MRR':>6s} {'band':>7s}  per-query match rank")
    print("=" * 104)
    for label, _ in CANDIDATES:
        index = indexes[label]
        for qlabel, qvecs in query_variants:
            h1 = h3 = h5 = 0
            mrr = 0.0
            ranks = []
            bands = []
            for item, qv in zip(BENCHMARK_TEST_SUITE, qvecs):
                order = rank_cases(index, qv, 200)
                found = match_rank(cases, item, order)
                if found == 1:
                    h1 += 1
                if found and found <= 3:
                    h3 += 1
                if found and found <= 5:
                    h5 += 1
                if found:
                    mrr += 1.0 / found
                ranks.append(found)
                bands.append(top_band(index, qv))
            nn = len(BENCHMARK_TEST_SUITE)
            rank_text = " ".join(str(r if r else "-") for r in ranks)
            avg_band = sum(bands) / len(bands)
            print(f"{label[:21] + ' + ' + qlabel[:22]:46s} "
                  f"{h1/nn:6.3f} {h3/nn:6.3f} {h5/nn:6.3f} {mrr/nn:6.3f} {avg_band:7.3f}  {rank_text}")
        print("-" * 104)
    print("=" * 104)
    print("'band' = mean width of the top-100 similarity band. A narrow band means the ranking")
    print("is compressed toward arbitrary; a wider band means the representation discriminates.")
    # ---- product path: the multi-symptom report -----------------------------
    print()
    print("=" * 104)
    print("PRODUCT PATH: multi-symptom report for EXC-001")
    print(f"  symptoms: {'; '.join(PRODUCT_SYMPTOMS)}")
    print(f"  expected: Hydraulic Pump / internal pump leakage")
    print("=" * 104)
    product_q = query_variants_for_product()
    # note: the shipped query_text() intentionally carries no machine context
    # Both query encodings are measured, because the BGE instruction is documented
    # for short-query-against-long-passage retrieval and these documents are short.
    product_vecs = []
    for label, text in product_q:
        for enc, payload in (("plain", text), ("bge", embed_query(text))):
            vec = embedder.encode([payload], normalize_embeddings=True).astype("float32")
            product_vecs.append((f"{label} [{enc}]", vec))
    for label, _ in CANDIDATES:
        index = indexes[label]
        for qlabel, qv in product_vecs:
            order = rank_cases(index, qv, 5)
            comps = [cases[i]["component"] for i in order]
            hit = next(
                (r for r, i in enumerate(order, start=1)
                 if any(e in cases[i]["component"].lower() for e in PRODUCT_EXPECTED_COMPONENTS)
                 or any(e in cases[i]["failure_mode"].lower() for e in PRODUCT_EXPECTED_FAILURES)),
                None,
            )
            mark = "OK " if hit == 1 else ("r" + str(hit) if hit else "MISS")
            print(f"{label[:30]:32s} {qlabel[:34]:36s} {mark:4s} top5: {', '.join(comps)}")
        print("-" * 104)

    print()
    print("query order:")
    for n, item in enumerate(BENCHMARK_TEST_SUITE, start=1):
        print(f"  {n}. {item['query']}  ->  {item['expected_component']} / {item['expected_failure']}")


if __name__ == "__main__":
    main()
