"""A2: typed run-record models validate, reject bad data, and round-trip through JSON."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from ai_trading_crew import models as m

T0 = datetime(2026, 11, 13, 14, 30, tzinfo=timezone.utc)
T1 = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)


def _samples():
    point = m.IndicatorPoint(symbol="AAPL", indicator="macd", series="macd_hist", params="12,26,9", ts=T0, value=-0.4)
    return [
        m.RunManifest(
            run_id="20261113-143000",
            started_at=T0,
            finished_at=T1,
            market_symbol="SPY",
            symbols=[
                m.SymbolStatus(symbol="spy", state="ok"),
                m.SymbolStatus(symbol="AAPL", state="failed", error="HTTP 429"),
            ],
        ),
        m.PriceBar(symbol="AAPL", ts=T0, open=230.1, high=232.0, low=229.5, close=231.2, volume=5_000_000),
        m.IndicatorSnapshot(symbol="AAPL", as_of=T0, points=[point]),
        m.SentimentSnapshot(symbol="AAPL", as_of=T0, bullish=12, bearish=4, neutral=9, messages=["- 14:00: up"]),
        m.NewsItem(symbol="AAPL", headline="Apple beats", url="https://example.com/a", source="finviz", published_at=T0),
        m.FundamentalSnapshot(
            symbol="AAPL",
            as_of=T0,
            metrics={"P/E": 31.2, "Sector": "Technology", "PEG": None},
            analyst_consensus="Moderate Buy",
            price_target_low=200,
            price_target_avg=250,
            price_target_high=300,
        ),
        m.ForecastPoint(symbol="AAPL", ds=date(2026, 11, 14), predicted_return_pct=0.42),
        m.AnalystStance(symbol="AAPL", analyst="technical", score=1, confidence="medium", headline="RSI rising"),
        m.Recommendation(symbol="AAPL", signal="bullish", confidence="high", key_factors=["earnings beat"]),
    ]


@pytest.mark.parametrize("model", _samples(), ids=lambda obj: type(obj).__name__)
def test_json_round_trip(model):
    restored = type(model).model_validate_json(model.model_dump_json())
    assert restored == model


def test_new_run_id_format():
    assert m.new_run_id(datetime(2026, 1, 2, 3, 4, 5)) == "20260102-030405"


@pytest.mark.parametrize("bad", ["2026-11-13", "20261113", "20261113-1430", "x20261113-143000"])
def test_run_id_rejects_bad_format(bad):
    with pytest.raises(ValidationError):
        m.RunManifest(run_id=bad, started_at=T0, market_symbol="SPY")


def test_manifest_status_lookup_and_failed():
    manifest = _samples()[0]
    assert manifest.status("spy").state is m.SymbolState.OK
    assert [s.symbol for s in manifest.failed] == ["AAPL"]
    with pytest.raises(KeyError):
        manifest.status("MSFT")


def test_manifest_rejects_duplicate_symbols():
    with pytest.raises(ValidationError, match="duplicate"):
        m.RunManifest(
            run_id="20261113-143000",
            started_at=T0,
            market_symbol="SPY",
            symbols=[m.SymbolStatus(symbol="AAPL"), m.SymbolStatus(symbol="aapl")],
        )


def test_manifest_rejects_finish_before_start():
    with pytest.raises(ValidationError, match="before"):
        m.RunManifest(run_id="20261113-143000", started_at=T1, finished_at=T0, market_symbol="SPY")


def test_failed_status_needs_error():
    with pytest.raises(ValidationError, match="error message"):
        m.SymbolStatus(symbol="AAPL", state="failed")


def test_strict_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        m.PriceBar(symbol="AAPL", ts=T0, open=1, high=2, low=1, close=1.5, vwap=1.4)


def test_price_bar_rejects_high_below_low():
    with pytest.raises(ValidationError, match="below low"):
        m.PriceBar(symbol="AAPL", ts=T0, open=1, high=1, low=2, close=1.5)


def test_price_bar_rejects_non_positive_price():
    with pytest.raises(ValidationError):
        m.PriceBar(symbol="AAPL", ts=T0, open=0, high=2, low=1, close=1.5)


def test_indicator_snapshot_series_and_latest():
    pts = [
        m.IndicatorPoint(symbol="AAPL", indicator="rsi", series="rsi", params="14", ts=T1, value=61.0),
        m.IndicatorPoint(symbol="AAPL", indicator="rsi", series="rsi", params="14", ts=T0, value=55.0),
        m.IndicatorPoint(symbol="AAPL", indicator="macd", series="macd", params="12,26,9", ts=T0, value=1.1),
    ]
    snap = m.IndicatorSnapshot(symbol="AAPL", as_of=T1, points=pts)
    assert [p.value for p in snap.series("rsi")] == [55.0, 61.0]
    assert snap.latest("rsi") == 61.0
    assert snap.latest("adx") is None
    assert snap.indicators == ["macd", "rsi"]


def test_indicator_snapshot_rejects_other_symbols():
    stray = m.IndicatorPoint(symbol="MSFT", indicator="rsi", series="rsi", ts=T0, value=50)
    with pytest.raises(ValidationError, match="other symbols"):
        m.IndicatorSnapshot(symbol="AAPL", as_of=T0, points=[stray])


def test_sentiment_totals_and_ratio():
    snap = m.SentimentSnapshot(symbol="AAPL", as_of=T0, bullish=3, bearish=1, neutral=6)
    assert snap.total == 10
    assert snap.bull_ratio == 0.75
    assert m.SentimentSnapshot(symbol="AAPL", as_of=T0, bullish=0, bearish=0, neutral=5).bull_ratio is None


def test_sentiment_rejects_negative_counts():
    with pytest.raises(ValidationError):
        m.SentimentSnapshot(symbol="AAPL", as_of=T0, bullish=-1, bearish=0, neutral=0)


def test_fundamental_rejects_inverted_targets():
    with pytest.raises(ValidationError, match="exceeds"):
        m.FundamentalSnapshot(symbol="AAPL", as_of=T0, price_target_low=300, price_target_high=200)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Very Bearish", m.Signal.VERY_BEARISH),
        ("bearish", m.Signal.BEARISH),
        ("NEUTRAL", m.Signal.NEUTRAL),
        (" Bullish ", m.Signal.BULLISH),
        ("very-bullish", m.Signal.VERY_BULLISH),
    ],
)
def test_recommendation_accepts_human_signal_labels(label, expected):
    rec = m.Recommendation(symbol="AAPL", signal=label, confidence="High", key_factors=["x"])
    assert rec.signal is expected
    assert rec.confidence is m.Confidence.HIGH


def test_recommendation_from_llm_json_ignores_extra_keys():
    raw = (
        '{"symbol": "AAPL", "signal": "Very Bullish", "confidence": "medium",'
        ' "key_factors": ["beat", "  ", "guidance up"], "reasoning": "long text"}'
    )
    rec = m.Recommendation.model_validate_json(raw)
    assert rec.signal is m.Signal.VERY_BULLISH
    assert rec.key_factors == ["beat", "guidance up"]


@pytest.mark.parametrize("factors", [[], ["", "   "]])
def test_recommendation_needs_key_factors(factors):
    with pytest.raises(ValidationError):
        m.Recommendation(symbol="AAPL", signal="neutral", confidence="low", key_factors=factors)


def test_recommendation_rejects_unknown_signal():
    with pytest.raises(ValidationError):
        m.Recommendation(symbol="AAPL", signal="Strong Buy", confidence="low", key_factors=["x"])


def test_signal_scores_round_trip():
    assert [s.score for s in m.Signal] == [-2, -1, 0, 1, 2]
    for signal in m.Signal:
        assert m.Signal.from_score(signal.score) is signal
    with pytest.raises(ValueError):
        m.Signal.from_score(3)


@pytest.mark.parametrize("score", [-3, 3])
def test_stance_score_range(score):
    with pytest.raises(ValidationError):
        m.AnalystStance(symbol="AAPL", analyst="news", score=score, confidence="low", headline="h")


def test_stance_headline_must_be_one_line():
    with pytest.raises(ValidationError, match="one line"):
        m.AnalystStance(symbol="AAPL", analyst="news", score=0, confidence="low", headline="a\nb")


def test_stance_signal_and_label_normalization():
    stance = m.AnalystStance(symbol="AAPL", analyst="TimeGPT", score=-2, confidence="Low", headline="drop")
    assert stance.analyst is m.AnalystKind.TIMEGPT
    assert stance.signal is m.Signal.VERY_BEARISH


def test_models_module_needs_no_api_keys(monkeypatch):
    import importlib
    import sys

    for key in ("OPENROUTER_API_KEY", "TWELVE_API_KEY", "RAPID_API_KEY", "TIMEGPT_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    sys.modules.pop("ai_trading_crew.models", None)
    module = importlib.import_module("ai_trading_crew.models")
    assert module.SCHEMA_VERSION == 1
