from __future__ import annotations

from pathlib import Path
from typing import Any


def export_lead_checklist(
    export_dir: str | Path,
    lead: dict[str, Any],
    score: float | None,
    category: str | None,
    disclaimer: str,
) -> Path:
    p = Path(export_dir)
    p.mkdir(parents=True, exist_ok=True)
    lead_id = lead.get("id", "unknown")
    out = p / f"lead_{lead_id}_wholesale_checklist.md"

    address = lead.get("property_address") or ""
    city = lead.get("property_city") or ""
    state = lead.get("property_state") or ""
    zipc = lead.get("property_zip") or ""

    owner = lead.get("owner_name") or "Unknown Owner"
    phone = lead.get("owner_phone") or ""
    email = lead.get("owner_email") or ""

    arv = lead.get("estimated_arv")
    mort = lead.get("estimated_mortgage_balance")
    repairs = lead.get("estimated_repairs")

    md = []
    md.append("## Wholesale deal checklist (auto-generated)")
    md.append("")
    md.append(f"**Disclaimer**: {disclaimer}")
    md.append("")
    md.append("### Lead")
    md.append(f"- **Lead ID**: {lead_id}")
    md.append(f"- **Owner**: {owner}")
    md.append(f"- **Phone**: {phone}")
    md.append(f"- **Email**: {email}")
    md.append(f"- **Property**: {address}, {city}, {state} {zipc}".strip())
    if score is not None:
        md.append(f"- **Score**: {score:.3f} ({category})")
    md.append("")
    md.append("### Underwriting snapshot (estimates)")
    md.append(f"- **ARV**: {arv}")
    md.append(f"- **Mortgage balance**: {mort}")
    md.append(f"- **Repairs**: {repairs}")
    md.append("")
    md.append("### Next actions (suggested)")
    md.append("- [ ] Verify ownership and liens (public records / title)")
    md.append("- [ ] Confirm occupancy + access plan (tenant/owner/vacant)")
    md.append("- [ ] Validate ARV comps (compliant sources)")
    md.append("- [ ] Walkthrough or photo/video review")
    md.append("- [ ] Offer strategy: MAO, earnest money, close timeline")
    md.append("- [ ] Choose disposition path: assign vs double-close")
    md.append("- [ ] Prepare buyer list blast (only after property verified)")
    md.append("- [ ] Open escrow/title with reputable company")
    md.append("")
    md.append("### Compliance")
    md.append("- [ ] Confirm you can wholesale/market this deal in your jurisdiction")
    md.append("- [ ] Ensure disclosures about your role are accurate")
    md.append("- [ ] Honor opt-out/DNC requests immediately")
    md.append("")

    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    return out

