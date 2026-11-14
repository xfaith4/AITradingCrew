"""SQLite run store: persists and reads back the A2 models (roadmap item A5).

Writes are idempotent: every table has a natural primary key, and saving the
same record twice replaces it instead of duplicating it. Child rows require
their run to exist (foreign keys are on), so call ``save_manifest`` first.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional, Union

from ai_trading_crew import models as m
from ai_trading_crew.store.schema import migrate

DEFAULT_DB_PATH = Path("output") / "aitc.sqlite"

PathLike = Union[str, Path]


def _iso(value: Optional[Union[datetime, date]]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _enum(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


class RunStore:
    """A thin, typed wrapper over one SQLite file.

    ``RunStore(":memory:")`` gives a throwaway store for tests.
    """

    def __init__(self, path: PathLike = DEFAULT_DB_PATH) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self.schema_version = migrate(self._conn)
        except Exception:
            self._conn.close()
            raise

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _write(self, sql: str, rows: Iterable[tuple]) -> None:
        with self._conn:
            self._conn.executemany(sql, list(rows))

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with closing(self._conn.execute(sql, params)) as cur:
            return cur.fetchall()

    # -- runs -----------------------------------------------------------------

    def save_manifest(self, manifest: m.RunManifest) -> None:
        """Insert or update the run row and every symbol status in it."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (run_id, schema_version, started_at, finished_at, market_symbol) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET "
                "schema_version = excluded.schema_version, started_at = excluded.started_at, "
                "finished_at = excluded.finished_at, market_symbol = excluded.market_symbol",
                (
                    manifest.run_id,
                    manifest.schema_version,
                    _iso(manifest.started_at),
                    _iso(manifest.finished_at),
                    manifest.market_symbol,
                ),
            )
            self._conn.executemany(
                "INSERT OR REPLACE INTO symbol_runs (run_id, symbol, state, error, started_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        manifest.run_id,
                        s.symbol,
                        _enum(s.state),
                        s.error,
                        _iso(s.started_at),
                        _iso(s.finished_at),
                    )
                    for s in manifest.symbols
                ],
            )

    def list_run_ids(self) -> list[str]:
        """Run IDs, newest first."""
        return [r["run_id"] for r in self._rows("SELECT run_id FROM runs ORDER BY run_id DESC")]

    def latest_run_id(self) -> Optional[str]:
        ids = self.list_run_ids()
        return ids[0] if ids else None

    def get_manifest(self, run_id: str) -> Optional[m.RunManifest]:
        runs = self._rows("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if not runs:
            return None
        run = dict(runs[0])
        statuses = [
            m.SymbolStatus(**{k: r[k] for k in ("symbol", "state", "error", "started_at", "finished_at")})
            for r in self._rows("SELECT * FROM symbol_runs WHERE run_id = ? ORDER BY rowid", (run_id,))
        ]
        return m.RunManifest(symbols=statuses, **run)

    def delete_run(self, run_id: str) -> None:
        """Remove a run and, through ON DELETE CASCADE, every row that belongs to it."""
        with self._conn:
            self._conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    # -- per-symbol data ------------------------------------------------------

    def save_price_bars(self, run_id: str, bars: Iterable[m.PriceBar]) -> None:
        self._write(
            "INSERT OR REPLACE INTO price_bars (run_id, symbol, ts, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ((run_id, b.symbol, _iso(b.ts), b.open, b.high, b.low, b.close, b.volume) for b in bars),
        )

    def get_price_bars(self, run_id: str, symbol: str) -> list[m.PriceBar]:
        rows = self._rows(
            "SELECT symbol, ts, open, high, low, close, volume FROM price_bars "
            "WHERE run_id = ? AND symbol = ? ORDER BY ts",
            (run_id, symbol),
        )
        return [m.PriceBar(**dict(r)) for r in rows]

    def save_indicator_snapshot(self, run_id: str, snapshot: m.IndicatorSnapshot) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM indicator_points WHERE run_id = ? AND symbol = ?", (run_id, snapshot.symbol)
            )
            self._conn.executemany(
                "INSERT OR REPLACE INTO indicator_points "
                "(run_id, symbol, as_of, interval, indicator, series, params, ts, value) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        p.symbol,
                        _iso(snapshot.as_of),
                        snapshot.interval,
                        p.indicator,
                        p.series,
                        p.params,
                        _iso(p.ts),
                        p.value,
                    )
                    for p in snapshot.points
                ],
            )

    def get_indicator_snapshot(self, run_id: str, symbol: str) -> Optional[m.IndicatorSnapshot]:
        """The stored snapshot, or ``None`` if it had no points (an empty snapshot is not stored)."""
        rows = self._rows(
            "SELECT * FROM indicator_points WHERE run_id = ? AND symbol = ? "
            "ORDER BY indicator, series, params, ts",
            (run_id, symbol),
        )
        if not rows:
            return None
        points = [
            m.IndicatorPoint(**{k: r[k] for k in ("symbol", "indicator", "series", "params", "ts", "value")})
            for r in rows
        ]
        return m.IndicatorSnapshot(symbol=symbol, as_of=rows[0]["as_of"], interval=rows[0]["interval"], points=points)

    def indicator_history(self, symbol: str, series: str) -> list[tuple[str, str, float]]:
        """``(run_id, ts, value)`` for the latest bar of ``series`` in every run, oldest run first.

        Answers "what was NVDA's RSI on each run" without reading Markdown.
        """
        rows = self._rows(
            "SELECT run_id, MAX(ts) AS ts, value FROM indicator_points "
            "WHERE symbol = ? AND series = ? GROUP BY run_id ORDER BY run_id",
            (symbol, series),
        )
        return [(r["run_id"], r["ts"], r["value"]) for r in rows]

    def save_sentiment(self, run_id: str, snap: m.SentimentSnapshot) -> None:
        self._write(
            "INSERT OR REPLACE INTO sentiment "
            "(run_id, symbol, source, as_of, bullish, bearish, neutral, messages_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    snap.symbol,
                    snap.source,
                    _iso(snap.as_of),
                    snap.bullish,
                    snap.bearish,
                    snap.neutral,
                    json.dumps(snap.messages),
                )
            ],
        )

    def get_sentiment(self, run_id: str, symbol: str, source: str = "stocktwits") -> Optional[m.SentimentSnapshot]:
        rows = self._rows(
            "SELECT * FROM sentiment WHERE run_id = ? AND symbol = ? AND source = ?", (run_id, symbol, source)
        )
        if not rows:
            return None
        r = rows[0]
        return m.SentimentSnapshot(
            symbol=r["symbol"],
            as_of=r["as_of"],
            source=r["source"],
            bullish=r["bullish"],
            bearish=r["bearish"],
            neutral=r["neutral"],
            messages=json.loads(r["messages_json"]),
        )

    def save_news(self, run_id: str, items: Iterable[m.NewsItem]) -> None:
        self._write(
            "INSERT OR REPLACE INTO news_items (run_id, symbol, url, headline, source, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ((run_id, n.symbol, n.url, n.headline, n.source, _iso(n.published_at)) for n in items),
        )

    def get_news(self, run_id: str, symbol: str) -> list[m.NewsItem]:
        rows = self._rows(
            "SELECT symbol, headline, url, source, published_at FROM news_items "
            "WHERE run_id = ? AND symbol = ? ORDER BY published_at DESC, url",
            (run_id, symbol),
        )
        return [m.NewsItem(**dict(r)) for r in rows]

    def save_fundamentals(self, run_id: str, snap: m.FundamentalSnapshot) -> None:
        self._write(
            "INSERT OR REPLACE INTO fundamentals (run_id, symbol, as_of, metrics_json, analyst_consensus, "
            "price_target_low, price_target_avg, price_target_high, intrinsic_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    snap.symbol,
                    _iso(snap.as_of),
                    json.dumps(snap.metrics),
                    snap.analyst_consensus,
                    snap.price_target_low,
                    snap.price_target_avg,
                    snap.price_target_high,
                    snap.intrinsic_value,
                )
            ],
        )

    def get_fundamentals(self, run_id: str, symbol: str) -> Optional[m.FundamentalSnapshot]:
        rows = self._rows("SELECT * FROM fundamentals WHERE run_id = ? AND symbol = ?", (run_id, symbol))
        if not rows:
            return None
        r = dict(rows[0])
        r.pop("run_id")
        r["metrics"] = json.loads(r.pop("metrics_json"))
        return m.FundamentalSnapshot(**r)

    def save_forecasts(self, run_id: str, points: Iterable[m.ForecastPoint]) -> None:
        self._write(
            "INSERT OR REPLACE INTO forecasts (run_id, symbol, model, ds, predicted_return_pct, horizon_days) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ((run_id, f.symbol, f.model, _iso(f.ds), f.predicted_return_pct, f.horizon_days) for f in points),
        )

    def get_forecasts(self, run_id: str, symbol: str) -> list[m.ForecastPoint]:
        rows = self._rows(
            "SELECT symbol, model, ds, predicted_return_pct, horizon_days FROM forecasts "
            "WHERE run_id = ? AND symbol = ? ORDER BY model, ds",
            (run_id, symbol),
        )
        return [m.ForecastPoint(**dict(r)) for r in rows]

    def save_stances(self, run_id: str, stances: Iterable[m.AnalystStance]) -> None:
        self._write(
            "INSERT OR REPLACE INTO analyst_stances (run_id, symbol, analyst, score, confidence, headline) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                (run_id, s.symbol, _enum(s.analyst), s.score, _enum(s.confidence), s.headline)
                for s in stances
            ),
        )

    def get_stances(self, run_id: str, symbol: str) -> list[m.AnalystStance]:
        rows = self._rows(
            "SELECT symbol, analyst, score, confidence, headline FROM analyst_stances "
            "WHERE run_id = ? AND symbol = ? ORDER BY analyst",
            (run_id, symbol),
        )
        return [m.AnalystStance(**dict(r)) for r in rows]

    def save_recommendation(self, run_id: str, rec: m.Recommendation) -> None:
        self._write(
            "INSERT OR REPLACE INTO recommendations "
            "(run_id, symbol, signal, signal_score, confidence, key_factors_json) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    rec.symbol,
                    _enum(rec.signal),
                    rec.signal.score,
                    _enum(rec.confidence),
                    json.dumps(rec.key_factors),
                )
            ],
        )

    def get_recommendation(self, run_id: str, symbol: str) -> Optional[m.Recommendation]:
        rows = self._rows("SELECT * FROM recommendations WHERE run_id = ? AND symbol = ?", (run_id, symbol))
        if not rows:
            return None
        r = rows[0]
        return m.Recommendation(
            symbol=r["symbol"],
            signal=r["signal"],
            confidence=r["confidence"],
            key_factors=json.loads(r["key_factors_json"]),
        )

    def save_artifact(self, run_id: str, kind: str, path: PathLike, symbol: str = "") -> None:
        """Record where a run's .md or .txt output lives. ``symbol=""`` marks a run-level artifact."""
        self._write(
            "INSERT OR REPLACE INTO artifacts (run_id, symbol, kind, path) VALUES (?, ?, ?, ?)",
            [(run_id, symbol, kind, Path(path).as_posix())],
        )

    def get_artifacts(self, run_id: str, symbol: Optional[str] = None) -> dict[str, str]:
        """``{kind: path}`` for one symbol, or for run-level artifacts when ``symbol`` is omitted."""
        rows = self._rows(
            "SELECT kind, path FROM artifacts WHERE run_id = ? AND symbol = ? ORDER BY kind",
            (run_id, symbol or ""),
        )
        return {r["kind"]: r["path"] for r in rows}
