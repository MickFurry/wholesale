from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lead:
    id: int | None
    source: str
    source_lead_id: str
    owner_name: str | None
    owner_email: str | None
    owner_phone: str | None
    property_address: str
    property_city: str | None
    property_state: str | None
    property_zip: str | None
    estimated_arv: float | None
    estimated_mortgage_balance: float | None
    estimated_repairs: float | None
    distress_signals: str | None
    occupancy: str | None
    notes: str | None


@dataclass(frozen=True)
class LeadScore:
    lead_id: int
    score: float
    category: str
    subscores_json: str


@dataclass(frozen=True)
class OutreachMessage:
    lead_id: int
    channel: str
    template: str
    to_value: str
    subject: str | None
    body: str
    status: str
    reason: str | None

