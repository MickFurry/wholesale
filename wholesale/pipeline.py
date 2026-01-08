from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wholesale import db
from wholesale.documents import export_lead_checklist
from wholesale.ingest import iter_csv_leads, validate_minimum_fields
from wholesale.outreach import render_template, write_outbox_message
from wholesale.scoring import score_lead


def ingest_sources(con, cfg) -> dict[str, Any]:
    imported = 0
    skipped = 0
    errors: list[str] = []

    csv_cfg = cfg.lead_sources.csv_import
    if csv_cfg and csv_cfg.enabled:
        for path in csv_cfg.paths:
            for lead in iter_csv_leads(path):
                ok, reason = validate_minimum_fields(lead)
                if not ok:
                    skipped += 1
                    errors.append(f"{path}: {reason}")
                    continue
                db.upsert_lead(con, lead)
                imported += 1

    return {"imported": imported, "skipped": skipped, "errors": errors}


def score_all(con, cfg) -> dict[str, Any]:
    leads = db.list_leads(con)
    scored = 0
    for l in leads:
        lead = dict(l)
        res = score_lead(lead, cfg.scoring.weights, cfg.scoring.thresholds)
        db.upsert_score(con, int(lead["id"]), res.score, res.category, res.subscores)
        scored += 1
    return {"scored": scored}


def _lead_context(lead_row: dict[str, Any]) -> dict[str, Any]:
    return {"lead": lead_row}


def queue_outreach(con, cfg, sender_name: str) -> dict[str, Any]:
    outbox_dir = Path("./data/outbox")
    outbox_dir.mkdir(parents=True, exist_ok=True)

    queued = 0
    skipped = 0
    reasons: dict[str, int] = {}

    tops = db.top_opportunities(con, limit=500)
    for row in tops:
        lead = dict(row)
        lead_id = int(lead["id"])
        category = lead.get("category")
        score = float(lead.get("score") or 0.0)

        if category not in ("pursue_now", "nurture"):
            continue

        # Enforce opt-out + identity guardrails.
        owner_name = (lead.get("owner_name") or "").strip()
        if cfg.outreach.block_if_missing_owner_name and not owner_name:
            skipped += 1
            reasons["missing_owner_name"] = reasons.get("missing_owner_name", 0) + 1
            db.log_activity(con, lead_id, "outreach_skipped", {"reason": "missing_owner_name"})
            continue

        # Email
        email_cfg = cfg.outreach.channels.email
        if email_cfg and email_cfg.enabled:
            to_email = (lead.get("owner_email") or "").strip()
            if not to_email:
                skipped += 1
                reasons["missing_email"] = reasons.get("missing_email", 0) + 1
            elif db.has_outreach(con, lead_id, "email", email_cfg.templates.first_touch):
                skipped += 1
                reasons["already_queued_email"] = reasons.get("already_queued_email", 0) + 1
                db.log_activity(
                    con,
                    lead_id,
                    "outreach_skipped",
                    {"reason": "already_queued", "channel": "email", "template": email_cfg.templates.first_touch},
                )
            elif cfg.outreach.respect_dnc and db.is_dnc(con, "email", to_email):
                skipped += 1
                reasons["dnc_email"] = reasons.get("dnc_email", 0) + 1
                db.log_activity(con, lead_id, "outreach_skipped", {"reason": "dnc_email", "value": to_email})
            else:
                ctx = {
                    "lead": {
                        **lead,
                        "owner_name": owner_name or "there",
                    },
                    "sender_name": sender_name,
                    "market": cfg.market.model_dump(),
                    "score": score,
                    "category": category,
                }
                rendered = render_template(email_cfg.templates.first_touch, ctx)
                outreach_id = db.enqueue_outreach(
                    con=con,
                    lead_id=lead_id,
                    channel="email",
                    template=email_cfg.templates.first_touch,
                    to_value=to_email,
                    subject=rendered.subject,
                    body=rendered.body,
                    status="queued" if (cfg.app.dry_run or not email_cfg.send_live) else "ready_to_send",
                    reason=None,
                )
                write_outbox_message(outbox_dir, outreach_id, "email", to_email, rendered.subject, rendered.body)
                db.log_activity(
                    con,
                    lead_id,
                    "outreach_queued",
                    {"channel": "email", "to": to_email, "template": email_cfg.templates.first_touch},
                )
                queued += 1

        # SMS
        sms_cfg = cfg.outreach.channels.sms
        if sms_cfg and sms_cfg.enabled:
            to_phone = (lead.get("owner_phone") or "").strip()
            if not to_phone:
                skipped += 1
                reasons["missing_phone"] = reasons.get("missing_phone", 0) + 1
            elif db.has_outreach(con, lead_id, "sms", sms_cfg.templates.first_touch):
                skipped += 1
                reasons["already_queued_sms"] = reasons.get("already_queued_sms", 0) + 1
                db.log_activity(
                    con,
                    lead_id,
                    "outreach_skipped",
                    {"reason": "already_queued", "channel": "sms", "template": sms_cfg.templates.first_touch},
                )
            elif cfg.outreach.respect_dnc and db.is_dnc(con, "phone", to_phone):
                skipped += 1
                reasons["dnc_phone"] = reasons.get("dnc_phone", 0) + 1
                db.log_activity(con, lead_id, "outreach_skipped", {"reason": "dnc_phone", "value": to_phone})
            else:
                ctx = {
                    "lead": {
                        **lead,
                        "owner_name": owner_name or "there",
                    },
                    "sender_name": sender_name,
                    "market": cfg.market.model_dump(),
                    "score": score,
                    "category": category,
                }
                rendered = render_template(sms_cfg.templates.first_touch, ctx)
                outreach_id = db.enqueue_outreach(
                    con=con,
                    lead_id=lead_id,
                    channel="sms",
                    template=sms_cfg.templates.first_touch,
                    to_value=to_phone,
                    subject=None,
                    body=rendered.body,
                    status="queued" if (cfg.app.dry_run or not sms_cfg.send_live) else "ready_to_send",
                    reason=None,
                )
                write_outbox_message(outbox_dir, outreach_id, "sms", to_phone, None, rendered.body)
                db.log_activity(
                    con,
                    lead_id,
                    "outreach_queued",
                    {"channel": "sms", "to": to_phone, "template": sms_cfg.templates.first_touch},
                )
                queued += 1

    return {"queued": queued, "skipped": skipped, "reasons": reasons}


def export_documents(con, cfg) -> dict[str, Any]:
    if not cfg.wholesale_process.generate_documents.enabled:
        return {"exported": 0}

    exported = 0
    rows = db.top_opportunities(con, limit=200)
    for row in rows:
        lead = dict(row)
        category = lead.get("category")
        if category not in ("pursue_now", "nurture"):
            continue
        out = export_lead_checklist(
            export_dir="./data/exports",
            lead=lead,
            score=float(lead.get("score") or 0.0),
            category=str(category),
            disclaimer=cfg.wholesale_process.generate_documents.disclaimer,
        )
        exported += 1
        db.log_activity(con, int(lead["id"]), "export_document", {"path": str(out)})
    return {"exported": exported}


def summarize(con) -> dict[str, Any]:
    top = db.top_opportunities(con, limit=10)
    return {"top": [dict(r) for r in top]}

