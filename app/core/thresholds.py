"""Configuration-driven thresholds for Karren's directional signal engine.

Single source of truth for:
- confidence tier labels (score -> label)
- risk tier labels (risk score -> label)
- push-notification triggers (confidence threshold, minimum confidence delta, ...)

Nothing in this module is a "magic number" scattered across the codebase: the
signal engine, the recommendation engine and the notification service all read
their thresholds from here.  Every value can be overridden through environment
variables (see ``app.core.config.Settings``).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class SignalThresholds:
    """All tunable thresholds used when building a directional signal."""

    # --- Confidence tiers -------------------------------------------------
    # Evaluated from the highest score downwards: a confidence of 84 maps to
    # "VERY HIGH", 74 to "HIGH", ... 49 and below to "VERY LOW".
    # NOTE: confidence is a directional conviction score, NOT a calibrated
    # probability of profit.
    confidence_tiers: tuple[tuple[int, str], ...] = (
        (80, "VERY HIGH"),
        (70, "HIGH"),
        (60, "MODERATE"),
        (50, "LOW"),
        (0, "VERY LOW"),
    )

    # --- Risk tiers -------------------------------------------------------
    # A *risk score* (higher = riskier trade structure) maps to a label when
    # it is <= the configured bound.
    risk_tiers: tuple[tuple[int, str], ...] = (
        (2, "LOW"),
        (4, "MODERATE"),
        (6, "HIGH"),
        (10_000, "VERY HIGH"),
    )

    # --- Evidence scoring -------------------------------------------------
    # Reference evidence mass used to normalise directional evidence into a
    # 0-100 confidence score.  Only one side of evidence reaching roughly
    # this mass (with no opposing evidence) is worth ~100 confidence.
    confidence_reference_evidence: float = 60.0

    # --- Push notifications ----------------------------------------------
    # Minimum confidence required before a *new* signal may notify.
    notify_min_confidence: int = 70
    # Minimum |new - old| confidence change worth notifying about.
    notify_min_confidence_delta: int = 10
    # Enable/disable individual notification triggers.
    notify_on_high_confidence: bool = True
    notify_on_validated_setup: bool = True
    notify_on_confidence_increase: bool = True
    notify_on_direction_change: bool = True

    # --- Data sufficiency -------------------------------------------------
    # Minimum candles required on a timeframe before a direction may be
    # derived from it.
    min_candles_per_timeframe: int = 10

    def confidence_label(self, score: float | int) -> str:
        """Map a 0-100 confidence score to its configured tier label."""
        numeric = int(round(score))
        for lower_bound, label in self.confidence_tiers:
            if numeric >= lower_bound:
                return label
        return self.confidence_tiers[-1][1]

    def risk_label(self, risk_score: float | int) -> str:
        """Map a raw risk score to its configured tier label."""
        numeric = int(round(risk_score))
        for upper_bound, label in self.risk_tiers:
            if numeric <= upper_bound:
                return label
        return self.risk_tiers[-1][1]


_DEFAULTS = SignalThresholds()


@lru_cache(maxsize=1)
def get_thresholds() -> SignalThresholds:
    """Return thresholds, applying any environment overrides from Settings."""
    try:
        from app.core.config import get_settings

        settings = get_settings()
    except Exception:  # pragma: no cover - settings must never break scoring
        return _DEFAULTS

    overrides: dict = {}

    tier_pairs = list(_DEFAULTS.confidence_tiers)
    tier_overrides = {
        "CONFIDENCE_TIER_VERY_HIGH": "VERY HIGH",
        "CONFIDENCE_TIER_HIGH": "HIGH",
        "CONFIDENCE_TIER_MODERATE": "MODERATE",
        "CONFIDENCE_TIER_LOW": "LOW",
    }
    for attr, label in tier_overrides.items():
        value: Optional[int] = getattr(settings, attr, None)
        if value is not None:
            tier_pairs = [(v, l) for (v, l) in tier_pairs if l != label]
            tier_pairs.append((int(value), label))
    if len(tier_pairs) != len(_DEFAULTS.confidence_tiers):
        # Invalid override (duplicate/colliding bounds) - fall back to defaults.
        tier_pairs = list(_DEFAULTS.confidence_tiers)
    else:
        tier_pairs.sort(key=lambda pair: pair[0], reverse=True)
    overrides["confidence_tiers"] = tuple(tier_pairs)

    simple_int_overrides = {
        "NOTIFY_MIN_CONFIDENCE": "notify_min_confidence",
        "NOTIFY_MIN_CONFIDENCE_DELTA": "notify_min_confidence_delta",
        "CONFIDENCE_REFERENCE_EVIDENCE": "confidence_reference_evidence",
    }
    for attr, field_name in simple_int_overrides.items():
        value = getattr(settings, attr, None)
        if value is not None:
            overrides[field_name] = type(getattr(_DEFAULTS, field_name))(value)

    simple_bool_overrides = {
        "NOTIFY_ON_HIGH_CONFIDENCE": "notify_on_high_confidence",
        "NOTIFY_ON_VALIDATED_SETUP": "notify_on_validated_setup",
        "NOTIFY_ON_CONFIDENCE_INCREASE": "notify_on_confidence_increase",
        "NOTIFY_ON_DIRECTION_CHANGE": "notify_on_direction_change",
    }
    for attr, field_name in simple_bool_overrides.items():
        value = getattr(settings, attr, None)
        if value is not None:
            overrides[field_name] = bool(value)

    return replace(_DEFAULTS, **overrides)


def reset_thresholds_cache() -> None:
    """Testing hook: drop the cached thresholds after changing Settings."""
    get_thresholds.cache_clear()
