from dataclasses import dataclass


@dataclass
class SwingSMCConfig:
    htf: str = "1D"
    structure_tf: str = "4H"
    entry_tf: str = "1H"

    swing_left: int = 2
    swing_right: int = 2

    atr_period: int = 14

    fvg_min_atr: float = 0.10

    displacement_body_atr: float = 1.2
    displacement_body_ratio: float = 0.65

    minimum_rr: float = 2.0
    strong_rr: float = 3.0

    liquidity_tolerance_atr: float = 0.10

    stop_buffer_atr: float = 0.10

    minimum_confidence: float = 50.0

    valid_timeframe_combos: list[tuple[str, str, str]] | None = None

    def __post_init__(self):
        if self.valid_timeframe_combos is None:
            self.valid_timeframe_combos = [
                ("1D", "4H", "1H"),
                ("4H", "1H", "15m"),
                ("1W", "1D", "4H"),
            ]

    def is_valid_combo(self) -> bool:
        if self.valid_timeframe_combos is None:
            return True
        return (self.htf, self.structure_tf, self.entry_tf) in self.valid_timeframe_combos
