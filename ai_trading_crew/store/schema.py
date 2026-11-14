"""Run-store schema and ordered, idempotent migrations (roadmap item A5).

Each migration runs once, inside a transaction, and records its version in
``schema_version``. Append new migrations to ``MIGRATIONS``; never edit one
that has shipped.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_V1 = """
CREATE TABLE runs (
    run_id          TEXT PRIMARY KEY,
    schema_version  INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    market_symbol   TEXT NOT NULL
);

CREATE TABLE symbol_runs (
    run_id       TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,
    state        TEXT NOT NULL,
    error        TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    PRIMARY KEY (run_id, symbol)
);

CREATE TABLE price_bars (
    run_id  TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol  TEXT NOT NULL,
    ts      TEXT NOT NULL,
    open    REAL NOT NULL,
    high    REAL NOT NULL,
    low     REAL NOT NULL,
    close   REAL NOT NULL,
    volume  REAL,
    PRIMARY KEY (run_id, symbol, ts)
);

CREATE TABLE indicator_points (
    run_id     TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol     TEXT NOT NULL,
    as_of      TEXT NOT NULL,
    interval   TEXT NOT NULL,
    indicator  TEXT NOT NULL,
    series     TEXT NOT NULL,
    params     TEXT NOT NULL,
    ts         TEXT NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (run_id, symbol, indicator, series, params, ts)
);
CREATE INDEX ix_indicator_points_symbol_series ON indicator_points (symbol, series);

CREATE TABLE sentiment (
    run_id         TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,
    source         TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    bullish        INTEGER NOT NULL,
    bearish        INTEGER NOT NULL,
    neutral        INTEGER NOT NULL,
    messages_json  TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol, source)
);

CREATE TABLE news_items (
    run_id        TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol        TEXT NOT NULL,
    url           TEXT NOT NULL,
    headline      TEXT NOT NULL,
    source        TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol, url)
);

CREATE TABLE fundamentals (
    run_id             TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol             TEXT NOT NULL,
    as_of              TEXT NOT NULL,
    metrics_json       TEXT NOT NULL,
    analyst_consensus  TEXT,
    price_target_low   REAL,
    price_target_avg   REAL,
    price_target_high  REAL,
    intrinsic_value    REAL,
    PRIMARY KEY (run_id, symbol)
);

CREATE TABLE forecasts (
    run_id                TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol                TEXT NOT NULL,
    model                 TEXT NOT NULL,
    ds                    TEXT NOT NULL,
    predicted_return_pct  REAL NOT NULL,
    horizon_days          INTEGER NOT NULL,
    PRIMARY KEY (run_id, symbol, model, ds)
);

CREATE TABLE analyst_stances (
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    analyst     TEXT NOT NULL,
    score       INTEGER NOT NULL CHECK (score BETWEEN -2 AND 2),
    confidence  TEXT NOT NULL,
    headline    TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol, analyst)
);

CREATE TABLE recommendations (
    run_id            TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol            TEXT NOT NULL,
    signal            TEXT NOT NULL,
    signal_score      INTEGER NOT NULL CHECK (signal_score BETWEEN -2 AND 2),
    confidence        TEXT NOT NULL,
    key_factors_json  TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol)
);
CREATE INDEX ix_recommendations_symbol ON recommendations (symbol);

CREATE TABLE artifacts (
    run_id  TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol  TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL,
    path    TEXT NOT NULL,
    PRIMARY KEY (run_id, symbol, kind)
);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, _V1),
]

LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration newer than the database. Returns the resulting version."""
    version = current_version(conn)
    conn.commit()
    if version > LATEST_VERSION:
        raise RuntimeError(
            f"run store schema is version {version}, newer than this code supports ({LATEST_VERSION})"
        )
    for target, script in MIGRATIONS:
        if target <= version:
            continue
        # executescript commits first, so wrap the migration in an explicit transaction
        # and roll it back if any statement fails, leaving the previous version intact.
        applied_at = datetime.now(timezone.utc).isoformat()
        try:
            conn.executescript(
                "BEGIN;\n"
                + script
                + f"\nINSERT INTO schema_version (version, applied_at) VALUES ({int(target)}, '{applied_at}');"
                + "\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        version = target
    return version
