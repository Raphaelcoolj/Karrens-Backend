from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class MarketAssessment(BaseModel):
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL"
    score: int = 50
    opposing_score: int = 50
    label: str = "BALANCED"
    quality: str = "UNKNOWN"
    rationale: list[str] = Field(default_factory=list)


class TradeStatus(BaseModel):
    status: Literal[
        "VALIDATED",
        "WAITING_FOR_CONFIRMATION",
        "INVALIDATED",
        "INSUFFICIENT_DATA",
        "NO_SETUP",
    ] = "NO_SETUP"
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL"
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence_score: Optional[int] = None
    risk_label: str = "UNKNOWN"
    entry_type: Optional[str] = None
    entry_scheme: Optional[str] = None
    reason_code: Optional[str] = None
    reason: str = ""


class Diagnostics(BaseModel):
    data_valid: bool = False
    candle_count: int = 0
    requested_timeframe: str = ""
    htf_timeframe: str = ""
    middle_timeframe: str = ""
    ltf_timeframe: str = ""

    htf_bias: str = "NEUTRAL"
    swing_high_count: int = 0
    swing_low_count: int = 0

    bos_count: int = 0
    choch_count: int = 0
    idm_count: int = 0

    liquidity_level_count: int = 0
    liquidity_sweep_count: int = 0

    fvg_count: int = 0
    order_block_count: int = 0
    order_flow_count: int = 0
    ifc_count: int = 0

    poi_count: int = 0

    ltf_choch_count: int = 0
    ltf_idm_count: int = 0
    ltf_sweep_count: int = 0

    entry_candidates: int = 0
    rejected_candidates: int = 0

    rejection_reasons: list[str] = Field(default_factory=list)
    structure_summary: str = ""


class AdvancedSMCAnalysisResult(BaseModel):
    symbol: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    assessment: MarketAssessment = Field(default_factory=MarketAssessment)
    trade: TradeStatus = Field(default_factory=TradeStatus)
    diagnostics: Diagnostics = Field(default_factory=Diagnostics)

    structure_state: str = ""
    bias: str = "NEUTRAL"

    bos_events: list[dict] = Field(default_factory=list)
    choch_events: list[dict] = Field(default_factory=list)
    idm_events: list[dict] = Field(default_factory=list)

    liquidity_levels_detected: int = 0
    liquidity_sweeps_detected: int = 0

    fvgs_detected: int = 0
    order_blocks_detected: int = 0
    ifcs_detected: int = 0

    current_price: Optional[float] = None

    risk: dict = Field(default_factory=dict)
    invalidation_conditions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
