"""fetch_* / format_* split of the analysts (roadmap A4).

The golden tests in ``test_golden_context.py`` pin the prompt text through the
old ``get_*_context`` entry points. These tests cover the new halves:

* each ``fetch_*`` returns the A2 records with the expected content;
* each ``format_*`` rebuilds the golden text from those records alone,
  including after a round trip through the run store;
* for technical indicators, the new formatter matches the legacy ``TwelveTI``
  code path on data shapes the golden does not cover.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pytest
import pytz
import talib

from ai_trading_crew import models as m
from ai_trading_crew.analysts import fundamental_analysis, social, technical_indicators, timegpt
from ai_trading_crew.config import settings
from ai_trading_crew.store import RunStore
from test_golden_context import (
    EXPECTED_DIR,
    FakeTwelveData,
    _forecast_frame,
    _fundamental_router,
    make_ohlcv,
    read_input,
)

pytestmark = pytest.mark.usefixtures("no_credentials")

RUN_ID = "20261113-093000"
AS_OF = datetime(2026, 11, 13, 14, 30, tzinfo=timezone.utc)


def golden(name: str) -> str:
    with open(EXPECTED_DIR / f"{name}.txt", encoding="utf-8", newline="") as fh:
        return fh.read()


@pytest.fixture
def store(tmp_path):
    with RunStore(tmp_path / "aitc.sqlite") as s:
        s.save_manifest(m.RunManifest(run_id=RUN_ID, started_at=AS_OF, market_symbol="QQQ"))
        yield s


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_aapl(monkeypatch):
    def install(n_bars: int = 140):
        quote = json.loads(read_input("twelvedata_quote_AAPL.json"))
        fake = FakeTwelveData({"AAPL": make_ohlcv(n_bars, 200.0)}, {"AAPL": quote})
        monkeypatch.setattr(technical_indicators, "twelve_data_manager", fake)
        return fake

    return install


def test_fetch_technical_data_returns_a2_records(fake_aapl):
    fake = fake_aapl()
    td = technical_indicators.fetch_technical_data("AAPL")

    assert isinstance(td.snapshot, m.IndicatorSnapshot)
    assert all(isinstance(bar, m.PriceBar) for bar in td.bars)
    assert len(td.bars) == 140
    assert td.snapshot.as_of == td.bars[-1].ts
    assert td.snapshot.indicators == sorted(
        ["adx", "bbands", "ema", "macd", "percent_b", "rsi", "sma", "stoch", "cci",
         "sar", "stochrsi", "ichimoku", "mfi", "obv", "mom", "willr"]
    )
    # Resolved periods come from settings, falling back to the method defaults.
    assert td.params["rsi_time_period"] == settings.TECHNICAL_INDICATOR_DEFAULTS["rsi_time_period"]

    close = fake.frames["AAPL"]["Close"].astype(float).to_numpy()
    rsi = talib.RSI(close, timeperiod=td.params["rsi_time_period"])
    assert td.snapshot.latest("rsi") == float(rsi[-1])
    assert len(td.snapshot.series("rsi")) == int((~np.isnan(rsi)).sum())
    assert {p.params for p in td.snapshot.series("macd_hist")} == {"fast=12,slow=26,signal=9"}


def test_format_ti_context_matches_golden(fake_aapl):
    fake_aapl()
    td = technical_indicators.fetch_technical_data("AAPL")
    assert technical_indicators.format_ti_context(td, days=30) == golden("ti_context_AAPL")


def test_ti_text_survives_run_store_round_trip(fake_aapl, store):
    fake_aapl()
    td = technical_indicators.fetch_technical_data("AAPL")
    store.save_price_bars(RUN_ID, td.bars)
    store.save_indicator_snapshot(RUN_ID, td.snapshot)

    restored = technical_indicators.TechnicalData(
        snapshot=store.get_indicator_snapshot(RUN_ID, "AAPL"),
        bars=tuple(store.get_price_bars(RUN_ID, "AAPL")),
        quote=td.quote,
        params=td.params,
    )
    assert technical_indicators.format_ti_context(restored, days=30) == golden("ti_context_AAPL")


def test_unknown_indicator_parameter_is_rejected(fake_aapl):
    fake_aapl()
    with pytest.raises(ValueError, match="rsi_periodd"):
        technical_indicators.fetch_technical_data("AAPL", {"rsi_periodd": 14})


def _legacy_ti_context(symbol: str, params: dict, days: int) -> str:
    """The pre-A4 get_ti_context, rebuilt on the legacy TwelveTI methods."""
    ti = technical_indicators.TwelveTI(symbol, "1day")
    result = ti.fetch_all(**params)
    price, quote, header = result.pop("price"), result.pop("quote"), result.pop("technical_indicators")
    out = f"{price}\n{quote}{header}"
    out += "\n\n" + "=" * 50 + "\nHISTORICAL DATA\n" + "=" * 50 + "\n\n"
    out += ti._format_price_historical_data(ti.fetch_historical_prices(days), symbol, days) + "\n\n"

    def hist(df, name, desc):
        return ti._format_historical_data(df, name, desc, days) + "\n\n"

    df, tp = ti.fetch_historical_adx(params.get("adx_time_period", 14), days)
    out += hist(df, "ADX", f"with time_period of {tp} days")
    df, tp = ti.fetch_historical_bbands(params.get("bbands_time_period", 20), days)
    out += hist(df, "BBANDS (Middle Band)", f"with time_period of {tp} days")
    df, tp = ti.fetch_historical_ema(params.get("ema_time_period", 9), days)
    out += hist(df, "EMA", f"with time_period of {tp} days")
    df, fp, sp, sig = ti.fetch_historical_macd(params.get("macd_fast_period", 12), params.get("macd_slow_period", 26), days)
    out += hist(df, "MACD", f"with fast_period {fp}, slow_period {sp} and signal_period {sig}")
    for key, name, default, fetch in (
        ("rsi_time_period", "RSI", 14, ti.fetch_historical_rsi),
        ("sma_time_period", "SMA", 20, ti.fetch_historical_sma),
        ("cci_time_period", "CCI", 20, ti.fetch_historical_cci),
        ("mfi_time_period", "MFI", 14, ti.fetch_historical_mfi),
    ):
        df, tp = fetch(params.get(key, default), days)
        out += hist(df, name, f"with time_period of {tp} days")
    bullets = "\n".join(f"• {k}: {v}" for k, v in result.items())
    return out.replace(header + "\n", header + "\n" + bullets + "\n")


@pytest.mark.parametrize(
    ("n_bars", "days", "params"),
    [
        (140, 30, settings.TECHNICAL_INDICATOR_DEFAULTS),
        (30, 30, settings.TECHNICAL_INDICATOR_DEFAULTS),  # MACD and Ichimoku B have no value on the last bar -> "nan"
        (60, 90, settings.TECHNICAL_INDICATOR_DEFAULTS),  # fewer bars than days -> WARNING lines
        (140, 1, settings.TECHNICAL_INDICATOR_DEFAULTS),  # one-row price table -> "N/A" daily change
        (140, 10, {}),  # method defaults only
    ],
)
def test_format_ti_context_matches_legacy_path(fake_aapl, n_bars, days, params):
    fake_aapl(n_bars)
    new = technical_indicators.format_ti_context(technical_indicators.fetch_technical_data("AAPL", params), days)
    assert new == _legacy_ti_context("AAPL", params, days)


def test_short_history_prints_nan_for_missing_current_values(fake_aapl):
    fake_aapl(30)
    text = technical_indicators.format_ti_context(technical_indicators.fetch_technical_data("AAPL"), 30)
    assert "has a macd value of nan" in text


# ---------------------------------------------------------------------------
# StockTwits
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_stocktwits(monkeypatch):
    from test_golden_context import FakeStockTwitsConnection

    FakeStockTwitsConnection.pages = json.loads(read_input("stocktwits_AAPL_pages.json"))
    FakeStockTwitsConnection.requests_made = []
    monkeypatch.setattr(social.http.client, "HTTPSConnection", FakeStockTwitsConnection)


SINCE = pytz.timezone("US/Eastern").localize(datetime(2026, 11, 10, 0, 0, 0))


def test_fetch_stocktwits_sentiment_returns_snapshot(fake_stocktwits):
    snap = social.fetch_stocktwits_sentiment("AAPL", 50, SINCE, as_of=AS_OF)

    assert isinstance(snap, m.SentimentSnapshot)
    assert snap.as_of == AS_OF
    assert snap.source == "stocktwits"
    assert all(not line.startswith("- ") and not line.endswith("\n") for line in snap.messages)
    text = golden("stocktwits_AAPL_since")
    assert f"Bullish: {snap.bullish}, Bearish: {snap.bearish}, Neutral: {snap.neutral}\n" in text
    assert len(snap.messages) == text.count("\n- ") + text.startswith("- ")


@pytest.mark.parametrize(("limit", "name"), [(50, "stocktwits_AAPL_since"), (3, "stocktwits_AAPL_limit3")])
def test_format_stocktwits_sentiment_matches_golden(fake_stocktwits, store, limit, name):
    snap = social.fetch_stocktwits_sentiment("AAPL", limit, SINCE, as_of=AS_OF)
    assert social.format_stocktwits_sentiment(snap) == golden(name)

    store.save_sentiment(RUN_ID, snap)
    assert social.format_stocktwits_sentiment(store.get_sentiment(RUN_ID, "AAPL")) == golden(name)


def test_empty_message_body_keeps_its_trailing_space():
    snap = m.SentimentSnapshot(
        symbol="AAPL", as_of=AS_OF, bullish=0, bearish=0, neutral=0,
        messages=["2026-11-12 09:30:00 EST: ", "2026-11-12 09:31:00 EST: ends with colon:"],
    )
    text = social.format_stocktwits_sentiment(snap)
    assert "- 2026-11-12 09:30:00 EST: \n" in text
    assert "- 2026-11-12 09:31:00 EST: ends with colon:\n" in text


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def test_fetch_fundamentals_parses_structured_fields(monkeypatch):
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router())
    data = fundamental_analysis.fetch_fundamentals("AAPL", as_of=AS_OF)
    snap = data.snapshot

    assert isinstance(snap, m.FundamentalSnapshot)
    assert snap.as_of == AS_OF
    assert snap.metrics["P/E"] == "34.12"
    assert snap.metrics["Market Cap"] == "3301.55B"
    assert snap.analyst_consensus == "Strong Buy"
    assert (snap.price_target_low, snap.price_target_avg, snap.price_target_high) == (180.0, 240.62, 300.0)
    assert snap.intrinsic_value == 185.20
    assert len(data.sections) == 4


@pytest.mark.parametrize(
    ("failing", "name"),
    [((), "fundamental_AAPL"), (("/stock-analysis", "/forecast", "valueinvesting.io"), "fundamental_AAPL_partial_failure")],
)
def test_format_fundamental_context_matches_golden(monkeypatch, store, failing, name):
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router(failing))
    data = fundamental_analysis.fetch_fundamentals("AAPL", as_of=AS_OF)
    assert fundamental_analysis.format_fundamental_context(data) == golden(name)

    store.save_fundamentals(RUN_ID, data.snapshot)
    assert store.get_fundamentals(RUN_ID, "AAPL") == data.snapshot


def test_failed_sources_leave_snapshot_fields_empty(monkeypatch):
    failing = ("/stock-analysis", "/forecast", "valueinvesting.io")
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router(failing))
    snap = fundamental_analysis.fetch_fundamentals("AAPL", as_of=AS_OF).snapshot

    assert snap.metrics  # Finviz still answered
    assert snap.analyst_consensus is None
    assert snap.price_target_avg is None
    assert snap.intrinsic_value is None


def test_inconsistent_price_targets_are_dropped_with_a_warning(caplog):
    forecast = (
        "• **Average Price Target**: $320.00\n"
        "• **Highest Price Target**: $300.00\n"
        "• **Lowest Price Target**: $180.00\n"
        "• **Overall Rating**: Buy\n"
    )
    with caplog.at_level(logging.WARNING, logger=fundamental_analysis.__name__):
        snap = fundamental_analysis._build_fundamental_snapshot("AAPL", AS_OF, {}, forecast, "")
    assert snap.price_target_avg is None and snap.price_target_high is None
    assert snap.analyst_consensus == "Buy"
    assert "inconsistent" in caplog.text


# ---------------------------------------------------------------------------
# TimeGPT
# ---------------------------------------------------------------------------

def test_fetch_forecast_point():
    point = timegpt.fetch_forecast_point(_forecast_frame(), "AAPL")
    assert point == m.ForecastPoint(symbol="AAPL", ds=date(2026, 11, 13), predicted_return_pct=0.123456)
    assert timegpt.fetch_forecast_point(_forecast_frame(), "NVDA") is None


@pytest.mark.parametrize(
    ("symbol", "company", "name"),
    [("AAPL", "Apple Inc.", "timegpt_AAPL"), ("NVDA", "NVIDIA Corporation", "timegpt_missing")],
)
def test_format_forecast_point_matches_golden(store, symbol, company, name):
    point = timegpt.fetch_forecast_point(_forecast_frame(), symbol)
    assert timegpt.format_forecast_point(point, company) == golden(name)

    if point is not None:
        store.save_forecasts(RUN_ID, [point])
        (restored,) = store.get_forecasts(RUN_ID, symbol)
        assert timegpt.format_forecast_point(restored, company) == golden(name)
