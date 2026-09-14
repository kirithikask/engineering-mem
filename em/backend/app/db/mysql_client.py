import os
import sqlite3
import pymysql
import hashlib
import json
from typing import Dict, List, Any, Optional

DB_FILE = os.path.abspath("data/engineering_memory.db")
SCHEMA_FILE = os.path.abspath("database/schema.sql")

def hash_password(password: str) -> str:
    """Secure password hashing using PBKDF2 with SHA-256."""
    salt = b"EngineeringMemorySalt2026"
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return pwd_hash.hex()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

class DatabaseClient:
    def __init__(self):
        self.use_mysql = False
        self.mysql_config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DB", "engineering_memory"),
            "autocommit": True,
            "cursorclass": pymysql.cursors.DictCursor
        }
        self.check_connection()

    def check_connection(self):
        try:
            conn = pymysql.connect(
                host=self.mysql_config["host"],
                port=self.mysql_config["port"],
                user=self.mysql_config["user"],
                password=self.mysql_config["password"],
                connect_timeout=2
            )
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.mysql_config['database']}")
            conn.close()
            self.use_mysql = True
            print(f"[DB] MySQL Connected successfully on {self.mysql_config['host']}:{self.mysql_config['port']}")
        except Exception as e:
            self.use_mysql = False
            print(f"[DB] MySQL unavailable ({e}). Using local SQLite database at {DB_FILE}")
            os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
            self.init_sqlite()

    def get_connection(self):
        if self.use_mysql:
            return pymysql.connect(**self.mysql_config)
        else:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            return conn

    def init_sqlite(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if os.path.exists(SCHEMA_FILE):
            with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            # Execute statement by statement
            statements = schema_sql.split(";")
            for stmt in statements:
                if stmt.strip():
                    cursor.execute(stmt)
        conn.commit()
        conn.close()

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            if self.use_mysql:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                conn.close()
                return list(result) if result else []
            else:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                conn.close()
                return result
        except Exception as e:
            conn.close()
            print(f"[DB Error] {e}")
            return []

    def execute_write(self, query: str, params: tuple = ()) -> int:
        conn = self.get_connection()
        try:
            if self.use_mysql:
                # SQLite upsert syntax is invalid on MySQL; translate it so callers can
                # write one portable statement (as the ingestion/setup scripts do).
                query = query.replace("INSERT OR REPLACE INTO", "REPLACE INTO").replace(
                    "INSERT OR IGNORE INTO", "INSERT IGNORE INTO"
                )
                with conn.cursor() as cursor:
                    affected = cursor.execute(query, params)
                conn.commit()
                conn.close()
                return affected
            else:
                cursor = conn.cursor()
                cursor.execute(query, params)
                affected = cursor.rowcount
                conn.commit()
                conn.close()
                return affected
        except Exception as e:
            conn.close()
            print(f"[DB Write Error] {e}")
            return 0

db = DatabaseClient()
