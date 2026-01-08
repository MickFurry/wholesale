from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_parent_dir(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: str) -> Iterable[sqlite3.Connection]:
    ensure_parent_dir(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        yield con
        con.commit()
    finally:
        con.close()


def init_db(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          source_lead_id TEXT NOT NULL,
          owner_name TEXT,
          owner_email TEXT,
          owner_phone TEXT,
          property_address TEXT NOT NULL,
          property_city TEXT,
          property_state TEXT,
          property_zip TEXT,
          estimated_arv REAL,
          estimated_mortgage_balance REAL,
          estimated_repairs REAL,
          distress_signals TEXT,
          occupancy TEXT,
          notes TEXT,
          status TEXT NOT NULL DEFAULT 'new',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(source, source_lead_id)
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
          lead_id INTEGER PRIMARY KEY,
          score REAL NOT NULL,
          category TEXT NOT NULL,
          subscores_json TEXT NOT NULL,
          scored_at TEXT NOT NULL,
          FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS outreach_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id INTEGER NOT NULL,
          channel TEXT NOT NULL,
          template TEXT NOT NULL,
          to_value TEXT NOT NULL,
          subject TEXT,
          body TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT,
          created_at TEXT NOT NULL,
          sent_at TEXT,
          FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          details_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dnc (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL, -- 'email' or 'phone'
          value TEXT NOT NULL,
          reason TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(kind, value)
        );
        """
    )


def upsert_lead(con: sqlite3.Connection, lead: dict[str, Any]) -> int:
    now = _utc_now_iso()
    lead = dict(lead)
    lead.setdefault("created_at", now)
    lead.setdefault("updated_at", now)

    cols = [
        "source",
        "source_lead_id",
        "owner_name",
        "owner_email",
        "owner_phone",
        "property_address",
        "property_city",
        "property_state",
        "property_zip",
        "estimated_arv",
        "estimated_mortgage_balance",
        "estimated_repairs",
        "distress_signals",
        "occupancy",
        "notes",
        "updated_at",
        "created_at",
    ]
    params = {c: lead.get(c) for c in cols}

    con.execute(
        """
        INSERT INTO leads (
          source, source_lead_id, owner_name, owner_email, owner_phone,
          property_address, property_city, property_state, property_zip,
          estimated_arv, estimated_mortgage_balance, estimated_repairs,
          distress_signals, occupancy, notes,
          updated_at, created_at
        ) VALUES (
          :source, :source_lead_id, :owner_name, :owner_email, :owner_phone,
          :property_address, :property_city, :property_state, :property_zip,
          :estimated_arv, :estimated_mortgage_balance, :estimated_repairs,
          :distress_signals, :occupancy, :notes,
          :updated_at, :created_at
        )
        ON CONFLICT(source, source_lead_id)
        DO UPDATE SET
          owner_name=excluded.owner_name,
          owner_email=excluded.owner_email,
          owner_phone=excluded.owner_phone,
          property_address=excluded.property_address,
          property_city=excluded.property_city,
          property_state=excluded.property_state,
          property_zip=excluded.property_zip,
          estimated_arv=excluded.estimated_arv,
          estimated_mortgage_balance=excluded.estimated_mortgage_balance,
          estimated_repairs=excluded.estimated_repairs,
          distress_signals=excluded.distress_signals,
          occupancy=excluded.occupancy,
          notes=excluded.notes,
          updated_at=excluded.updated_at
        ;
        """,
        params,
    )

    row = con.execute(
        "SELECT id FROM leads WHERE source=? AND source_lead_id=?",
        (lead["source"], lead["source_lead_id"]),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def list_leads(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute("SELECT * FROM leads ORDER BY id DESC"))


def set_lead_status(con: sqlite3.Connection, lead_id: int, status: str) -> None:
    con.execute(
        "UPDATE leads SET status=?, updated_at=? WHERE id=?",
        (status, _utc_now_iso(), lead_id),
    )


def upsert_score(
    con: sqlite3.Connection,
    lead_id: int,
    score: float,
    category: str,
    subscores: dict[str, Any],
) -> None:
    con.execute(
        """
        INSERT INTO scores (lead_id, score, category, subscores_json, scored_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(lead_id) DO UPDATE SET
          score=excluded.score,
          category=excluded.category,
          subscores_json=excluded.subscores_json,
          scored_at=excluded.scored_at
        """,
        (lead_id, score, category, json.dumps(subscores, sort_keys=True), _utc_now_iso()),
    )


def top_opportunities(con: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT l.*, s.score, s.category
            FROM leads l
            JOIN scores s ON s.lead_id = l.id
            ORDER BY s.score DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def is_dnc(con: sqlite3.Connection, kind: str, value: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM dnc WHERE kind=? AND value=?",
        (kind, value.strip()),
    ).fetchone()
    return row is not None


def add_dnc(con: sqlite3.Connection, kind: str, value: str, reason: str | None) -> None:
    con.execute(
        """
        INSERT INTO dnc (kind, value, reason, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(kind, value) DO UPDATE SET reason=excluded.reason
        """,
        (kind, value.strip(), reason, _utc_now_iso()),
    )


def enqueue_outreach(
    con: sqlite3.Connection,
    lead_id: int,
    channel: str,
    template: str,
    to_value: str,
    subject: str | None,
    body: str,
    status: str,
    reason: str | None,
) -> int:
    cur = con.execute(
        """
        INSERT INTO outreach_queue (
          lead_id, channel, template, to_value, subject, body,
          status, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (lead_id, channel, template, to_value, subject, body, status, reason, _utc_now_iso()),
    )
    return int(cur.lastrowid)


def list_outreach_queue(con: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return list(con.execute("SELECT * FROM outreach_queue WHERE status=? ORDER BY id", (status,)))
    return list(con.execute("SELECT * FROM outreach_queue ORDER BY id"))


def has_outreach(con: sqlite3.Connection, lead_id: int, channel: str, template: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM outreach_queue
        WHERE lead_id=? AND channel=? AND template=?
        LIMIT 1
        """,
        (lead_id, channel, template),
    ).fetchone()
    return row is not None


def log_activity(con: sqlite3.Connection, lead_id: int, type_: str, details: dict[str, Any]) -> None:
    con.execute(
        """
        INSERT INTO activities (lead_id, type, details_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (lead_id, type_, json.dumps(details, sort_keys=True), _utc_now_iso()),
    )

