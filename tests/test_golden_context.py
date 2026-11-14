"""Golden text fixtures for the analyst context builders (roadmap A3).

Each test feeds a fixed input through one of the functions that build LLM
prompt text, with the network boundary replaced by a fake, and compares the
result byte-for-byte with a file in ``tests/fixtures/golden/expected``. The
A4 refactor (fetch_* / format_* split) must keep every one of these passing.

The inputs are synthetic but shaped like the real provider responses:
deterministic OHLCV series in the Twelve Data manager's DataFrame format, a
Twelve Data quote payload, a Yahoo chart payload, StockTwits stream pages,
and trimmed HTML pages for Finviz, TipRanks, and ValueInvesting.io.

To regenerate after an intentional change to prompt text::

    $env:UPDATE_GOLDENS = '1'; uv run pytest tests/test_golden_context.py -q; Remove-Item Env:UPDATE_GOLDENS

Review the diff of ``tests/fixtures/golden/expected`` before committing.
"""
from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import pytz
import requests

from ai_trading_crew.analysts import (
    fundamental_analysis,
    market_overview,
    social,
    stock_headlines_fetcher,
    technical_indicators,
    timegpt,
)
from ai_trading_crew.config import settings

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"
INPUT_DIR = GOLDEN_DIR / "inputs"
EXPECTED_DIR = GOLDEN_DIR / "expected"
UPDATE = os.getenv("UPDATE_GOLDENS") == "1"

pytestmark = pytest.mark.usefixtures("no_credentials")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_golden(name: str, actual: str) -> None:
    """Compare ``actual`` with the stored golden, or rewrite it when UPDATE_GOLDENS=1."""
    path = EXPECTED_DIR / f"{name}.txt"
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(actual)
        return
    assert path.exists(), f"missing golden {path.name}; run with UPDATE_GOLDENS=1 to create it"
    with open(path, encoding="utf-8", newline="") as fh:
        expected = fh.read()
    assert actual == expected, f"output differs from golden {path.name}"


def read_input(name: str) -> str:
    return (INPUT_DIR / name).read_text(encoding="utf-8")


def make_ohlcv(n: int, base: float, start: str = "2026-05-04", phase: float = 0.0) -> pd.DataFrame:
    """Deterministic daily OHLCV frame in the shape TwelveDataManager returns.

    Pure arithmetic (no RNG) so the series is identical on every platform and
    library version. The index is a DatetimeIndex named ``datetime`` sorted
    ascending, with capitalised OHLCV columns, as in get_time_series_data.
    """
    dates = pd.bdate_range(start, periods=n, name="datetime")
    rows = []
    for i in range(n):
        x = i + phase
        close = round(base * (1 + 0.06 * math.sin(x / 6) + 0.002 * i + 0.015 * math.sin(x / 2.3)), 2)
        open_ = round(close * (1 - 0.006 * math.sin(x / 1.7)), 2)
        high = round(max(open_, close) * (1 + 0.004 + 0.003 * abs(math.sin(x))), 2)
        low = round(min(open_, close) * (1 - 0.004 - 0.003 * abs(math.cos(x))), 2)
        volume = int(1_000_000 + 250_000 * math.sin(x / 3) + 5_000 * i)
        rows.append((open_, high, low, close, volume))
    return pd.DataFrame(rows, index=dates, columns=["Open", "High", "Low", "Close", "Volume"])


class FakeTwelveData:
    """Stands in for the lazy ``twelve_data_manager`` singleton."""

    def __init__(self, frames: dict[str, pd.DataFrame], quotes: dict[str, dict] | None = None):
        self.frames = frames
        self.quotes = quotes or {}

    def get_time_series_data(self, symbol: str, interval: str = "1day", period: str = "4mo") -> pd.DataFrame:
        if symbol not in self.frames:
            raise ValueError(f"No data available for symbol {symbol}")
        return self.frames[symbol].copy()

    def get_quote_data(self, symbol: str) -> dict:
        return copy.deepcopy(self.quotes[symbol])


class FakeResponse:
    def __init__(self, *, text: str = "", payload: dict | None = None, status: int = 200):
        self.text = text
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error: fixture")

    def json(self) -> dict:
        return self._payload


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def test_ti_context_golden(monkeypatch):
    quote = json.loads(read_input("twelvedata_quote_AAPL.json"))
    fake = FakeTwelveData({"AAPL": make_ohlcv(140, 200.0)}, {"AAPL": quote})
    monkeypatch.setattr(technical_indicators, "twelve_data_manager", fake)

    actual = technical_indicators.get_ti_context(
        "AAPL", indicator_params=settings.TECHNICAL_INDICATOR_DEFAULTS, interval="1day", days=30
    )
    assert_golden("ti_context_AAPL", actual)


# ---------------------------------------------------------------------------
# Market overview: VIX and global markets
# ---------------------------------------------------------------------------

def _yahoo_vix_payload() -> dict:
    # Noon UTC keeps the calendar date stable for any local timezone within +/-11h,
    # because fetch_vix_historical_data converts with datetime.fromtimestamp (local time).
    days = pd.bdate_range("2026-09-21", periods=40)
    timestamps = [int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp()) for d in days]
    closes = [round(16 + 3 * math.sin(i / 4) + 0.05 * i, 2) for i in range(len(days))]
    closes[25] = None  # Yahoo sometimes returns null closes; they are dropped
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def test_vix_golden(monkeypatch):
    payload = _yahoo_vix_payload()
    monkeypatch.setattr(market_overview.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        market_overview.requests, "get", lambda url, headers=None, params=None: FakeResponse(payload=payload)
    )

    actual = market_overview.HistoricalMarketFetcher().get_vix(days=30)
    assert_golden("vix_30d", actual)


def test_global_market_golden(monkeypatch):
    frames = {
        "EUR/USD": make_ohlcv(90, 1.08, phase=1.0),
        "BTC/USD": make_ohlcv(20, 68000.0, start="2026-08-17", phase=2.0),  # short history -> WARNING branch
        "GLD": make_ohlcv(90, 245.0, phase=3.0),
        "MCHI": make_ohlcv(90, 52.0, phase=4.0),
        "INDA": make_ohlcv(90, 55.0, phase=5.0),
        # "US2Y" deliberately missing -> per-asset error branch
        "IEF": make_ohlcv(90, 94.0, phase=6.0),
        "SPY": make_ohlcv(90, 590.0, phase=7.0),
    }
    monkeypatch.setattr(market_overview, "twelve_data_manager", FakeTwelveData(frames))

    actual = market_overview.HistoricalMarketFetcher().get_global_market(days=30)
    assert_golden("global_market_30d", actual)


# ---------------------------------------------------------------------------
# StockTwits
# ---------------------------------------------------------------------------

class FakeStockTwitsConnection:
    pages: list[dict] = []
    requests_made: list[str] = []

    def __init__(self, host: str):
        self.host = host
        self._next = None

    def request(self, method: str, endpoint: str, headers=None) -> None:
        FakeStockTwitsConnection.requests_made.append(endpoint)
        index = len(FakeStockTwitsConnection.requests_made) - 1
        pages = FakeStockTwitsConnection.pages
        self._next = pages[index] if index < len(pages) else {"messages": []}

    def getresponse(self):
        body = json.dumps(self._next).encode("utf-8")
        return type("Resp", (), {"read": lambda _self: body})()


@pytest.fixture
def fake_stocktwits(monkeypatch):
    FakeStockTwitsConnection.pages = json.loads(read_input("stocktwits_AAPL_pages.json"))
    FakeStockTwitsConnection.requests_made = []
    monkeypatch.setattr(social.http.client, "HTTPSConnection", FakeStockTwitsConnection)
    return FakeStockTwitsConnection


@pytest.mark.parametrize(
    ("fetch_limit", "golden"),
    [(50, "stocktwits_AAPL_since"), (3, "stocktwits_AAPL_limit3")],
)
def test_stocktwits_context_golden(fake_stocktwits, fetch_limit, golden):
    since = pytz.timezone("US/Eastern").localize(datetime(2026, 11, 10, 0, 0, 0))
    actual = social.get_stocktwits_context("AAPL", fetch_limit, since)
    assert_golden(golden, actual)


def test_stocktwits_paginates_with_cursor(fake_stocktwits):
    since = pytz.timezone("US/Eastern").localize(datetime(2026, 11, 10, 0, 0, 0))
    social.get_stocktwits_context("AAPL", 50, since)
    assert fake_stocktwits.requests_made == [
        "/streams/symbol/AAPL.json?limit=50",
        "/streams/symbol/AAPL.json?limit=50&max=1004",
    ]


# ---------------------------------------------------------------------------
# Fundamentals (Finviz, TipRanks, ValueInvesting.io scrapes)
# ---------------------------------------------------------------------------

def _fundamental_router(failing: tuple[str, ...] = ()):
    pages = {
        "finviz.com": "finviz_AAPL.html",
        "/stock-analysis": "tipranks_analysis_AAPL.html",
        "/forecast": "tipranks_forecast_AAPL.html",
        "valueinvesting.io": "valueinvesting_AAPL.html",
    }

    def fake_get(url, headers=None, **_kwargs):
        for key, filename in pages.items():
            if key in url:
                if key in failing:
                    return FakeResponse(status=503)
                return FakeResponse(text=read_input(filename))
        raise AssertionError(f"unexpected URL in fixture: {url}")

    return fake_get


def test_fundamental_context_golden(monkeypatch):
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router())
    actual = fundamental_analysis.get_fundamental_context("AAPL")
    assert_golden("fundamental_AAPL", actual)


def test_fundamental_context_partial_failure_golden(monkeypatch):
    failing = ("/stock-analysis", "/forecast", "valueinvesting.io")
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router(failing))
    actual = fundamental_analysis.get_fundamental_context("AAPL")
    assert_golden("fundamental_AAPL_partial_failure", actual)


@pytest.mark.xfail(
    strict=True,
    raises=UnboundLocalError,
    reason="_get_finviz_data references company_name before assignment when the request fails; ROADMAP X8",
)
def test_fundamental_context_survives_finviz_failure(monkeypatch):
    monkeypatch.setattr(fundamental_analysis.requests, "get", _fundamental_router(("finviz.com",)))
    text = fundamental_analysis.get_fundamental_context("AAPL")
    assert text.startswith("Error fetching fundamental data for AAPL")


# ---------------------------------------------------------------------------
# TimeGPT
# ---------------------------------------------------------------------------

def _forecast_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": ["AAPL", "MSFT", "QQQ"],
            "ds": pd.to_datetime(["2026-11-13", "2026-11-13", "2026-11-13"]),
            "TimeGPT": [0.123456, -0.0875, 0.04],
        }
    )


@pytest.mark.parametrize(
    ("symbol", "company", "golden"),
    [("AAPL", "Apple Inc.", "timegpt_AAPL"), ("NVDA", "NVIDIA Corporation", "timegpt_missing")],
)
def test_timegpt_format_golden(symbol, company, golden):
    actual = timegpt.format_timegpt_forecast(_forecast_frame(), symbol, company)
    assert_golden(golden, actual)


# ---------------------------------------------------------------------------
# News headlines
# ---------------------------------------------------------------------------
# The four scrapers are replaced with fixed item lists, so these goldens pin
# the merge, filter, dedupe, headline clean-up, and formatting in
# fetch_stock_news and get_news_context. Per-scraper HTML parsing is X4.

_NEWS_SCRAPERS = {
    "finviz": "fetch_finviz_news",
    "tipranks": "fetch_tipranks_news",
    "seeking_alpha": "fetch_seeking_alpha_news",
    "marketwatch": "fetch_marketwatch_news",
}


def _patch_news_sources(monkeypatch, sources: dict[str, list[dict]]) -> None:
    for key, func_name in _NEWS_SCRAPERS.items():
        items = [
            stock_headlines_fetcher.NewsItem(
                headline=raw["headline"],
                url=raw["url"],
                source=raw["source"],
                published_at=datetime.fromisoformat(raw["published_at"]),
            )
            for raw in sources.get(key, [])
        ]
        monkeypatch.setattr(stock_headlines_fetcher, func_name, lambda ticker, start, _items=items: list(_items))
    monkeypatch.setattr(stock_headlines_fetcher, "get_company_name", lambda symbol: "Apple Inc.")


def test_news_context_golden(monkeypatch):
    _patch_news_sources(monkeypatch, json.loads(read_input("news_AAPL_sources.json")))
    actual = stock_headlines_fetcher.get_news_context("AAPL", "2026-11-11")
    assert_golden("news_AAPL", actual)


def test_news_context_empty_golden(monkeypatch):
    _patch_news_sources(monkeypatch, {})
    actual = stock_headlines_fetcher.get_news_context("AAPL", "2026-11-11 09:30")
    assert_golden("news_AAPL_empty", actual)
