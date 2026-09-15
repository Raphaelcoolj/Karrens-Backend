from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


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
    strength: int = 0


@dataclass
class StructureLabel:
    type: Literal["HH", "HL", "LH", "LL"]
    index: int
    timestamp: datetime
    price: float
    confirmed: bool = False


@dataclass
class IDM:
    index: int
    timestamp: datetime
    price: float
    direction: Literal["BULLISH", "BEARISH"]
    swept: bool = False
    sweep_index: int | None = None
    sweep_timestamp: datetime | None = None


@dataclass
class StructureEvent:
    type: Literal["BOS", "CHOCH"]
    direction: Literal["BULLISH", "BEARISH"]
    price: float
    timestamp: datetime
    index: int
    confirmed: bool = True
    swept: bool = False
    sweep_index: int | None = None


@dataclass
class LiquidityLevel:
    type: Literal[
        "EQUAL_HIGH", "EQUAL_LOW",
        "PDH", "PDL",
        "ASIAN_HIGH", "ASIAN_LOW",
        "LONDON_HIGH", "LONDON_LOW",
        "NY_HIGH", "NY_LOW",
        "SESSION_HIGH", "SESSION_LOW",
        "SWING_HIGH", "SWING_LOW",
    ]
    price: float
    strength: float = 1.0
    swept: bool = False
    sweep_timestamp: datetime | None = None
    session: str | None = None


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
    source_index: int = 0


@dataclass
class OrderBlock:
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    timestamp: datetime
    source_candle_index: int
    strength: float = 0.0
    mitigated: bool = False
    ob_type: Literal["OB_IDM", "OB_EXT", "TRAP", "RAW"] = "RAW"
    has_imbalance: bool = False
    is_ifc: bool = False


@dataclass
class OrderFlow:
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    timestamp: datetime
    source_index: int
    strength: float = 0.0


@dataclass
class IFC:
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    wick_high: float
    wick_low: float
    timestamp: datetime
    index: int
    swept_liquidity: bool = False
    closes_through: bool = False


@dataclass
class EntryZone:
    type: Literal["OB_IDM", "OB_EXT", "ORDER_FLOW", "IFC", "FVG", "SMT"]
    direction: Literal["BULLISH", "BEARISH"]
    high: float
    low: float
    timestamp: datetime
    index: int
    reason: str = ""


@dataclass
class AdvancedSMCSetup:
    symbol: str = ""
    direction: Literal["LONG", "SHORT", "NO_SIGNAL"] = "NO_SIGNAL"
    market_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"

    htf_timeframe: str = ""
    middle_timeframe: str = ""
    ltf_timeframe: str = ""

    structure_state: str = ""

    bos_events: list[StructureEvent] = field(default_factory=list)
    choch_events: list[StructureEvent] = field(default_factory=list)
    idm_events: list[IDM] = field(default_factory=list)

    liquidity_levels: list[LiquidityLevel] = field(default_factory=list)
    liquidity_sweeps: list[LiquidityLevel] = field(default_factory=list)

    fvgs: list[FairValueGap] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    order_flow: list[OrderFlow] = field(default_factory=list)
    ifcs: list[IFC] = field(default_factory=list)

    poi_type: str = ""
    poi_zone: EntryZone | None = None

    entry_type: Literal["IDM_BASED", "IFC_BASED", ""] = ""
    entry_scheme: str = ""

    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None

    take_profit_1: float | None = None
    take_profit_2: float | None = None
    take_profit_3: float | None = None

    risk_reward: float | None = None

    confidence: float = 0.0

    reasons: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)

    htf_labels: list[StructureLabel] = field(default_factory=list)
    middle_labels: list[StructureLabel] = field(default_factory=list)
    ltf_labels: list[StructureLabel] = field(default_factory=list)
