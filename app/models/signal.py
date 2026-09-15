from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_SIGNAL = "NO SIGNAL"


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
