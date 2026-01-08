from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def iter_csv_leads(path: str | Path) -> Iterable[dict[str, Any]]:
    p = Path(path)
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {
                "source": (row.get("source") or "csv").strip(),
                "source_lead_id": (row.get("lead_id") or row.get("source_lead_id") or "").strip(),
                "owner_name": (row.get("owner_name") or "").strip() or None,
                "owner_email": (row.get("owner_email") or "").strip() or None,
                "owner_phone": (row.get("owner_phone") or "").strip() or None,
                "property_address": (row.get("property_address") or "").strip(),
                "property_city": (row.get("property_city") or "").strip() or None,
                "property_state": (row.get("property_state") or "").strip() or None,
                "property_zip": (row.get("property_zip") or "").strip() or None,
                "estimated_arv": _to_float(row.get("estimated_arv")),
                "estimated_mortgage_balance": _to_float(row.get("estimated_mortgage_balance")),
                "estimated_repairs": _to_float(row.get("estimated_repairs")),
                "distress_signals": (row.get("distress_signals") or "").strip() or None,
                "occupancy": (row.get("occupancy") or "").strip() or None,
                "notes": (row.get("notes") or "").strip() or None,
            }


def validate_minimum_fields(lead: dict[str, Any]) -> tuple[bool, str | None]:
    if not lead.get("source_lead_id"):
        return False, "missing source_lead_id"
    if not lead.get("property_address"):
        return False, "missing property_address"
    return True, None

