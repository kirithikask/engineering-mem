import re
import uuid

from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional

from backend.app.db.mysql_client import db, hash_password
from backend.app.schemas.schemas import LoginRequest, SignupRequest, TokenResponse
from backend.app.services.auth_service import authenticate_user, create_access_token, decode_access_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

VALID_ROLES = {"TECHNICIAN", "ENGINEER", "ADMIN"}

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        # Default anonymous technician role for offline convenience if token omitted
        return {"user_id": "USR-003", "username": "technician", "role": "TECHNICIAN", "full_name": "Field Technician"}
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return payload

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest):
    """Create an operator account and return a session token for it."""
    role = (req.role or "TECHNICIAN").upper()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Unknown role")

    username = req.username.strip()
    email = req.email.strip()
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{3,32}", username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 characters (letters, digits, . _ -)")

    ph = "%s" if db.use_mysql else "?"
    existing = db.execute_query(
        f"SELECT user_id FROM users WHERE username = {ph} OR email = {ph}", (username, email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already registered")

    user_id = f"USR-{uuid.uuid4().hex[:8].upper()}"
    db.execute_write(
        f"INSERT INTO users (user_id, username, email, password_hash, role, full_name) "
        f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
        (user_id, username, email, hash_password(req.password), role, req.full_name.strip() or username),
    )

    user = {"user_id": user_id, "username": username, "email": email, "role": role,
            "full_name": req.full_name.strip() or username}
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}


@router.get("/directory")
def list_operators(user: dict = Depends(get_current_user)):
    """Administrator view of registered operators. Never exposes password hashes."""
    if user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator role required")
    rows = db.execute_query(
        "SELECT user_id, username, email, role, full_name, created_at FROM users ORDER BY created_at DESC"
    )
    return {"users": rows}
