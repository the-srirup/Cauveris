"""payments-gateway HTTP entrypoint (abridged) - incident CAU-9001 snapshot.

Every /v1/* handler checks a connection out of the shared pool before
running its query. When the pool is exhausted the checkout blocks until
connection_timeout_ms and then raises, which the handler maps to 503.
"""

from __future__ import annotations

import time

from .db import create_pool

pool = create_pool()


class PoolExhausted(Exception):
    """Raised when no connection could be checked out inside the deadline."""


def checkout_connection():
    deadline = pool["connection_timeout_ms"]
    waited = 0
    while waited < deadline:
        conn = _try_acquire()
        if conn is not None:
            return conn
        time.sleep(0.05)
        waited += 50
    # This is the 503 every failing request shared during the incident:
    # "connection pool exhausted ... checkout timeout after 5000 ms".
    raise PoolExhausted(
        f"connection pool exhausted after {deadline} ms "
        f"(max_connections={pool['max_connections']})"
    )


def _try_acquire():
    # Real implementation: psycopg pool.getconn() with the configured cap.
    ...


def charge(customer_id: int) -> dict:
    conn = checkout_connection()
    try:
        return {"status": "ok", "order": _query(conn, customer_id)}
    finally:
        _release(conn)


def _query(conn, customer_id: int) -> dict:
    ...


def _release(conn) -> None:
    ...
