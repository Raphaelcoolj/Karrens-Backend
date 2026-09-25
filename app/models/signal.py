from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_SIGNAL = "NO SIGNAL"


# ---------------------------------------------------------------------------
# Directional (always-on) signal types
# ---------------------------------------------------------------------------
SignalStatus = Literal[
    "OK",
    "INSUFFICIENT_DATA",
    "MARKET_DATA_UNAVAILABLE",
    "UPSTREAM_RATE_LIMITED",
    "INVALID_SYMBOL",
    "ANALYSIS_ERROR",
]

SetupStatus = Literal[
    "DEVELOPING",
    "WAITING_FOR_CONFIRMATION",
    "PARTIALLY_CONFIRMED",
    "VALIDATED",
    "INVALIDATED",
    "NONE",
]

RiskLevel = Literal["LOW", "MODERATE", "HIGH", "VERY HIGH", "UNKNOWN"]


class DirectionalSignal(BaseModel):
    """Always-on result for one symbol/timeframe.

    Hierarchy: direction -> confidence -> setup status -> risk -> trade levels.
    ``entry``/``sl``/``tp``/``rr`` are populated only when the canonical
    strategy rules produced a fully validated setup.
    """

    status: SignalStatus = "OK"
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL"
    confidence: int = Field(default=0, ge=0, le=100)
    confidence_label: str = "VERY LOW"
    setup_status: SetupStatus = "NONE"
    risk: RiskLevel = "UNKNOWN"
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    rr: Optional[float] = None
    reasons: list[str] = []
    invalidation_conditions: list[str] = []
    bullish_score: float = 0.0
    bearish_score: float = 0.0


class SignalBase(BaseModel):
    pair: str
    timeframe: str
    direction: Direction
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: int = Field(ge=0, le=100, default=0)
    reasoning: str = ""
    triggered_conditions: list[str] = []
    invalidating_conditions: list[str] = []
    strategy_alignment: Optional[str] = None
    market_context: str = ""

    @field_validator("entry", "stop_loss", "take_profit", mode="before")
    @classmethod
    def format_price(cls, v):
        if v is None:
            return v
        return float(v)

    @field_validator("risk_reward", mode="before")
    @classmethod
    def format_rr(cls, v):
        if v is None:
            return v
        return round(float(v), 2)


class Signal(SignalBase):
    id: Optional[str] = Field(default=None, alias="_id")
    strategy_used: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class AnalysisResult(BaseModel):
    pair: str
    timeframe: str
    strategy_id: Optional[str] = None
    market_data_snapshot: dict = {}
    technical_analysis: dict = {}
    strategy_context: Optional[dict] = None
    ai_reasoning: str = ""
    signal: Optional[Signal] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    processing_time_ms: Optional[int] = None
    # Explicit non-signal status ("OK" when a direction was produced).
    data_status: str = "OK"
    directional: dict = {}
