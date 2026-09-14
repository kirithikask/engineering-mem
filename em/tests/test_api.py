import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["offline_mode"] is True
    print("[PASS] Health endpoint returned 200 OK.")

def test_auth_endpoint():
    res = client.post("/api/auth/login", json={"username": "technician", "password": "tech_password_2026"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "TECHNICIAN"
    print("[PASS] Auth login returned valid JWT token.")

def test_machines_endpoint():
    res = client.get("/api/machines")
    assert res.status_code == 200
    data = res.json()
    assert len(data["machines"]) >= 5
    print(f"[PASS] Machines endpoint returned {len(data['machines'])} units.")

def test_cases_endpoint():
    res = client.get("/api/cases?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert len(data["cases"]) == 10
    print("[PASS] Cases endpoint returned historical maintenance cases.")

def test_documents_endpoint():
    res = client.get("/api/documents")
    assert res.status_code == 200
    data = res.json()
    assert len(data["documents"]) >= 1
    print(f"[PASS] Documents endpoint returned {len(data['documents'])} indexed manuals.")

def test_sensors_endpoint():
    res = client.get("/api/sensors/EXC-001?oil_temp=78&pressure=240")
    assert res.status_code == 200
    data = res.json()
    assert "pump_leakage_condition" in data["analysis"]
    print("[PASS] Sensors ML endpoint returned condition monitoring analysis.")

def test_benchmark_endpoint():
    res = client.get("/api/benchmark")
    assert res.status_code == 200
    data = res.json()
    assert "benchmark_summary" in data
    print(f"[PASS] Benchmark suite completed: Recall@1 = {data['benchmark_summary']['recall_at_1']}, Latency = {data['benchmark_summary']['mean_retrieval_latency_ms']} ms")

if __name__ == "__main__":
    print("--- Running FastAPI Endpoints Test Suite ---")
    test_health_endpoint()
    test_auth_endpoint()
    test_machines_endpoint()
    test_cases_endpoint()
    test_documents_endpoint()
    test_sensors_endpoint()
    test_benchmark_endpoint()
    print("ALL API ENDPOINT TESTS PASSED.")
