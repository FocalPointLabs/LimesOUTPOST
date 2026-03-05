"""
limes_outpost.api.routers.auth
~~~~~~~~~~~~~~~~~~~~~~~~~~~
POST /auth/register
POST /auth/login
POST /auth/refresh
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.context import CryptContext

from limes_outpost.api.dependencies import DBPool, CurrentUser
from limes_outpost.api.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse,
)

router = APIRouter()

# ── Crypto ───────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET        = os.getenv("JWT_SECRET",     "change-me-before-production")
JWT_ALGORITHM     = os.getenv("JWT_ALGORITHM",  "HS256")
ACCESS_EXPIRE_MIN = int(os.getenv("JWT_ACCESS_EXPIRE_MIN",  "60"))    # 60 min
REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30")) # 30 days


def _make_token(user_id: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": user_id, "type": token_type, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _make_token_pair(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=_make_token(
            user_id, "access", timedelta(minutes=ACCESS_EXPIRE_MIN)
        ),
        refresh_token=_make_token(
            user_id, "refresh", timedelta(days=REFRESH_EXPIRE_DAYS)
        ),
    )


# ─────────────────────────────────────────────────────────────
#  Register
# ─────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(body: RegisterRequest, db_pool: DBPool):
    """Create a new user account and return token pair."""
    hashed = pwd_context.hash(body.password)

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check for duplicate email
            cur.execute(
                "SELECT id FROM public.users WHERE email = %s;",
                (body.email,)
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists.",
                )

            cur.execute(
                """
                INSERT INTO public.users (email, password_hash)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (body.email, hashed),
            )
            user_id = str(cur.fetchone()[0])
        conn.commit()
    finally:
        db_pool.putconn(conn)

    return _make_token_pair(user_id)


# ─────────────────────────────────────────────────────────────
#  Login
# ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db_pool: DBPool):
    """Authenticate and return a token pair."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, password_hash FROM public.users WHERE email = %s;",
                (body.email,)
            )
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    # Generic message — don't reveal whether email exists
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )

    if not row or not pwd_context.verify(body.password, row[1]):
        raise invalid

    user_id = str(row[0])

    # Update last_login
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.users SET last_login = NOW() WHERE id = %s;",
                (user_id,)
            )
        conn.commit()
    finally:
        db_pool.putconn(conn)

    return _make_token_pair(user_id)


# ─────────────────────────────────────────────────────────────
#  Refresh
# ─────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db_pool: DBPool):
    """Exchange a valid refresh token for a new token pair."""
    from jose import JWTError

    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )

    try:
        payload = jwt.decode(body.refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "refresh":
            raise invalid
    except JWTError:
        raise invalid

    # Verify user still exists
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE id = %s;", (user_id,))
            if not cur.fetchone():
                raise invalid
    finally:
        db_pool.putconn(conn)

    return _make_token_pair(user_id)


# ─────────────────────────────────────────────────────────────
#  Me
# ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser):
    """Return the currently authenticated user."""
    return user
