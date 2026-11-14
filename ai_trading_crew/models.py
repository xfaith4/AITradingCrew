"""Typed records for one pipeline run (roadmap item A2).

These models are the contract between the analysts (A4 ``fetch_*`` functions),
the run store (A5), the typed recommendation (A6), per-analyst stances (A7),
and everything later releases draw from them. They hold data only: no I/O,
no network, no LLM calls, so they import without API keys.

Conventions:

* Models the pipeline builds itself use ``extra="forbid"`` so a typo in a
  field name fails loudly.
* Models an LLM fills (``AnalystStance``, ``Recommendation``) use
  ``extra="ignore"`` so a model that adds a stray key such as ``reasoning``
  still validates, and they accept human labels such as ``"Very Bullish"``.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1

RUN_ID_FORMAT = "%Y%m%d-%H%M%S"
RUN_ID_PATTERN = r"^\d{8}-\d{6}$"


def new_run_id(at: datetime) -> str:
    """Return the run ID (``YYYYMMDD-HHMMSS``) for a run started at ``at``."""
    return at.strftime(RUN_ID_FORMAT)


def _normalize_label(value: object) -> object:
    """Turn ``"Very Bullish"``, ``"very-bullish"`` or ``"VERY_BULLISH"`` into ``"very_bullish"``."""
    if isinstance(value, str):
        return re.sub(r"[\s\-]+", "_", value.strip()).lower()
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _LlmOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# --- Enums -------------------------------------------------------------------


class Signal(str, Enum):
    """The five outcomes the day-trader task is told to choose from."""

    VERY_BEARISH = "very_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    VERY_BULLISH = "very_bullish"

    @property
    def score(self) -> int:
        """The signal as an integer from -2 (very bearish) to 2 (very bullish)."""
        return _SIGNAL_SCORES[self]

    @classmethod
    def from_score(cls, score: int) -> "Signal":
        for signal, value in _SIGNAL_SCORES.items():
            if value == score:
                return signal
        raise ValueError(f"score must be between -2 and 2, got {score}")


_SIGNAL_SCORES = {
    Signal.VERY_BEARISH: -2,
    Signal.BEARISH: -1,
    Signal.NEUTRAL: 0,
    Signal.BULLISH: 1,
    Signal.VERY_BULLISH: 2,
}


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SymbolState(str, Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalystKind(str, Enum):
    """The five per-symbol summary tasks whose stance A7 extracts."""

    NEWS = "news"
    SENTIMENT = "sentiment"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    TIMEGPT = "timegpt"


# --- Run bookkeeping ---------------------------------------------------------


class SymbolStatus(_Strict):
    symbol: str = Field(min_length=1)
    state: SymbolState = SymbolState.PENDING
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _error_only_when_failed(self) -> "SymbolStatus":
        if self.state is SymbolState.FAILED and not self.error:
            raise ValueError("a failed symbol needs an error message")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at is before started_at")
        return self


class RunManifest(_Strict):
    """What ``output/runs/<run_id>/manifest.json`` holds (A8)."""

    schema_version: int = SCHEMA_VERSION
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    started_at: datetime
    finished_at: Optional[datetime] = None
    market_symbol: str = Field(min_length=1)
    symbols: list[SymbolStatus] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "RunManifest":
        seen = [status.symbol for status in self.symbols]
        duplicates = sorted({s for s in seen if seen.count(s) > 1})
        if duplicates:
            raise ValueError(f"duplicate symbols in manifest: {duplicates}")
        if self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at is before started_at")
        return self

    def status(self, symbol: str) -> SymbolStatus:
        symbol = symbol.upper()
        for status in self.symbols:
            if status.symbol == symbol:
                return status
        raise KeyError(symbol)

    @property
    def failed(self) -> list[SymbolStatus]:
        return [s for s in self.symbols if s.state is SymbolState.FAILED]


# --- Market data -------------------------------------------------------------


class PriceBar(_Strict):
    symbol: str = Field(min_length=1)
    ts: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _high_low(self) -> "PriceBar":
        if self.high < self.low:
            raise ValueError(f"high {self.high} is below low {self.low}")
        return self


class IndicatorPoint(_Strict):
    """One value of one indicator series on one bar.

    Multi-output indicators get one point per series, for example MACD as
    ``series`` ``macd``, ``macd_signal`` and ``macd_hist``; single-output
    indicators use the indicator name as the series.
    """

    symbol: str = Field(min_length=1)
    indicator: str = Field(min_length=1)
    series: str = Field(min_length=1)
    params: str = ""
    ts: datetime
    value: float


class IndicatorSnapshot(_Strict):
    symbol: str = Field(min_length=1)
    as_of: datetime
    interval: str = "1day"
    points: list[IndicatorPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _same_symbol(self) -> "IndicatorSnapshot":
        others = {p.symbol for p in self.points} - {self.symbol}
        if others:
            raise ValueError(f"points for other symbols in {self.symbol} snapshot: {sorted(others)}")
        return self

    @property
    def indicators(self) -> list[str]:
        return sorted({p.indicator for p in self.points})

    def series(self, name: str) -> list[IndicatorPoint]:
        """Points of one series, oldest first."""
        return sorted((p for p in self.points if p.series == name), key=lambda p: p.ts)

    def latest(self, name: str) -> Optional[float]:
        points = self.series(name)
        return points[-1].value if points else None


class SentimentSnapshot(_Strict):
    symbol: str = Field(min_length=1)
    as_of: datetime
    source: str = "stocktwits"
    bullish: int = Field(ge=0)
    bearish: int = Field(ge=0)
    neutral: int = Field(ge=0)
    messages: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.bullish + self.bearish + self.neutral

    @property
    def bull_ratio(self) -> Optional[float]:
        """Bullish share of messages that carry a bullish or bearish tag."""
        tagged = self.bullish + self.bearish
        return self.bullish / tagged if tagged else None


class NewsItem(_Strict):
    symbol: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    url: str = Field(min_length=1)
    source: str = Field(min_length=1)
    published_at: datetime


class FundamentalSnapshot(_Strict):
    """Scraped fundamentals. ``metrics`` keeps the Finviz table as scraped."""

    symbol: str = Field(min_length=1)
    as_of: datetime
    metrics: dict[str, Union[float, str, None]] = Field(default_factory=dict)
    analyst_consensus: Optional[str] = None
    price_target_low: Optional[float] = Field(default=None, gt=0)
    price_target_avg: Optional[float] = Field(default=None, gt=0)
    price_target_high: Optional[float] = Field(default=None, gt=0)
    intrinsic_value: Optional[float] = None

    @model_validator(mode="after")
    def _target_order(self) -> "FundamentalSnapshot":
        low, avg, high = self.price_target_low, self.price_target_avg, self.price_target_high
        if low is not None and high is not None and low > high:
            raise ValueError(f"price_target_low {low} exceeds price_target_high {high}")
        if avg is not None and low is not None and avg < low:
            raise ValueError(f"price_target_avg {avg} is below price_target_low {low}")
        if avg is not None and high is not None and avg > high:
            raise ValueError(f"price_target_avg {avg} exceeds price_target_high {high}")
        return self


class ForecastPoint(_Strict):
    """A TimeGPT forecast; ``timegpt.py`` scales the model output to percent."""

    symbol: str = Field(min_length=1)
    ds: date
    predicted_return_pct: float
    model: str = "TimeGPT"
    horizon_days: int = Field(default=1, ge=1)


# --- LLM outputs -------------------------------------------------------------


class AnalystStance(_LlmOutput):
    symbol: str = Field(min_length=1)
    analyst: AnalystKind
    score: int = Field(ge=-2, le=2)
    confidence: Confidence
    headline: str = Field(min_length=1, max_length=300)

    @field_validator("analyst", "confidence", mode="before")
    @classmethod
    def _labels(cls, value: object) -> object:
        return _normalize_label(value)

    @field_validator("headline")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("headline must be one line")
        return value

    @property
    def signal(self) -> Signal:
        return Signal.from_score(self.score)


class Recommendation(_LlmOutput):
    """The day-trader output A6 asks the LLM for."""

    symbol: str = Field(min_length=1)
    signal: Signal
    confidence: Confidence
    key_factors: list[str] = Field(min_length=1)

    @field_validator("signal", "confidence", mode="before")
    @classmethod
    def _labels(cls, value: object) -> object:
        return _normalize_label(value)

    @field_validator("key_factors")
    @classmethod
    def _non_empty_factors(cls, value: list[str]) -> list[str]:
        cleaned = [factor.strip() for factor in value if factor and factor.strip()]
        if not cleaned:
            raise ValueError("key_factors needs at least one non-empty factor")
        return cleaned


__all__ = [
    "SCHEMA_VERSION",
    "RUN_ID_FORMAT",
    "RUN_ID_PATTERN",
    "new_run_id",
    "Signal",
    "Confidence",
    "SymbolState",
    "AnalystKind",
    "SymbolStatus",
    "RunManifest",
    "PriceBar",
    "IndicatorPoint",
    "IndicatorSnapshot",
    "SentimentSnapshot",
    "NewsItem",
    "FundamentalSnapshot",
    "ForecastPoint",
    "AnalystStance",
    "Recommendation",
]
