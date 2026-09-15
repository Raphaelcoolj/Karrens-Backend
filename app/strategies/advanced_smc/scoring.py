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


def calculate_assessment_score(
    bias: str,
    has_bos: bool = False,
    has_choch: bool = False,
    idm_count: int = 0,
    idm_swept_count: int = 0,
    ifc_count: int = 0,
    ob_count: int = 0,
    fvg_count: int = 0,
    liquidity_sweep_count: int = 0,
    entry_scheme_found: bool = False,
) -> tuple[int, int, str, str]:
    if bias == "NEUTRAL":
        return (50, 50, "BALANCED", "MODERATE")

    score = 50
    opposing = 50

    if bias == "BULLISH":
        score += 10
        opposing -= 10
    elif bias == "BEARISH":
        opposing += 10
        score -= 10

    if has_bos:
        if bias == "BULLISH":
            score += 10
            opposing -= 5
        else:
            opposing += 10
            score -= 5

    if has_choch:
        if bias == "BULLISH":
            score += 8
            opposing -= 3
        else:
            opposing += 8
            score -= 3

    if idm_swept_count > 0:
        if bias == "BULLISH":
            score += 8
            opposing -= 3
        else:
            opposing += 8
            score -= 3
    elif idm_count > 0:
        if bias == "BULLISH":
            score += 4
        else:
            opposing += 4

    if ifc_count > 0:
        if bias == "BULLISH":
            score += 6
            opposing -= 2
        else:
            opposing += 6
            score -= 2

    if ob_count > 0:
        if bias == "BULLISH":
            score += 4
        else:
            opposing += 4

    if fvg_count > 0:
        if bias == "BULLISH":
            score += 3
        else:
            opposing += 3

    if liquidity_sweep_count > 0:
        if bias == "BULLISH":
            score += 5
            opposing -= 2
        else:
            opposing += 5
            score -= 2

    if entry_scheme_found:
        if bias == "BULLISH":
            score += 8
            opposing -= 5
        else:
            opposing += 8
            score -= 5

    score = max(10, min(90, score))
    opposing = max(10, min(90, opposing))

    total = score + opposing
    if total > 0:
        score = round(score * 100 / total)
        opposing = 100 - score

    if bias == "BULLISH":
        conviction = score
    elif bias == "BEARISH":
        conviction = opposing
    else:
        conviction = 50

    if conviction >= 75:
        quality = "EXTREME CONVICTION"
    elif conviction >= 65:
        quality = "HIGH CONVICTION"
    elif conviction >= 58:
        quality = "FAVOURED"
    elif conviction >= 53:
        quality = "MODERATE"
    elif conviction >= 48:
        quality = "BALANCED"
    elif conviction >= 40:
        quality = "WEAK"
    else:
        quality = "HIGH RISK"

    if score >= 60:
        label = "LONG-FAVOURED" if bias == "BULLISH" else "SHORT-FAVOURED"
    elif score <= 40:
        label = "SHORT-FAVOURED" if bias == "BULLISH" else "LONG-FAVOURED"
    else:
        label = "NEUTRAL"

    return (score, opposing, label, quality)


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
        return "INSUFFICIENT"
