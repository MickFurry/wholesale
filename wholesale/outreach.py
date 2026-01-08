from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@dataclass(frozen=True)
class RenderedMessage:
    subject: str | None
    body: str


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader("."),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_path: str, context: dict[str, Any]) -> RenderedMessage:
    env = _jinja_env()
    template = env.get_template(template_path)
    rendered = template.render(**context).strip()

    # Convention: email templates can optionally start with "Subject: ..."
    subject = None
    body = rendered
    if rendered.lower().startswith("subject:"):
        first_line, *rest = rendered.splitlines()
        subject = first_line.split(":", 1)[1].strip()
        body = "\n".join(rest).strip()
    return RenderedMessage(subject=subject, body=body)


def write_outbox_message(
    outbox_dir: str | Path,
    outreach_id: int,
    channel: str,
    to_value: str,
    subject: str | None,
    body: str,
) -> Path:
    p = Path(outbox_dir)
    p.mkdir(parents=True, exist_ok=True)
    fname = f"{outreach_id:06d}_{channel}_{_safe_filename(to_value)}.txt"
    out = p / fname
    header = []
    header.append(f"Channel: {channel}")
    header.append(f"To: {to_value}")
    if subject is not None:
        header.append(f"Subject: {subject}")
    header.append("")
    out.write_text("\n".join(header) + body + "\n", encoding="utf-8")
    return out


def _safe_filename(s: str) -> str:
    keep = []
    for ch in s.strip():
        if ch.isalnum():
            keep.append(ch)
        elif ch in ("@", "+", "-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:80] or "recipient"

