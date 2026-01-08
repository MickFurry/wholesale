from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from wholesale import db
from wholesale.config import load_config
from wholesale.pipeline import export_documents, ingest_sources, queue_outreach, score_all


def _read_version() -> str:
    try:
        from wholesale import __version__

        return __version__
    except Exception:
        return "unknown"


def _templates_dir() -> Path:
    return Path(__file__).parent / "templates"


def _static_dir() -> Path:
    return Path(__file__).parent / "static"


def create_app(config_path: str | None = None) -> FastAPI:
    config_path = config_path or os.getenv("WHOLESALE_CONFIG_PATH", "./config.yaml")
    loaded = load_config(config_path)
    cfg = loaded.config

    app = FastAPI(title="Wholesale Dashboard", version=_read_version())
    templates = Jinja2Templates(directory=str(_templates_dir()))

    static_dir = _static_dir()
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def _db_rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            top = _db_rows_to_dicts(db.top_opportunities(con, limit=20))
            queue = _db_rows_to_dicts(db.list_outreach_queue(con, status=None))[-20:]
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "cfg": cfg,
                "config_path": str(loaded.path),
                "top": top,
                "queue": queue,
            },
        )

    @app.get("/partials/top", response_class=HTMLResponse)
    def partial_top(request: Request):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            top = _db_rows_to_dicts(db.top_opportunities(con, limit=20))
        return templates.TemplateResponse("partials/top.html", {"request": request, "top": top})

    @app.get("/partials/queue", response_class=HTMLResponse)
    def partial_queue(request: Request):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            queue = _db_rows_to_dicts(db.list_outreach_queue(con, status=None))[-50:]
        return templates.TemplateResponse("partials/queue.html", {"request": request, "queue": queue})

    @app.get("/leads", response_class=HTMLResponse)
    def leads(request: Request):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            rows = _db_rows_to_dicts(db.list_leads_with_scores(con))
        return templates.TemplateResponse("leads.html", {"request": request, "rows": rows})

    @app.get("/lead/{lead_id}", response_class=HTMLResponse)
    def lead_detail(request: Request, lead_id: int):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            lead = db.get_lead(con, lead_id)
            score = db.get_score(con, lead_id)
            acts = _db_rows_to_dicts(db.list_activities(con, lead_id=lead_id, limit=100))
            out = _db_rows_to_dicts(db.list_outreach_for_lead(con, lead_id=lead_id, limit=100))
        if lead is None:
            return templates.TemplateResponse("not_found.html", {"request": request, "kind": "Lead", "id": lead_id})
        return templates.TemplateResponse(
            "lead.html",
            {"request": request, "lead": dict(lead), "score": dict(score) if score else None, "activities": acts, "outreach": out},
        )

    @app.get("/activity", response_class=HTMLResponse)
    def activity(request: Request):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            acts = _db_rows_to_dicts(db.list_activities(con, lead_id=None, limit=200))
        return templates.TemplateResponse("activity.html", {"request": request, "activities": acts})

    @app.get("/dnc", response_class=HTMLResponse)
    def dnc_page(request: Request):
        return templates.TemplateResponse("dnc.html", {"request": request})

    @app.post("/dnc/add")
    def dnc_add(kind: str = Form(...), value: str = Form(...), reason: str | None = Form(default=None)):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            db.add_dnc(con, kind, value, reason)
        return RedirectResponse(url="/dnc", status_code=303)

    @app.post("/actions/run-pipeline")
    def run_pipeline(sender_name: str = Form(default="Alex")):
        with db.connect(cfg.app.db_path) as con:
            db.init_db(con)
            ingest_sources(con, cfg)
            score_all(con, cfg)
            queue_outreach(con, cfg, sender_name=sender_name)
            export_documents(con, cfg)
        return RedirectResponse(url="/", status_code=303)

    return app


# Uvicorn import target: `uvicorn wholesale.web.app:app`
app = create_app()

