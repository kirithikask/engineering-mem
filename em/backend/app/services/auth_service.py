import os
import time
from typing import Dict, Any, Optional
from jose import jwt, JWTError
from backend.app.db.mysql_client import db, verify_password

SECRET_KEY = os.getenv("JWT_SECRET", "EngineeringMemorySecretKeyOffline2026_SecureIndustrialPlatform")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400 * 7 # 7 days offline session

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = time.time() + ACCESS_TOKEN_EXPIRE_SECONDS
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    query = "SELECT user_id, username, email, password_hash, role, full_name FROM users WHERE username = %s" if db.use_mysql else "SELECT user_id, username, email, password_hash, role, full_name FROM users WHERE username = ?"
    users = db.execute_query(query, (username,))
    if not users:
        return None
    user = users[0]
    if verify_password(password, user["password_hash"]):
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "full_name": user.get("full_name", user["username"])
        }
    return None
