import time
from fastapi import APIRouter
from typing import Dict, Any, List
from backend.app.services.memory_service import memory_service
from backend.app.services.reasoning_service import parse_symptoms
from backend.app.services.representation import query_text

router = APIRouter(prefix="/api/benchmark", tags=["Benchmark Suite"])

BENCHMARK_TEST_SUITE = [
    {
        "query": "Slow boom movement and weak digging force",
        "expected_component": "Hydraulic Pump",
        "expected_failure": "Internal pump leakage"
    },
    {
        "query": "Hydraulic oil overheating and slow operation after shift",
        "expected_component": "Hydraulic Cooler",
        "expected_failure": "Cooler restriction"
    },
    {
        "query": "Delayed control response across all levers",
        "expected_component": "Pilot System",
        "expected_failure": "Pilot pressure problem"
    },
    {
        "query": "Jerky cylinder movements and pressure fluctuation on startup",
        "expected_component": "Accumulator",
        "expected_failure": "Accumulator pressure loss"
    },
    {
        "query": "Filter warning indicator on dashboard at high RPM",
        "expected_component": "Hydraulic Filter",
        "expected_failure": "Filter blockage"
    },
    {
        "query": "Bucket curl function completely unresponsive under load",
        "expected_component": "Main Control Valve",
        "expected_failure": "Valve problem"
    },
    {
        "query": "Arm cylinder drifts down when machine parked",
        "expected_component": "Arm Cylinder",
        "expected_failure": "Cylinder leakage"
    }
]

@router.get("")
def run_benchmark():
    start_total = time.time()
    results = []
    
    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    mrr_total = 0.0
    latencies = []
    
    for item in BENCHMARK_TEST_SUITE:
        t0 = time.time()
        # Built through the same representation the diagnosis path uses, so this
        # suite measures the real query pipeline rather than a parallel one.
        res = memory_service.search(
            query_text([item["query"]]), top_k_cases=5, top_k_chunks=2
        )
        elapsed = (time.time() - t0) * 1000 # ms
        latencies.append(elapsed)
        
        cases = res["cases"]
        found_rank = None
        
        for rank, c in enumerate(cases, start=1):
            if item["expected_component"].lower() in c["component"].lower() or item["expected_failure"].lower() in c["failure_mode"].lower():
                found_rank = rank
                break
                
        if found_rank == 1:
            top1_hits += 1
        if found_rank is not None and found_rank <= 3:
            top3_hits += 1
        if found_rank is not None and found_rank <= 5:
            top5_hits += 1
        if found_rank is not None:
            mrr_total += (1.0 / found_rank)
            
        results.append({
            "query": item["query"],
            "expected_component": item["expected_component"],
            "retrieved_top1": cases[0]["component"] if cases else "None",
            "top1_similarity": cases[0]["similarity"] if cases else 0.0,
            "match_rank": found_rank,
            "latency_ms": round(elapsed, 2)
        })
        
    n = len(BENCHMARK_TEST_SUITE)
    recall_at_1 = round(top1_hits / n, 3)
    recall_at_3 = round(top3_hits / n, 3)
    recall_at_5 = round(top5_hits / n, 3)
    mrr = round(mrr_total / n, 3)
    avg_latency = round(sum(latencies) / n, 2)
    total_time = round((time.time() - start_total), 2)

    # Only metrics measured by this suite are reported. Grounding and
    # unsupported-diagnosis rates are not evaluated here, so they are omitted
    # rather than asserted. Top-1/Top-3 accuracy is the same rank-based match as
    # Recall@1/@3, reported once under the recall keys.
    return {
        "benchmark_summary": {
            "test_cases_evaluated": n,
            "recall_at_1": recall_at_1,
            "recall_at_3": recall_at_3,
            "recall_at_5": recall_at_5,
            "mrr": mrr,
            "mean_retrieval_latency_ms": avg_latency,
            "total_execution_time_sec": total_time
        },
        "detailed_results": results
    }
