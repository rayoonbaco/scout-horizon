# Executive Decision Intelligence Engine

A demo-safe strategic signal radar for regulated life-sciences automation leadership. The app turns public or sample signals into an executive snapshot, ranked signal list, filterable decision lenses, detail panels, and recommended next-action review.

This public package intentionally avoids private names, private employer references, customer information, credentials, and regulated operational data.

## App type
FastAPI backend serving a browser dashboard from `/viewer/index.html`.

## Local run on Windows
Double-click `VIEW_RADAR.bat`, then open:

`http://127.0.0.1:8787/viewer/index.html`

## Render deployment
Use a Python Web Service.

Build command:

`pip install -r requirements.txt`

Start command:

`uvicorn viewer_server:app --host 0.0.0.0 --port $PORT`

Health check path:

`/healthz`

## Public demo safety
The hosted demo is designed to work without credentials. Optional Google Programmable Search credentials should be set as Render environment variables, not typed into a public browser form.

## Key folders
- `viewer/` — browser dashboard
- `viewer_server.py` — FastAPI server and API endpoints
- `src/` — radar engine modules
- `config/` — source and filter configuration
- `cache/` — viewer-ready demo cache
- `outputs/` — runtime logs/output

## Pass 1 wow + smoke-test workflow

This pass adds a stronger executive-facing first screen, a Boardroom Brief, cleaner demo-safe language, and a one-click internal smoke test.

### One-click local demo
Double-click:

`RUN_STRATEGIC_RADAR_PASS1.bat`

Then use:

`http://127.0.0.1:8787/viewer/index.html`

### One-click green-light smoke test
Double-click:

`PASS1_SMOKE_TEST.bat`

The smoke test starts a temporary local server, checks `/healthz`, `/viewer/index.html`, `/viewer/app.js`, `/api/state`, `/api/signals`, `/api/demo_fill`, and `/api/ingest`, then prints `GREEN LIGHT` if the pass is safe to review.


## Scout Mode visual identity
Pass 3 adds Scout Mode: a dark, demo-safe executive command-center treatment inspired by patient observation, terrain awareness, horizon scanning, and decisive action. The public dashboard keeps all personal backstory anonymous and does not expose private names, employer references, customers, credentials, or regulated operational data.

## Pass 3.1 - Curated Scout Mode default

Pass 3.1 restores the public first impression to a curated executive signal set. The Scout Mode dashboard should open with 12 demo-safe life-sciences decision signals, not a high-volume raw cybersecurity/feed dump. Use `PASS3_1_SMOKE_TEST.bat` for the green-light check and `RUN_STRATEGIC_RADAR_PASS3_1.bat` to launch locally.

## Phase 4 launch readiness

Use `PASS4_LAUNCH_SMOKE_TEST.bat` as the final green-light check before committing, deploying to Render, or sharing publicly. It verifies the server boots, Scout Mode loads, the default first impression remains curated to 8-12 executive signals, core endpoints return JSON, and obvious private identifiers are absent from the public demo surface.

For portfolio/LinkedIn copy, use `PORTFOLIO_LAUNCH_KIT.md` and `LINKEDIN_FEATURED_BLURB.md`.

For Render deployment, use `RENDER_DEPLOYMENT_GUIDE.md`.
