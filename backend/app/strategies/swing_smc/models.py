from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    type: Literal["HIGH", "LOW"]
    strength: int


@dataclass
class StructureEvent:
    type: Literal["BOS", "CHOCH"]
    direction: Literal["BULLISH", "BEARISH"]
    price: float
    timestamp: datetime
    broken_swing_index: int
    confirmed: bool


@dataclass
class LiquidityLevel:
    type: Literal[
        "EQUAL_HIGH",
        "EQUAL_LOW",
        "PREVIOUS_HIGH",
        "PREVIOUS_LOW",
        "SWING_HIGH",
        "SWING_LOW",
    ]
    price: float
    strength: float
    swept: bool = False
    sweep_timestamp: datetime | None = None


@dataclass
class FairValueGap:
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    midpoint: float
    created_at: datetime
    timeframe: str
    filled: bool = False
    fill_percentage: float = 0.0


@dataclass
class OrderBlock:
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    timestamp: datetime
    source_candle_index: int
    strength: float
    mitigated: bool = False


@dataclass
class TradeSetup:
    direction: Literal["LONG", "SHORT", "NO_SIGNAL"]

    entry_low: float | None = None
    entry_high: float | None = None

    stop_loss: float | None = None

    take_profit_1: float | None = None
    take_profit_2: float | None = None
    take_profit_3: float | None = None

    risk_reward: float | None = None

    confidence: float = 0.0

    market_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"

    reasons: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)

    structure_events: list[StructureEvent] = field(default_factory=list)
    liquidity_levels: list[LiquidityLevel] = field(default_factory=list)
    fvg: FairValueGap | None = None
    order_block: OrderBlock | None = None
