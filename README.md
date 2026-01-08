## Autonomous real estate wholesaling ops (MVP)

This repo is a **workflow automation system** for real estate wholesaling operations:

- **Lead intake** (CSV imports; extensible to other compliant sources)
- **Opportunity scoring** (prioritize highest probability + margin first)
- **Outreach queue generation** (templates + opt-out + DNC checks)
- **Lightweight CRM** (SQLite: statuses, contact history, next actions)
- **Wholesale process checklisting** (tasks + document placeholders)

### Important legal/compliance note

This is **not legal advice** and it is not a substitute for licensed brokerage/legal counsel. Wholesaling is regulated differently across jurisdictions; use **state-approved forms**, follow **advertising/disclosure** rules, and honor **DNC/opt-out** requirements.

### Quickstart

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the autonomous pipeline (dry-run by default):

```bash
cp .env.example .env
python3 -m wholesale run --config ./config.yaml
```

### Live local web dashboard

Start the dashboard:

```bash
python3 -m wholesale web --config ./config.yaml --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` and click **Run now** to refresh the business state. The tables auto-refresh every few seconds.

### Bring your own leads (CSV)

Create a CSV with these headers (see `data/sample_leads.csv`):

- **identity**: `source`, `lead_id`
- **owner**: `owner_name`, `owner_email`, `owner_phone`
- **property**: `property_address`, `property_city`, `property_state`, `property_zip`
- **underwriting inputs**: `estimated_arv`, `estimated_mortgage_balance`, `estimated_repairs`
- **signals**: `distress_signals` (semicolon-separated, e.g. `tax_delinquent;absentee_owner`), `occupancy`
- **notes**: `notes`

Then point `config.yaml -> lead_sources -> csv_import -> paths` at your file(s).

### What it produces

- `data/wholesale.db`: CRM database (leads, scores, outreach queue, activity log)
- `data/outbox/`: rendered messages (email/sms) for review
- Console output: top opportunities + next recommended actions
