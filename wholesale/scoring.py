from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


DISTRESS_WEIGHTS: dict[str, float] = {
    # These are heuristics; tune to your market + strategy.
    "tax_delinquent": 0.9,
    "probate": 0.8,
    "code_violations": 0.7,
    "preforeclosure": 0.9,
    "recent_divorce": 0.6,
    "absentee_owner": 0.6,
    "vacant": 0.7,
    "liens": 0.7,
}


OCCUPANCY_SIMPLICITY: dict[str, float] = {
    "vacant": 1.0,
    "owner_occupied": 0.7,
    "tenant_occupied": 0.4,
    "unknown": 0.5,
}


@dataclass(frozen=True)
class ScoreResult:
    score: float
    category: str
    subscores: dict[str, Any]


def score_lead(lead: dict[str, Any], weights: dict[str, float], thresholds: dict[str, float]) -> ScoreResult:
    arv = lead.get("estimated_arv")
    mort = lead.get("estimated_mortgage_balance")
    repairs = lead.get("estimated_repairs")

    # Equity proxy: (ARV - mortgage - repairs) / ARV
    if isinstance(arv, (int, float)) and arv and arv > 0:
        mort_v = float(mort or 0.0)
        repairs_v = float(repairs or 0.0)
        equity = _clamp01((float(arv) - mort_v - repairs_v) / float(arv))
    else:
        equity = 0.35  # unknown; don't zero it out so it can still be prioritized if other signals are strong

    signals = [s.strip() for s in (lead.get("distress_signals") or "").split(";") if s.strip()]
    if signals:
        distress = _clamp01(sum(DISTRESS_WEIGHTS.get(s, 0.4) for s in signals) / len(signals))
    else:
        distress = 0.25

    has_email = bool((lead.get("owner_email") or "").strip())
    has_phone = bool((lead.get("owner_phone") or "").strip())
    contactability = 0.15 + (0.45 if has_phone else 0.0) + (0.40 if has_email else 0.0)
    contactability = _clamp01(contactability)

    occ = (lead.get("occupancy") or "unknown").strip().lower()
    simplicity = OCCUPANCY_SIMPLICITY.get(occ, 0.5)

    # Weighted sum normalized by total weights.
    total_w = sum(max(0.0, float(v)) for v in weights.values()) or 1.0
    score = (
        equity * float(weights.get("equity", 0.0))
        + distress * float(weights.get("distress", 0.0))
        + contactability * float(weights.get("contactability", 0.0))
        + simplicity * float(weights.get("simplicity", 0.0))
    ) / total_w
    score = _clamp01(score)

    pursue_now = float(thresholds.get("pursue_now", 0.72))
    nurture = float(thresholds.get("nurture", 0.50))
    if score >= pursue_now:
        category = "pursue_now"
    elif score >= nurture:
        category = "nurture"
    else:
        category = "low_priority"

    return ScoreResult(
        score=score,
        category=category,
        subscores={
            "equity": round(equity, 4),
            "distress": round(distress, 4),
            "contactability": round(contactability, 4),
            "simplicity": round(simplicity, 4),
            "signals": signals,
        },
    )

