from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ScoringWeights:
    htf_bias: float = 15.0
    structure_bos: float = 10.0
    structure_choch: float = 10.0
    idm_sweep: float = 12.0
    ifc_confirmation: float = 10.0
    order_block: float = 10.0
    fvg: float = 8.0
    liquidity_event: float = 10.0
    entry_scheme_valid: float = 10.0
    rr_quality: float = 5.0

    @property
    def maximum(self) -> float:
        return (
            self.htf_bias + self.structure_bos + self.structure_choch
            + self.idm_sweep + self.ifc_confirmation + self.order_block
            + self.fvg + self.liquidity_event + self.entry_scheme_valid
            + self.rr_quality
        )


@dataclass
class ScoringInput:
    htf_aligned: bool = False
    has_bos: bool = False
    has_choch: bool = False
    idm_swept: bool = False
    ifc_confirms: bool = False
    has_order_block: bool = False
    has_fvg: bool = False
    liquidity_event: bool = False
    entry_scheme_valid: bool = False
    rr_strong: bool = False


def calculate_score(
    inp: ScoringInput,
    weights: ScoringWeights | None = None,
) -> float:
    if weights is None:
        weights = ScoringWeights()

    score = 0.0
    if inp.htf_aligned:
        score += weights.htf_bias
    if inp.has_bos:
        score += weights.structure_bos
    if inp.has_choch:
        score += weights.structure_choch
    if inp.idm_swept:
        score += weights.idm_sweep
    if inp.ifc_confirms:
        score += weights.ifc_confirmation
    if inp.has_order_block:
        score += weights.order_block
    if inp.has_fvg:
        score += weights.fvg
    if inp.liquidity_event:
        score += weights.liquidity_event
    if inp.entry_scheme_valid:
        score += weights.entry_scheme_valid
    if inp.rr_strong:
        score += weights.rr_quality

    return min(score, weights.maximum)


def confidence_label(score: float) -> str:
    if score >= 80:
        return "VERY_STRONG"
    elif score >= 65:
        return "STRONG"
    elif score >= 50:
        return "MODERATE"
    elif score >= 35:
        return "WEAK"
    else:
        return "NO_SIGNAL"
