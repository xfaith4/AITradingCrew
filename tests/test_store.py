"""A5: the SQLite run store migrates idempotently and round-trips every A2 model."""

import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from ai_trading_crew import models as m
from ai_trading_crew.store import LATEST_VERSION, RunStore, migrate

T0 = datetime(2026, 11, 13, 14, 30, tzinfo=timezone.utc)
RUN = "20261113-143000"

EXPECTED_TABLES = {
    "runs",
    "symbol_runs",
    "price_bars",
    "indicator_points",
    "sentiment",
    "news_items",
    "fundamentals",
    "forecasts",
    "analyst_stances",
    "recommendations",
    "artifacts",
    "schema_version",
}


def _manifest(run_id=RUN, **kw):
    return m.RunManifest(
        run_id=run_id,
        started_at=T0,
        market_symbol="SPY",
        symbols=[m.SymbolStatus(symbol="SPY", state="ok"), m.SymbolStatus(symbol="AAPL", state="ok")],
        **kw,
    )


@pytest.fixture
def store(tmp_path):
    with RunStore(tmp_path / "aitc.sqlite") as s:
        s.save_manifest(_manifest())
        yield s


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_creates_file_parent_dir_and_all_tables(tmp_path):
    path = tmp_path / "nested" / "aitc.sqlite"
    RunStore(path).close()
    assert path.exists()
    assert EXPECTED_TABLES <= _tables(path)


def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "aitc.sqlite"
    for _ in range(3):
        with RunStore(path) as s:
            assert s.schema_version == LATEST_VERSION
    with sqlite3.connect(path) as conn:
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_version")]
    assert versions == list(range(1, LATEST_VERSION + 1))


def test_refuses_a_newer_schema(tmp_path):
    path = tmp_path / "aitc.sqlite"
    RunStore(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO schema_version VALUES (?, 'future')", (LATEST_VERSION + 1,))
    with pytest.raises(RuntimeError, match="newer"):
        RunStore(path)


def test_failed_migration_rolls_back(monkeypatch):
    from ai_trading_crew.store import schema

    conn = sqlite3.connect(":memory:")
    migrate(conn)
    monkeypatch.setattr(
        schema,
        "MIGRATIONS",
        schema.MIGRATIONS + [(LATEST_VERSION + 1, "CREATE TABLE half_done (x INTEGER); THIS IS NOT SQL;")],
    )
    monkeypatch.setattr(schema, "LATEST_VERSION", LATEST_VERSION + 1)
    with pytest.raises(sqlite3.Error):
        schema.migrate(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "half_done" not in tables
    assert schema.current_version(conn) == LATEST_VERSION


def test_manifest_round_trip_and_update(store):
    assert store.get_manifest(RUN) == _manifest()
    finished = _manifest(finished_at=T0 + timedelta(minutes=20))
    finished.symbols[1] = m.SymbolStatus(symbol="AAPL", state="failed", error="HTTP 429")
    store.save_manifest(finished)
    got = store.get_manifest(RUN)
    assert got == finished
    assert [s.symbol for s in got.failed] == ["AAPL"]
    assert store.get_manifest("19990101-000000") is None


def test_two_runs_same_day_stay_distinct(store):
    store.save_manifest(_manifest(run_id="20261113-160000"))
    assert store.list_run_ids() == ["20261113-160000", RUN]
    assert store.latest_run_id() == "20261113-160000"


def test_child_rows_require_the_run(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.save_recommendation(
            "20000101-000000", m.Recommendation(symbol="AAPL", signal="neutral", confidence="low", key_factors=["x"])
        )


def test_price_bars_round_trip_and_rewrite_is_idempotent(store):
    bars = [
        m.PriceBar(symbol="AAPL", ts=T0 - timedelta(days=d), open=100 + d, high=102 + d, low=99 + d, close=101 + d)
        for d in range(3)
    ]
    store.save_price_bars(RUN, bars)
    store.save_price_bars(RUN, bars)
    got = store.get_price_bars(RUN, "AAPL")
    assert got == sorted(bars, key=lambda b: b.ts)
    assert store.get_price_bars(RUN, "MSFT") == []


def test_indicator_snapshot_round_trip_and_history(store):
    def snap(run_id, rsi_values):
        points = [
            m.IndicatorPoint(symbol="NVDA", indicator="rsi", series="rsi", params="14", ts=T0 + timedelta(days=i), value=v)
            for i, v in enumerate(rsi_values)
        ]
        points.append(m.IndicatorPoint(symbol="NVDA", indicator="macd", series="macd_hist", params="12,26,9", ts=T0, value=-0.3))
        return m.IndicatorSnapshot(symbol="NVDA", as_of=T0, points=points)

    first = snap(RUN, [40.0, 55.0])
    store.save_indicator_snapshot(RUN, first)
    got = store.get_indicator_snapshot(RUN, "NVDA")
    assert sorted(got.points, key=lambda p: (p.series, p.ts)) == sorted(first.points, key=lambda p: (p.series, p.ts))
    assert got.latest("rsi") == 55.0

    store.save_manifest(_manifest(run_id="20261114-143000"))
    store.save_indicator_snapshot("20261114-143000", snap("20261114-143000", [60.0, 70.0]))
    assert [(run, value) for run, _, value in store.indicator_history("NVDA", "rsi")] == [
        (RUN, 55.0),
        ("20261114-143000", 70.0),
    ]
    assert store.get_indicator_snapshot(RUN, "MSFT") is None


def test_resaving_indicator_snapshot_replaces_old_points(store):
    old = m.IndicatorSnapshot(
        symbol="AAPL",
        as_of=T0,
        points=[m.IndicatorPoint(symbol="AAPL", indicator="adx", series="adx", params="14", ts=T0, value=20)],
    )
    new = m.IndicatorSnapshot(
        symbol="AAPL",
        as_of=T0,
        points=[m.IndicatorPoint(symbol="AAPL", indicator="rsi", series="rsi", params="14", ts=T0, value=50)],
    )
    store.save_indicator_snapshot(RUN, old)
    store.save_indicator_snapshot(RUN, new)
    assert store.get_indicator_snapshot(RUN, "AAPL").indicators == ["rsi"]


def test_sentiment_round_trip(store):
    snap = m.SentimentSnapshot(symbol="AAPL", as_of=T0, bullish=5, bearish=2, neutral=3, messages=["- 14:00: up", "- 14:05: down"])
    store.save_sentiment(RUN, snap)
    assert store.get_sentiment(RUN, "AAPL") == snap
    assert store.get_sentiment(RUN, "MSFT") is None


def test_news_round_trip_newest_first(store):
    items = [
        m.NewsItem(symbol="AAPL", headline=f"h{i}", url=f"https://example.com/{i}", source="finviz", published_at=T0 + timedelta(hours=i))
        for i in range(3)
    ]
    store.save_news(RUN, items)
    store.save_news(RUN, items[:1])
    assert store.get_news(RUN, "AAPL") == list(reversed(items))


def test_fundamentals_round_trip(store):
    snap = m.FundamentalSnapshot(
        symbol="AAPL",
        as_of=T0,
        metrics={"P/E": 31.2, "Sector": "Technology", "PEG": None},
        analyst_consensus="Moderate Buy",
        price_target_low=200,
        price_target_avg=250,
        price_target_high=300,
        intrinsic_value=180.5,
    )
    store.save_fundamentals(RUN, snap)
    assert store.get_fundamentals(RUN, "AAPL") == snap


def test_forecasts_round_trip(store):
    points = [m.ForecastPoint(symbol="AAPL", ds=date(2026, 11, 14), predicted_return_pct=0.42)]
    store.save_forecasts(RUN, points)
    store.save_forecasts(RUN, points)
    assert store.get_forecasts(RUN, "AAPL") == points


def test_stances_round_trip(store):
    stances = [
        m.AnalystStance(symbol="AAPL", analyst=kind, score=score, confidence="medium", headline=f"{kind.value} view")
        for kind, score in zip(m.AnalystKind, [-2, -1, 0, 1, 2])
    ]
    store.save_stances(RUN, stances)
    got = store.get_stances(RUN, "AAPL")
    assert sorted(got, key=lambda s: s.analyst.value) == sorted(stances, key=lambda s: s.analyst.value)


def test_recommendation_round_trip_and_score_column(store, tmp_path):
    rec = m.Recommendation(symbol="AAPL", signal="Very Bullish", confidence="high", key_factors=["beat", "guidance"])
    store.save_recommendation(RUN, rec)
    assert store.get_recommendation(RUN, "AAPL") == rec
    score = store._rows("SELECT signal_score FROM recommendations WHERE run_id = ?", (RUN,))[0][0]
    assert score == 2


def test_artifacts_by_symbol_and_run_level(store):
    store.save_artifact(RUN, "recommendation_md", "output/2026-11-13/AAPL/day_trader.md", symbol="AAPL")
    store.save_artifact(RUN, "manifest", "output/runs/20261113-143000/manifest.json")
    assert store.get_artifacts(RUN, "AAPL") == {"recommendation_md": "output/2026-11-13/AAPL/day_trader.md"}
    assert store.get_artifacts(RUN) == {"manifest": "output/runs/20261113-143000/manifest.json"}


def test_delete_run_cascades(store):
    store.save_recommendation(RUN, m.Recommendation(symbol="AAPL", signal="neutral", confidence="low", key_factors=["x"]))
    store.save_artifact(RUN, "manifest", "m.json")
    store.delete_run(RUN)
    assert store.get_manifest(RUN) is None
    assert store.get_recommendation(RUN, "AAPL") is None
    assert store.get_artifacts(RUN) == {}


def test_in_memory_store():
    with RunStore(":memory:") as s:
        s.save_manifest(_manifest())
        assert s.latest_run_id() == RUN
