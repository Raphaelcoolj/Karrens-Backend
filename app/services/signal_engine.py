"""Deterministic directional signal engine for Karren.

Philosophy
----------
Karren is an always-on directional market intelligence system.  Whenever
sufficient market data exists it must answer with ``LONG`` or ``SHORT`` --
never with a silent "no setup".  The canonical Advanced SMC detectors stay
authoritative; their output is consumed here as *evidence* rather than as an
on/off switch.

The hierarchy of a result is::

    DIRECTION  ->  CONFIDENCE  ->  SETUP STATUS  ->  RISK  ->  TRADE LEVELS

Key invariants:

* The engine is **deterministic**: identical candles + identical configuration
  always produce the same direction, confidence, setup status, risk and
  reasons.  No LLM is involved.
* Scoring is **bipolar**: every component can add evidence to *both* sides, so
  conflicting evidence lowers confidence instead of being ignored.
* Confidence is a **directional conviction score (0-100)**, not a calibrated
  probability of profit.
* Entry / SL / TP / RR are exposed **only** when the canonical strategy rules
  produced a fully validated setup.  Nothing is ever fabricated.
* Evidence is derived exclusively from candles at or before the analysis
  timestamp (no lookahead).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

from app.core.thresholds import SignalThresholds, get_thresholds
from app.models.signal import DirectionalSignal, SetupStatus, SignalStatus

# ---------------------------------------------------------------------------
# Data / failure statuses
# ---------------------------------------------------------------------------
STATUS_OK: SignalStatus = "OK"
STATUS_INSUFFICIENT_DATA: SignalStatus = "INSUFFICIENT_DATA"
STATUS_MARKET_DATA_UNAVAILABLE: SignalStatus = "MARKET_DATA_UNAVAILABLE"
STATUS_UPSTREAM_RATE_LIMITED: SignalStatus = "UPSTREAM_RATE_LIMITED"
STATUS_INVALID_SYMBOL: SignalStatus = "INVALID_SYMBOL"
STATUS_ANALYSIS_ERROR: SignalStatus = "ANALYSIS_ERROR"

DATA_FAILURE_STATUSES: tuple[str, ...] = (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MARKET_DATA_UNAVAILABLE,
    STATUS_UPSTREAM_RATE_LIMITED,
    STATUS_INVALID_SYMBOL,
    STATUS_ANALYSIS_ERROR,
)

# Strategy rejection codes that mean "the data itself was unusable" - in these
# cases no direction may be manufactured.
DATA_FAILURE_REJECTIONS = frozenset(
    {"INSUFFICIENT_DATA", "NO_STRUCTURE", "ATR_ZERO", "TIMEFRAME_INVALID"}
)

# Rejection codes that mean a candidate setup was produced but rejected by the
# canonical validation rules.
SETUP_REJECTED_REJECTIONS = frozenset({"INVALID_RR", "LOW_CONFIDENCE"})

Side = Literal["BULLISH", "BEARISH"]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceWeights:
    """Bipolar evidence weights.

    Each field is the weight contributed to *one* side when the corresponding
    evidence is detected in that direction.  ``max_events`` caps how many
    individual events of a kind may contribute so that counting cannot inflate
    the score without bound.
    """

    htf_bias: float = 15.0
    middle_bias: float = 12.0
    ltf_bias: float = 8.0

    bos_event: float = 7.0
    bos_max_events: int = 2
    choch_event: float = 6.0
    choch_max_events: int = 2
    idm_swept: float = 6.0
    idm_max_events: int = 2
    liquidity_sweep: float = 5.0
    liquidity_max_events: int = 2
    ifc: float = 5.0
    ifc_max_events: int = 2
    order_block: float = 3.0
    ob_max_events: int = 2
    fvg: float = 2.0
    fvg_max_events: int = 2
    entry_scheme: float = 8.0

    # Existing technical-analysis evidence (app.analysis.engine only)
    trend_structure: float = 6.0
    ema_alignment: float = 4.0
    rsi_extreme: float = 3.0
    price_momentum: float = 4.0
    macd_crossover: float = 3.0


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    side: Side
    weight: float


@dataclass
class EvidenceSummary:
    bullish: float = 0.0
    bearish: float = 0.0
    items: list[EvidenceItem] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.bullish + self.bearish

    @property
    def net(self) -> float:
        return self.bullish - self.bearish


# Liquidity level types whose sweep is a bullish (sell-side) sweep.
_BULLISH_SWEEP_TYPES = frozenset(
    {"EQUAL_LOW", "PDL", "ASIAN_LOW", "LONDON_LOW", "NY_LOW", "SESSION_LOW", "SWING_LOW"}
)
_BEARISH_SWEEP_TYPES = frozenset(
    {"EQUAL_HIGH", "PDH", "ASIAN_HIGH", "LONDON_HIGH", "NY_HIGH", "SESSION_HIGH", "SWING_HIGH"}
)


def _bias_side(bias: str) -> Optional[Side]:
    if bias == "BULLISH":
        return "BULLISH"
    if bias == "BEARISH":
        return "BEARISH"
    return None


def collect_evidence(
    setup=None,
    technical_analysis: Optional[dict] = None,
    weights: Optional[EvidenceWeights] = None,
) -> EvidenceSummary:
    """Gather bipolar directional evidence from Advanced SMC + technical analysis."""
    w = weights or EvidenceWeights()
    summary = EvidenceSummary()

    def add(label: str, side: Side, weight: float) -> None:
        if weight <= 0:
            return
        summary.items.append(EvidenceItem(label=label, side=side, weight=weight))
        if side == "BULLISH":
            summary.bullish += weight
        else:
            summary.bearish += weight

    # --- Higher timeframe -------------------------------------------------
    if setup is not None:
        htf_side = _bias_side(getattr(setup, "htf_bias", "NEUTRAL") or "NEUTRAL")
        if htf_side:
            add(
                f"HTF ({getattr(setup, 'htf_timeframe', '') or 'HTF'}) "
                f"{'bullish' if htf_side == 'BULLISH' else 'bearish'} structure",
                htf_side,
                w.htf_bias,
            )

        # --- Middle timeframe structure -----------------------------------
        middle_side = _bias_side(getattr(setup, "market_bias", "NEUTRAL") or "NEUTRAL")
        if middle_side:
            add(
                f"Middle-TF {'bullish' if middle_side == 'BULLISH' else 'bearish'} structure",
                middle_side,
                w.middle_bias,
            )

        # --- Lower timeframe structure -------------------------------------
        ltf_side = _bias_side(getattr(setup, "ltf_bias", "NEUTRAL") or "NEUTRAL")
        if ltf_side:
            add(
                f"LTF {'bullish' if ltf_side == 'BULLISH' else 'bearish'} structure",
                ltf_side,
                w.ltf_bias,
            )

        # --- BOS / CHoCH ----------------------------------------------------
        bos_events = list(getattr(setup, "bos_events", []) or [])
        bos_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for event in bos_events:
            side = _bias_side(getattr(event, "direction", "NEUTRAL"))
            if side and bos_count[side] < w.bos_max_events:
                bos_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} BOS confirmed",
                    side,
                    w.bos_event,
                )

        choch_events = list(getattr(setup, "choch_events", []) or [])
        choch_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for event in choch_events:
            side = _bias_side(getattr(event, "direction", "NEUTRAL"))
            if side and choch_count[side] < w.choch_max_events:
                choch_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} CHoCH confirmed",
                    side,
                    w.choch_event,
                )

        # --- IDM sweeps -----------------------------------------------------
        idm_events = list(getattr(setup, "idm_events", []) or [])
        idm_swept_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        pending_idm: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for idm in idm_events:
            side = _bias_side(getattr(idm, "direction", "NEUTRAL"))
            if not side:
                continue
            if getattr(idm, "swept", False):
                if idm_swept_count[side] < w.idm_max_events:
                    idm_swept_count[side] += 1
                    add(
                        f"{'Bullish' if side == 'BULLISH' else 'Bearish'} IDM liquidity swept",
                        side,
                        w.idm_swept,
                    )
            else:
                pending_idm[side] += 1
        summary._pending_idm = pending_idm  # type: ignore[attr-defined]

        # --- Liquidity sweeps ------------------------------------------------
        sweeps = list(getattr(setup, "liquidity_sweeps", []) or [])
        sweep_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for level in sweeps:
            level_type = getattr(level, "type", "")
            if level_type in _BULLISH_SWEEP_TYPES:
                side: Side = "BULLISH"
            elif level_type in _BEARISH_SWEEP_TYPES:
                side = "BEARISH"
            else:
                continue
            if sweep_count[side] < w.liquidity_max_events:
                sweep_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} liquidity sweep ({level_type})",
                    side,
                    w.liquidity_sweep,
                )
        summary._sweep_side = max(sweep_count, key=sweep_count.get) if any(sweep_count.values()) else None  # type: ignore[attr-defined]

        # --- IFC -------------------------------------------------------------
        ifcs = list(getattr(setup, "ifcs", []) or [])
        ifc_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for ifc in ifcs:
            side = _bias_side(getattr(ifc, "direction", "NEUTRAL"))
            if side and ifc_count[side] < w.ifc_max_events:
                ifc_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} IFC confirmation",
                    side,
                    w.ifc,
                )

        # --- POI: order blocks / FVGs ---------------------------------------
        ob_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for ob in getattr(setup, "order_blocks", []) or []:
            if getattr(ob, "mitigated", False):
                continue
            side = _bias_side(getattr(ob, "direction", "NEUTRAL"))
            if side and ob_count[side] < w.ob_max_events:
                ob_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} order block at POI",
                    side,
                    w.order_block,
                )

        fvg_count: dict[str, int] = {"BULLISH": 0, "BEARISH": 0}
        for fvg in getattr(setup, "fvgs", []) or []:
            if getattr(fvg, "filled", False):
                continue
            side = _bias_side(getattr(fvg, "direction", "NEUTRAL"))
            if side and fvg_count[side] < w.fvg_max_events:
                fvg_count[side] += 1
                add(
                    f"{'Bullish' if side == 'BULLISH' else 'Bearish'} fair value gap",
                    side,
                    w.fvg,
                )

        # --- Valid entry scheme ----------------------------------------------
        entry_scheme = getattr(setup, "entry_scheme", "") or ""
        if entry_scheme:
            zone = getattr(setup, "poi_zone", None)
            zone_side = _bias_side(getattr(zone, "direction", "NEUTRAL")) if zone else None
            if zone_side is None:
                zone_side = "BULLISH" if getattr(setup, "direction", "") == "LONG" else "BEARISH"
            add(f"Valid entry scheme ({entry_scheme})", zone_side, w.entry_scheme)

    # --- Existing technical analysis (momentum / price structure) ----------
    if technical_analysis and "error" not in technical_analysis:
        structure = (technical_analysis.get("market_structure") or {}).get("structure")
        if structure == "bullish":
            add("Technical structure bullish", "BULLISH", w.trend_structure)
        elif structure == "bearish":
            add("Technical structure bearish", "BEARISH", w.trend_structure)

        momentum = technical_analysis.get("momentum") or {}
        ema_alignment = momentum.get("ema_alignment")
        if ema_alignment == "bullish":
            add("EMA alignment bullish", "BULLISH", w.ema_alignment)
        elif ema_alignment == "bearish":
            add("EMA alignment bearish", "BEARISH", w.ema_alignment)

        rsi_zone = momentum.get("rsi_zone")
        if rsi_zone == "oversold":
            add("RSI in oversold zone", "BULLISH", w.rsi_extreme)
        elif rsi_zone == "overbought":
            add("RSI in overbought zone", "BEARISH", w.rsi_extreme)

        macd_cross = momentum.get("macd_crossover")
        if macd_cross == "bullish":
            add("MACD crossover bullish", "BULLISH", w.macd_crossover)
        elif macd_cross == "bearish":
            add("MACD crossover bearish", "BEARISH", w.macd_crossover)

        price_change = technical_analysis.get("price_change_20")
        if isinstance(price_change, (int, float)) and price_change != 0:
            if price_change > 0:
                add("Price rising over last 20 candles", "BULLISH", w.price_momentum)
            else:
                add("Price falling over last 20 candles", "BEARISH", w.price_momentum)

    return summary


# ---------------------------------------------------------------------------
# Direction + confidence
# ---------------------------------------------------------------------------
def choose_direction(
    summary: EvidenceSummary,
    setup=None,
    technical_analysis: Optional[dict] = None,
) -> str:
    """Pick the strongest direction.  With sufficient data this is never neutral."""
    if summary.bullish > summary.bearish:
        return "LONG"
    if summary.bearish > summary.bullish:
        return "SHORT"

    # Balanced (or empty) evidence: deterministic tie-breakers, most
    # significant first.  The direction may be weak, but it is still a
    # direction - confidence reflects the lack of conviction.
    if setup is not None:
        for bias_field in ("htf_bias", "market_bias", "ltf_bias"):
            bias = getattr(setup, bias_field, "NEUTRAL") or "NEUTRAL"
            if bias == "BULLISH":
                return "LONG"
            if bias == "BEARISH":
                return "SHORT"

    if technical_analysis and "error" not in technical_analysis:
        structure = (technical_analysis.get("market_structure") or {}).get("structure")
        if structure == "bullish":
            return "LONG"
        if structure == "bearish":
            return "SHORT"
        price_change = technical_analysis.get("price_change_20")
        if isinstance(price_change, (int, float)) and price_change != 0:
            return "LONG" if price_change > 0 else "SHORT"

    return "LONG"


def compute_confidence(
    bullish: float,
    bearish: float,
    thresholds: Optional[SignalThresholds] = None,
) -> int:
    """Map bipolar evidence totals to a 0-100 directional conviction score.

    ``confidence = 100 * coverage * (0.5 + 0.5 * imbalance)`` where

    * ``coverage``    = how much evidence exists vs. the configured reference
      mass (thin evidence cannot score high), and
    * ``imbalance``   = |bull - bear| / (bull + bear): balanced evidence can
      never exceed ~50 because conviction in the winning side is weak.
    """
    th = thresholds or get_thresholds()
    total = bullish + bearish
    if total <= 0:
        return 0
    coverage = min(total / th.confidence_reference_evidence, 1.0)
    imbalance = abs(bullish - bearish) / total
    score = 100.0 * coverage * (0.5 + 0.5 * imbalance)
    return int(max(0, min(100, round(score))))


def confidence_label(score: float | int, thresholds: Optional[SignalThresholds] = None) -> str:
    th = thresholds or get_thresholds()
    return th.confidence_label(score)


# ---------------------------------------------------------------------------
# Setup status
# ---------------------------------------------------------------------------
def _setup_status_from_setup(setup, thresholds: Optional[SignalThresholds] = None) -> SetupStatus:
    th = thresholds or get_thresholds()

    direction = getattr(setup, "direction", "NO_SIGNAL")
    rejection = getattr(setup, "rejection_reason", "") or ""

    if direction in ("LONG", "SHORT"):
        entry = getattr(setup, "entry_low", None)
        stop_loss = getattr(setup, "stop_loss", None)
        tp1 = getattr(setup, "take_profit_1", None)
        rr = getattr(setup, "risk_reward", None)
        levels_complete = (
            entry is not None
            and stop_loss is not None
            and tp1 is not None
            and rr is not None
            and rr > 0
        )
        if levels_complete:
            # The canonical rules only keep direction LONG/SHORT after passing
            # their R:R and confidence validation -> setup fully validated.
            return "VALIDATED"
        # Direction confirmed by structure, but the risk engine did not (yet)
        # produce a complete, tradeable set of levels.
        return _confirmation_status(setup)

    if rejection in SETUP_REJECTED_REJECTIONS:
        return "INVALIDATED"

    return _confirmation_status(setup)


def _confirmation_status(setup) -> SetupStatus:
    """Classify a direction-less (or level-less) candidate by confirmations."""
    strong_confirmations = 0
    strong_confirmations += 1 if getattr(setup, "bos_events", None) else 0
    strong_confirmations += 1 if getattr(setup, "choch_events", None) else 0
    idm_events = list(getattr(setup, "idm_events", []) or [])
    strong_confirmations += 1 if any(getattr(i, "swept", False) for i in idm_events) else 0
    strong_confirmations += 1 if getattr(setup, "ifcs", None) else 0
    strong_confirmations += 1 if getattr(setup, "entry_scheme", "") else 0

    if strong_confirmations >= 2:
        return "PARTIALLY_CONFIRMED"
    if strong_confirmations == 1:
        return "WAITING_FOR_CONFIRMATION"
    if idm_events:
        # Inducement formed but not swept yet - classic waiting state.
        return "WAITING_FOR_CONFIRMATION"
    return "DEVELOPING"


def determine_setup_status(
    setup=None,
    thresholds: Optional[SignalThresholds] = None,
) -> SetupStatus:
    """Separate "the evidence leans <direction>" from "a trade setup exists"."""
    if setup is None:
        return "DEVELOPING"
    return _setup_status_from_setup(setup, thresholds)


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------
_SETUP_RISK_BASE: dict[str, int] = {
    "VALIDATED": 0,
    "PARTIALLY_CONFIRMED": 2,
    "WAITING_FOR_CONFIRMATION": 3,
    "DEVELOPING": 4,
    "INVALIDATED": 5,
}


def compute_risk_score(
    setup_status: str,
    direction: str,
    htf_bias: str = "NEUTRAL",
    middle_bias: str = "NEUTRAL",
    ltf_bias: str = "NEUTRAL",
    bullish: float = 0.0,
    bearish: float = 0.0,
    rr: Optional[float] = None,
    data_quality_ok: bool = True,
    freshness_degraded: bool = False,
    adverse_liquidity: bool = False,
) -> int:
    """Risk is deliberately *independent* from confidence.

    Confidence = how strongly the evidence leans.  Risk = how trustworthy the
    trade structure around that lean is (confirmation, timeframe agreement,
    reward profile, data quality, liquidity).
    """
    score = _SETUP_RISK_BASE.get(setup_status, 4)

    opposing = "SHORT" if direction == "LONG" else "LONG"
    for bias in (htf_bias, middle_bias, ltf_bias):
        if bias in ("BULLISH", "BEARISH"):
            bias_direction = "LONG" if bias == "BULLISH" else "SHORT"
            if bias_direction == opposing:
                score += 1

    total = bullish + bearish
    if total > 0:
        opposing_evidence = bearish if direction == "LONG" else bullish
        ratio = opposing_evidence / total
        if ratio >= 0.5:
            score += 2
        elif ratio >= 0.35:
            score += 1

    if rr is None:
        score += 1
    elif rr < 2.0:
        score += 1

    if not data_quality_ok:
        score += 1
    if freshness_degraded:
        score += 1
    if adverse_liquidity:
        score += 1

    return score


def classify_risk(risk_score: int, thresholds: Optional[SignalThresholds] = None) -> str:
    th = thresholds or get_thresholds()
    return th.risk_label(risk_score)


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------
def build_reasons(
    summary: EvidenceSummary,
    direction: str,
    setup_status: str,
    setup=None,
    max_reasons: int = 12,
) -> list[str]:
    """Human readable, fact-based reasons for the chosen direction."""
    supporting_side: Side = "BULLISH" if direction == "LONG" else "BEARISH"
    reasons: list[str] = []

    for item in summary.items:
        if item.side == supporting_side:
            reasons.append(item.label)

    conflicting = [
        f"{item.label} (conflicting)"
        for item in summary.items
        if item.side != supporting_side
    ]
    # Most significant conflicts first, keep the list readable.
    conflicting.sort(key=lambda text: text, reverse=False)
    reasons.extend(conflicting[:3])

    # Caveats / pending conditions -----------------------------------------
    if setup is not None:
        ltf_bias = getattr(setup, "ltf_bias", "NEUTRAL") or "NEUTRAL"
        ltf_supported = (
            (direction == "LONG" and ltf_bias == "BULLISH")
            or (direction == "SHORT" and ltf_bias == "BEARISH")
        )
        if not ltf_supported:
            reasons.append("LTF confirmation pending")

        idm_events = list(getattr(setup, "idm_events", []) or [])
        supporting_pending_idm = [
            i
            for i in idm_events
            if not getattr(i, "swept", False)
            and getattr(i, "direction", "") == supporting_side
        ]
        if supporting_pending_idm:
            reasons.append("IDM not yet swept")

        if not getattr(setup, "bos_events", None) and not getattr(setup, "choch_events", None):
            reasons.append("No confirmed BOS/CHoCH")

        if setup_status in ("DEVELOPING", "WAITING_FOR_CONFIRMATION", "PARTIALLY_CONFIRMED"):
            reasons.append("Awaiting entry confirmation")
        elif setup_status == "INVALIDATED":
            for text in getattr(setup, "reasons", []) or []:
                if "R:R" in text or "Confidence" in text:
                    reasons.append(f"Setup rejected: {text}")
                    break
            else:
                reasons.append("Candidate setup failed validation")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique.append(reason)
    return unique[:max_reasons]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _data_status_for_setup(setup) -> SignalStatus:
    if setup is None:
        return STATUS_ANALYSIS_ERROR
    rejection = getattr(setup, "rejection_reason", "") or ""
    if rejection in DATA_FAILURE_REJECTIONS:
        return STATUS_INSUFFICIENT_DATA
    reasons: Sequence[str] = getattr(setup, "reasons", []) or []
    for reason in reasons:
        lowered = reason.lower()
        if lowered.startswith("insufficient") or "atr is zero" in lowered:
            return STATUS_INSUFFICIENT_DATA
        if "invalid timeframe" in lowered:
            return STATUS_INSUFFICIENT_DATA
    if not getattr(setup, "reasons", None) and getattr(setup, "market_bias", "NEUTRAL") == "NEUTRAL" \
            and not getattr(setup, "htf_labels", None) and not getattr(setup, "middle_labels", None):
        # Nothing could be computed at all.
        return STATUS_INSUFFICIENT_DATA
    return STATUS_OK


def generate_directional_signal(
    setup=None,
    technical_analysis: Optional[dict] = None,
    status: SignalStatus = STATUS_OK,
    weights: Optional[EvidenceWeights] = None,
    thresholds: Optional[SignalThresholds] = None,
    data_quality_ok: bool = True,
    freshness_degraded: bool = False,
) -> DirectionalSignal:
    """Produce Karren's result for one symbol/timeframe.

    Always returns a direction when ``status`` is ``OK``; genuine data/system
    failures are returned as an explicit non-signal ``status`` instead.
    """
    th = thresholds or get_thresholds()

    # 1. Data / system failures are the only way to end without a direction.
    if status not in (STATUS_OK, None):
        return DirectionalSignal(
            status=status,
            direction="NEUTRAL",
            confidence=0,
            confidence_label=th.confidence_label(0),
            setup_status="NONE",
            risk="UNKNOWN",
            reasons=[f"Signal unavailable: {status}"],
        )

    if setup is not None:
        derived_status = _data_status_for_setup(setup)
        if derived_status != STATUS_OK:
            reasons = list(getattr(setup, "reasons", []) or []) or [
                f"Signal unavailable: {derived_status}"
            ]
            return DirectionalSignal(
                status=derived_status,
                direction="NEUTRAL",
                confidence=0,
                confidence_label=th.confidence_label(0),
                setup_status="NONE",
                risk="UNKNOWN",
                reasons=reasons[:6],
            )

    if setup is None and (not technical_analysis or "error" in technical_analysis):
        return DirectionalSignal(
            status=STATUS_INSUFFICIENT_DATA,
            direction="NEUTRAL",
            confidence=0,
            confidence_label=th.confidence_label(0),
            setup_status="NONE",
            risk="UNKNOWN",
            reasons=["Insufficient market data for analysis"],
        )

    # 2. Evidence -> direction -> confidence.
    summary = collect_evidence(setup, technical_analysis, weights)
    direction = choose_direction(summary, setup, technical_analysis)
    confidence = compute_confidence(summary.bullish, summary.bearish, th)

    # 3. Setup status (independent of direction strength).
    setup_status = determine_setup_status(setup, th)

    # 4. Trade levels: only when the canonical rules fully validated them.
    entry = sl = tp = rr = None
    if setup is not None and setup_status == "VALIDATED":
        entry = getattr(setup, "entry_low", None)
        sl = getattr(setup, "stop_loss", None)
        tp = getattr(setup, "take_profit_1", None)
        rr = getattr(setup, "risk_reward", None)
        if entry is None or sl is None or tp is None or rr is None:
            entry = sl = tp = rr = None
            setup_status = "PARTIALLY_CONFIRMED"

    # 5. Risk (separate axis from confidence).
    adverse_liquidity = False
    if setup is not None:
        sweep_side = getattr(summary, "_sweep_side", None)
        if sweep_side:
            adverse_liquidity = (
                (direction == "LONG" and sweep_side == "BEARISH")
                or (direction == "SHORT" and sweep_side == "BULLISH")
            )
        elif summary.total > 0:
            opposing = summary.bearish if direction == "LONG" else summary.bullish
            adverse_liquidity = opposing > summary.bullish if direction == "LONG" else opposing > summary.bearish

    htf_bias = getattr(setup, "htf_bias", "NEUTRAL") if setup is not None else "NEUTRAL"
    middle_bias = getattr(setup, "market_bias", "NEUTRAL") if setup is not None else "NEUTRAL"
    ltf_bias = getattr(setup, "ltf_bias", "NEUTRAL") if setup is not None else "NEUTRAL"
    if setup is None and technical_analysis and "error" not in technical_analysis:
        structure = (technical_analysis.get("market_structure") or {}).get("structure")
        if structure == "bullish":
            middle_bias = "BULLISH"
        elif structure == "bearish":
            middle_bias = "BEARISH"

    risk_score = compute_risk_score(
        setup_status=setup_status,
        direction=direction,
        htf_bias=htf_bias,
        middle_bias=middle_bias,
        ltf_bias=ltf_bias,
        bullish=summary.bullish,
        bearish=summary.bearish,
        rr=rr,
        data_quality_ok=data_quality_ok,
        freshness_degraded=freshness_degraded,
        adverse_liquidity=adverse_liquidity,
    )
    risk = classify_risk(risk_score, th)

    reasons = build_reasons(summary, direction, setup_status, setup)
    invalidation = list(getattr(setup, "invalidation_conditions", []) or []) if setup is not None else []

    return DirectionalSignal(
        status=STATUS_OK,
        direction=direction,
        confidence=confidence,
        confidence_label=th.confidence_label(confidence),
        setup_status=setup_status,
        risk=risk,
        entry=entry,
        sl=sl,
        tp=tp,
        rr=rr,
        reasons=reasons,
        bullish_score=round(summary.bullish, 2),
        bearish_score=round(summary.bearish, 2),
        invalidation_conditions=invalidation[:6],
    )
