from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Push subscription endpoint must use HTTPS")
        return v


class PushSubscription(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    failure_count: int = 0
    active: bool = True

    model_config = {"populate_by_name": True}


class NotificationLog(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    signal_fingerprint: str
    subscription_id: str
    notification_type: str
    symbol: str = ""
    direction: str = ""
    score: int = 0
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["sent", "failed", "expired"] = "sent"

    model_config = {"populate_by_name": True}


class NotificationPayload(BaseModel):
    type: str = "TRADING_SIGNAL"
    signal_id: str = ""
    symbol: str = ""
    direction: str = ""
    score: int = 0
    quality: str = ""
    entry: str = ""
    sl: str = ""
    tp: str = ""
    rr: str = ""
    timeframe: str = ""
    reason: str = ""


class VAPIDKeyResponse(BaseModel):
    public_key: str


class SubscribeResponse(BaseModel):
    status: str
    subscription_id: Optional[str] = None


class NotificationStatusResponse(BaseModel):
    supported: bool
    permission: str
    subscribed: bool
    subscription_id: Optional[str] = None
