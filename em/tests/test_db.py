import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.db.mysql_client import db, hash_password, verify_password

def test_password_hashing():
    pwd = "industrial_secure_pwd_123"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_pwd", hashed) is False
    print("[PASS] Password hashing and verification passed.")

def test_database_tables():
    machines = db.execute_query("SELECT COUNT(*) as count FROM machines")
    assert machines[0]["count"] >= 5
    
    cases = db.execute_query("SELECT COUNT(*) as count FROM maintenance_cases")
    assert cases[0]["count"] >= 1000
    
    components = db.execute_query("SELECT COUNT(*) as count FROM components")
    assert components[0]["count"] >= 10
    
    print(f"[PASS] Database tables populated: {machines[0]['count']} machines, {cases[0]['count']} cases, {components[0]['count']} components.")

if __name__ == "__main__":
    print("--- Running Database & Auth Tests ---")
    test_password_hashing()
    test_database_tables()
    print("ALL DB TESTS PASSED.")
