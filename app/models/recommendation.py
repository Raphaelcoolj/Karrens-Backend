from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class RecommendationStatus(str):
    WATCH = "WATCH"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    VALIDATED = "VALIDATED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class Recommendation(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    symbol: str
    asset_class: str = "unknown"
    timeframe: str = ""
    direction: str = "NEUTRAL"
    score: int = 0
    quality: str = "UNKNOWN"
    status: str = "WATCH"
    trade_status: str = "NO_SETUP"

    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    rr: Optional[float] = None

    strategy: str = "advanced_smc"
    reasons: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)

    confirmation_state: str = ""
    structure_summary: str = ""
    liquidity_summary: str = ""
    poi_summary: str = ""

    htf_bias: str = "NEUTRAL"
    middle_bias: str = "NEUTRAL"
    ltf_confirmation: str = "NONE"

    bos_count: int = 0
    choch_count: int = 0
    idm_count: int = 0
    idm_swept_count: int = 0
    ifc_count: int = 0
    fvg_count: int = 0
    ob_count: int = 0
    liquidity_sweep_count: int = 0

    recommendation_fingerprint: str = ""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_analysis_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}


class RecommendationResponse(BaseModel):
    id: str = ""
    symbol: str
    asset_class: str = "unknown"
    timeframe: str = ""
    direction: str = "NEUTRAL"
    score: int = 0
    quality: str = "UNKNOWN"
    status: str = "WATCH"
    trade_status: str = "NO_SETUP"

    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    rr: Optional[float] = None

    strategy: str = "advanced_smc"
    reasons: list[str] = []
    negative_factors: list[str] = []

    confirmation_state: str = ""
    structure_summary: str = ""
    liquidity_summary: str = ""
    poi_summary: str = ""

    htf_bias: str = "NEUTRAL"
    middle_bias: str = "NEUTRAL"
    ltf_confirmation: str = "NONE"

    created_at: str = ""
    updated_at: str = ""
    expires_at: Optional[str] = None

    model_config = {"populate_by_name": True}


class RecommendationsListResponse(BaseModel):
    recommendations: list[RecommendationResponse]
    total: int
    generated_at: str


class TopRecommendationResponse(BaseModel):
    recommendation: Optional[RecommendationResponse] = None
    generated_at: str
