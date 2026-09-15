from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class StrategyStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class StrategyDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    source_type: str  # pdf, txt, md
    original_filename: str
    cloudinary_url: Optional[str] = None
    status: StrategyStatus = StrategyStatus.PENDING
    version: int = 1
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class StrategyChunk(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    strategy_id: str
    section: str
    content: str
    chunk_index: int
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class StrategyRules(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    strategy_id: str
    entry_rules: list[str] = []
    exit_rules: list[str] = []
    confirmation_rules: list[str] = []
    invalidation_rules: list[str] = []
    timeframe_requirements: list[str] = []
    indicators: list[str] = []
    market_structure_requirements: list[str] = []
    risk_rules: list[str] = []
    exceptions: list[str] = []
    terminology: dict = {}
    examples: list[str] = []
    raw_text: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
