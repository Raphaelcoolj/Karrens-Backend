from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ScoringWeights:
    htf_alignment: float = 20.0
    structure_confirmation: float = 15.0
    liquidity_sweep: float = 15.0
    premium_discount: float = 10.0
    order_block: float = 10.0
    fvg: float = 10.0
    displacement: float = 10.0
    volume_confirmation: float = 5.0
    strong_rr: float = 5.0

    @property
    def maximum(self) -> float:
        return (
            self.htf_alignment
            + self.structure_confirmation
            + self.liquidity_sweep
            + self.premium_discount
            + self.order_block
            + self.fvg
            + self.displacement
            + self.volume_confirmation
            + self.strong_rr
        )


@dataclass
class ScoringInput:
    htf_aligned: bool = False
    structure_confirmed: bool = False
    liquidity_swept: bool = False
    in_preferred_zone: bool = False
    has_order_block: bool = False
    has_fvg: bool = False
    has_displacement: bool = False
    volume_confirms: bool = False
    rr_strong: bool = False


def calculate_score(
    inp: ScoringInput,
    weights: ScoringWeights | None = None,
) -> float:
    if weights is None:
        weights = ScoringWeights()

    score = 0.0

    if inp.htf_aligned:
        score += weights.htf_alignment
    if inp.structure_confirmed:
        score += weights.structure_confirmation
    if inp.liquidity_swept:
        score += weights.liquidity_sweep
    if inp.in_preferred_zone:
        score += weights.premium_discount
    if inp.has_order_block:
        score += weights.order_block
    if inp.has_fvg:
        score += weights.fvg
    if inp.has_displacement:
        score += weights.displacement
    if inp.volume_confirms:
        score += weights.volume_confirmation
    if inp.rr_strong:
        score += weights.strong_rr

    return min(score, weights.maximum)


def confidence_label(score: float) -> str:
    if score >= 85:
        return "VERY_STRONG"
    elif score >= 75:
        return "STRONG"
    elif score >= 65:
        return "MODERATE"
    elif score >= 50:
        return "WEAK"
    else:
        return "NO_SIGNAL"
