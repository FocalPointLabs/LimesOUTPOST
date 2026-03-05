"""
limes_outpost.api.dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI dependency injection:
  - get_db_pool()        → psycopg2 connection pool (module singleton)
  - get_current_user()   → validates JWT, returns user row
  - get_venture_or_403() → checks venture_members, returns venture row
"""

import os
from typing import Annotated

import psycopg2
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from limes_outpost.utils.db import get_pool

# ── JWT config ───────────────────────────────────────────────
JWT_SECRET    = os.getenv("JWT_SECRET", "change-me-before-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

security = HTTPBearer()


# ─────────────────────────────────────────────────────────────
#  DB Pool
# ─────────────────────────────────────────────────────────────

def get_db_pool():
    """Returns the module-level psycopg2 connection pool."""
    return get_pool()


DBPool = Annotated[psycopg2.pool.SimpleConnectionPool, Depends(get_db_pool)]


# ─────────────────────────────────────────────────────────────
#  Current user
# ─────────────────────────────────────────────────────────────

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db_pool: DBPool,
) -> dict:
    """
    Validates the Bearer JWT and returns the user row from DB.

    Raises 401 if token is missing, expired, or tampered.
    Raises 401 if the user_id in the token doesn't exist in DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if not user_id or token_type != "access":
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Verify user still exists in DB
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at FROM public.users WHERE id = %s;",
                (user_id,)
            )
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    if not row:
        raise credentials_exception

    return {"id": str(row[0]), "email": row[1], "created_at": row[2]}


CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────
#  Venture access guard
# ─────────────────────────────────────────────────────────────

def make_venture_dep(required_role: str = "viewer"):
    """
    Returns a callable that FastAPI uses as a dependency.
    Checks venture_members for the current user and enforces role.

    Usage via the Annotated shorthands at the bottom of this file:
        async def my_route(venture_id: str, venture: AnyMember): ...
    """
    def _dep(
        venture_id: str,
        user: Annotated[dict, Depends(get_current_user)],
        db_pool: Annotated[psycopg2.pool.SimpleConnectionPool, Depends(get_db_pool)],
    ) -> dict:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT v.id, v.name, v.brand_profile, v.status,
                           v.workflow_schedule, v.timezone, vm.role
                    FROM public.ventures v
                    JOIN public.venture_members vm
                      ON vm.venture_id = v.id
                    WHERE v.id = %s
                      AND vm.user_id = %s;
                """, (venture_id, user["id"]))
                row = cur.fetchone()
        finally:
            db_pool.putconn(conn)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Venture not found or access denied.",
            )

        venture = {
            "id":                row[0],
            "name":              row[1],
            "brand_profile":     row[2],
            "status":            row[3],
            "workflow_schedule": row[4],
            "timezone":          row[5],
            "role":              row[6],
        }

        role_order = {"viewer": 0, "operator": 1}
        if role_order.get(venture["role"], -1) < role_order.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{required_role}' role.",
            )

        return venture

    return _dep


# Convenience shorthands used in routers — use as Annotated type hints
# e.g.  async def my_route(venture: AnyMember): ...
AnyMember    = Annotated[dict, Depends(make_venture_dep("viewer"))]
OperatorOnly = Annotated[dict, Depends(make_venture_dep("operator"))]