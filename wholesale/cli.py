from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from wholesale import db
from wholesale.config import load_config
from wholesale.pipeline import export_documents, ingest_sources, queue_outreach, score_all, summarize


def _console() -> Console:
    return Console()


def _default_sender_name() -> str:
    # Keep generic by default; user can change in templates/config later.
    return os.getenv("SENDER_NAME") or "Alex"


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    """
    Allow global flags like --config to appear after the subcommand.

    Example supported:
      wholesale run --config ./config.yaml
    """
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return argv

    cfg_value: str | None = None
    out: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--config" and i + 1 < len(argv):
            cfg_value = argv[i + 1]
            i += 2
            continue
        if a.startswith("--config="):
            cfg_value = a.split("=", 1)[1]
            i += 1
            continue
        out.append(a)
        i += 1

    if cfg_value is None:
        return out
    return ["--config", cfg_value, *out]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wholesale", description="Autonomous wholesaling ops MVP")
    p.add_argument("--config", default=os.getenv("WHOLESALE_CONFIG_PATH", "./config.yaml"))

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Initialize the SQLite CRM schema")

    sub.add_parser("import", help="Import leads from configured sources")

    sub.add_parser("score", help="Score all leads")

    sub.add_parser("outreach", help="Queue outreach messages into outbox")

    sub.add_parser("export", help="Export per-lead wholesale checklist docs")

    run = sub.add_parser("run", help="Run end-to-end: init, import, score, outreach, export")
    run.add_argument("--sender-name", default=_default_sender_name())

    dnc = sub.add_parser("add-dnc", help="Add a DNC entry (email or phone)")
    dnc.add_argument("--kind", choices=["email", "phone"], required=True)
    dnc.add_argument("--value", required=True)
    dnc.add_argument("--reason", default=None)

    top = sub.add_parser("top", help="Show top opportunities")
    top.add_argument("--limit", type=int, default=10)

    web = sub.add_parser("web", help="Run local web dashboard (FastAPI)")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--reload", action="store_true", help="Auto-reload on code changes")

    return p


def _print_top(console: Console, rows: list[dict]) -> None:
    t = Table(title="Top opportunities (by score)")
    t.add_column("ID", justify="right")
    t.add_column("Score", justify="right")
    t.add_column("Cat")
    t.add_column("Owner")
    t.add_column("Address")
    t.add_column("ARV", justify="right")
    t.add_column("Mort", justify="right")
    t.add_column("Rep", justify="right")
    t.add_column("Signals")
    for r in rows:
        t.add_row(
            str(r.get("id", "")),
            f'{float(r.get("score") or 0.0):.3f}',
            str(r.get("category") or ""),
            str(r.get("owner_name") or ""),
            str(r.get("property_address") or ""),
            str(r.get("estimated_arv") or ""),
            str(r.get("estimated_mortgage_balance") or ""),
            str(r.get("estimated_repairs") or ""),
            str(r.get("distress_signals") or ""),
        )
    console.print(t)


def _run_web_server(config_path: str, host: str, port: int, reload: bool) -> int:
    import uvicorn

    # Create the app with the chosen config path.
    os.environ["WHOLESALE_CONFIG_PATH"] = config_path
    uvicorn.run(
        "wholesale.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(_normalize_argv(argv))
    console = _console()

    # `web` is long-running, so handle it before opening DB connections.
    if args.cmd == "web":
        config_path = args.config
        console.print(f"Starting dashboard on [bold]http://{args.host}:{args.port}[/bold]")
        return _run_web_server(config_path=config_path, host=args.host, port=args.port, reload=args.reload)

    loaded = load_config(args.config)
    cfg = loaded.config
    Path("./data").mkdir(parents=True, exist_ok=True)

    with db.connect(cfg.app.db_path) as con:
        if args.cmd == "init-db":
            db.init_db(con)
            console.print(f"Initialized DB at [bold]{cfg.app.db_path}[/bold]")
            return 0

        if args.cmd == "add-dnc":
            db.init_db(con)
            db.add_dnc(con, args.kind, args.value, args.reason)
            console.print(f"Added DNC: {args.kind}={args.value}")
            return 0

        if args.cmd == "import":
            db.init_db(con)
            res = ingest_sources(con, cfg)
            console.print(f"Imported: {res['imported']}, skipped: {res['skipped']}")
            if res["errors"]:
                console.print("Errors:")
                for e in res["errors"][:20]:
                    console.print(f"- {e}")
            return 0

        if args.cmd == "score":
            db.init_db(con)
            res = score_all(con, cfg)
            console.print(f"Scored: {res['scored']}")
            return 0

        if args.cmd == "outreach":
            db.init_db(con)
            res = queue_outreach(con, cfg, sender_name=_default_sender_name())
            console.print(f"Queued: {res['queued']}, skipped: {res['skipped']}")
            if res["reasons"]:
                console.print(res["reasons"])
            return 0

        if args.cmd == "export":
            db.init_db(con)
            res = export_documents(con, cfg)
            console.print(f"Exported docs: {res['exported']}")
            return 0

        if args.cmd == "top":
            db.init_db(con)
            rows = db.top_opportunities(con, limit=args.limit)
            _print_top(console, [dict(r) for r in rows])
            return 0

        if args.cmd == "run":
            db.init_db(con)

            res_ingest = ingest_sources(con, cfg)
            res_score = score_all(con, cfg)
            res_out = queue_outreach(con, cfg, sender_name=args.sender_name)
            res_exp = export_documents(con, cfg)

            console.print(
                f"Run complete. Imported {res_ingest['imported']} (skipped {res_ingest['skipped']}), "
                f"scored {res_score['scored']}, queued {res_out['queued']} (skipped {res_out['skipped']}), "
                f"exported {res_exp['exported']} docs."
            )

            summary = summarize(con)
            _print_top(console, summary["top"])
            console.print(f"Outbox: [bold]./data/outbox[/bold] (dry-run safe)")
            return 0

    return 2

