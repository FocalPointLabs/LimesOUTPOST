"""
limes_outpost.utils.db
Singleton connection pool factory.
Populated in Phase 3 (Celery + Redis).
"""

import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

_pool = None


def get_pool(minconn: int = 1, maxconn: int = 10):
    """Returns a module-level SimpleConnectionPool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "limes_outpost_db"),
            user=os.getenv("DB_USER", "limes_outpost_user"),
            password=os.getenv("DB_PASSWORD", "limes_outpost_password"),
            port=int(os.getenv("DB_PORT", "5432")),
        )
    return _pool
