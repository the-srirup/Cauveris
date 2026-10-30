"""Database pool bootstrap for payments-gateway.

The pool size comes straight from the deployed configuration
(config/payments.toml -> [database].max_connections). During incident
CAU-9001 this was 10 while peak concurrent demand reached 35, so checkout
requests waited up to connection_timeout_ms (5000 ms) and were then
abandoned with a 503.
"""

from __future__ import annotations

import os
from pathlib import Path

import tomllib


def load_database_config(path: str | Path = "config/payments.toml") -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)["database"]


def build_pool_url(cfg: dict) -> str:
    return (
        f"{cfg['driver']}://{cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['name']}"
    )


def create_pool(cfg: dict | None = None):
    """Create the connection pool with the configured envelope."""
    cfg = cfg or load_database_config()
    # The envelope: max_connections caps how many DB connections this pod
    # holds at once. 10 was fine at 400 rps; at ~1000 rps with slow reads it
    # starves (see incident CAU-9001).
    return {
        "url": build_pool_url(cfg),
        "max_connections": int(cfg["max_connections"]),
        "connection_timeout_ms": int(cfg["connection_timeout_ms"]),
        "statement_budget_ms": int(cfg.get("statement_budget_ms", 8000)),
    }


if __name__ == "__main__":
    print(create_pool())
