from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    db_path: str = "./data/wholesale.db"
    timezone: str = "UTC"
    dry_run: bool = True


class MarketConfig(BaseModel):
    state: str = "TX"
    city: str = "Dallas"
    county: str = "Dallas"


class CsvImportConfig(BaseModel):
    enabled: bool = True
    paths: list[str] = Field(default_factory=list)


class LeadSourcesConfig(BaseModel):
    csv_import: CsvImportConfig = Field(default_factory=CsvImportConfig)


class ScoringConfig(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "equity": 0.40,
            "distress": 0.25,
            "contactability": 0.20,
            "simplicity": 0.15,
        }
    )
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {"pursue_now": 0.72, "nurture": 0.50}
    )


class ChannelTemplatesConfig(BaseModel):
    first_touch: str
    follow_up_1: str | None = None


class EmailChannelConfig(BaseModel):
    enabled: bool = True
    send_live: bool = False
    templates: ChannelTemplatesConfig


class SmsChannelConfig(BaseModel):
    enabled: bool = False
    send_live: bool = False
    templates: ChannelTemplatesConfig


class OutreachChannelsConfig(BaseModel):
    email: EmailChannelConfig | None = None
    sms: SmsChannelConfig | None = None


class OutreachConfig(BaseModel):
    require_opt_out: bool = True
    block_if_missing_owner_name: bool = True
    respect_dnc: bool = True
    daily_send_limit: int = 50
    channels: OutreachChannelsConfig


class DocumentConfig(BaseModel):
    enabled: bool = True
    disclaimer: str = (
        "Not legal advice. Use state-approved forms and consult a qualified attorney "
        "or broker for your jurisdiction."
    )


class WholesaleProcessConfig(BaseModel):
    generate_documents: DocumentConfig = Field(default_factory=DocumentConfig)


class WholesaleConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    lead_sources: LeadSourcesConfig = Field(default_factory=LeadSourcesConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    outreach: OutreachConfig
    wholesale_process: WholesaleProcessConfig = Field(default_factory=WholesaleProcessConfig)


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    config: WholesaleConfig


def load_config(path: str | Path) -> LoadedConfig:
    p = Path(path)
    raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return LoadedConfig(path=p, config=WholesaleConfig.model_validate(raw))

