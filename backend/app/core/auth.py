"""SafeBite auth — stdlib only (PBKDF2 passwords + random session tokens in SQLite)."""
import hashlib
import hmac
import re
import secrets
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core import database as db

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ITERATIONS = 200_000


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Credentials(BaseModel):
    email: str
    password: str


def _session_response(user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    db.create_session(_token_hash(token), user["id"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"]}}


@router.post("/signup")
def signup(body: Credentials):
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    try:
        user = db.create_user(email, _hash_password(body.password))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with that email already exists. Try logging in.")
    return _session_response(user)


@router.post("/login")
def login(body: Credentials):
    user = db.get_user_by_email(body.email.strip().lower())
    if not user or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Wrong email or password.")
    return _session_response(user)


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in.")
    user = db.get_user_by_token_hash(_token_hash(authorization[7:].strip()))
    if not user:
        raise HTTPException(401, "Session expired. Please log in again.")
    return user


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "email": user["email"]}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        db.delete_session(_token_hash(authorization[7:].strip()))
    return {"ok": True}