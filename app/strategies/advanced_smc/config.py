from dataclasses import dataclass, field
from typing import Literal
from datetime import time


@dataclass
class SessionConfig:
    name: str
    start: time
    end: time
    timezone: str = "UTC"


@dataclass
class AdvancedSMCConfig:
    htf: str = "1D"
    middle_tf: str = "15m"
    ltf: str = "1m"

    exit_mode: Literal["CONSERVATIVE", "AGGRESSIVE"] = "CONSERVATIVE"

    conservative_rr_min: float = 5.0
    conservative_rr_max: float = 10.0

    swing_left: int = 2
    swing_right: int = 2

    atr_period: int = 14

    fvg_min_atr: float = 0.05
    fvg_enabled: bool = True

    ob_body_atr: float = 0.8
    ob_body_ratio: float = 0.5

    ifc_wick_ratio: float = 0.6
    ifc_sweep_atr: float = 0.3

    session_liquidity_enabled: bool = True

    asian_session: SessionConfig = field(default_factory=lambda: SessionConfig(
        name="asian", start=time(0, 0), end=time(8, 0), timezone="UTC"
    ))
    london_session: SessionConfig = field(default_factory=lambda: SessionConfig(
        name="london", start=time(7, 0), end=time(16, 0), timezone="UTC"
    ))
    new_york_session: SessionConfig = field(default_factory=lambda: SessionConfig(
        name="new_york", start=time(12, 0), end=time(21, 0), timezone="UTC"
    ))

    liquidity_tolerance_atr: float = 0.10

    minimum_rr: float = 2.0

    minimum_confidence: float = 40.0

    valid_timeframe_combos: list[tuple[str, str, str]] | None = None

    def __post_init__(self):
        if self.valid_timeframe_combos is None:
            self.valid_timeframe_combos = [
                ("1D", "15m", "1m"),
                ("1D", "4H", "1H"),
                ("4H", "1H", "5m"),
                ("4H", "1H", "15m"),
                ("4H", "15m", "1m"),
                ("1W", "1D", "4H"),
                ("1W", "1D", "1H"),
                ("1D", "1H", "15m"),
                ("1D", "1H", "5m"),
                ("4H", "15m", "5m"),
                ("1H", "15m", "1m"),
                ("1H", "5m", "1m"),
            ]

    def is_valid_combo(self) -> bool:
        if self.valid_timeframe_combos is None:
            return True
        return (self.htf, self.middle_tf, self.ltf) in self.valid_timeframe_combos

    def get_timeframe_mapping(self) -> dict[str, str]:
        return {
            "htf": self.htf,
            "middle": self.middle_tf,
            "ltf": self.ltf,
        }
