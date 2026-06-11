# Phase 4 Launch Checklist

## Before committing
1. Run `PASS4_LAUNCH_SMOKE_TEST.bat` and confirm GREEN LIGHT.
2. Open `http://127.0.0.1:8787/viewer/index.html` with `RUN_STRATEGIC_RADAR_FINAL.bat`.
3. Confirm the opening dashboard shows 8-12 curated executive signals.
4. Confirm the first signal is not a raw CISA/CVE item.
5. Confirm no private names, employer names, customer names, credentials, or regulated operational data appear.
6. Capture screenshots for portfolio and LinkedIn.

## Git safety
Run `git status` first. Stage only intentional files. Do not use `git add .`.

## Files likely safe to stage for Phase 4
- `.gitignore`
- `viewer/index.html`
- `viewer/app.js`
- `viewer/assets/scout-horizon.svg`
- `viewer_server.py`
- `cache/radar_signals.json`
- `cache/radar_summary.json`
- `outputs/radar_signals.json`
- `outputs/radar_summary.json`
- `config/webassist_state.json`
- `config/executive_profile.json`
- `outputs/run_log.json`
- `README.md`
- `QA_REPORT.md`
- `RENDER_DEPLOYMENT_GUIDE.md`
- `PORTFOLIO_LAUNCH_KIT.md`
- `LINKEDIN_FEATURED_BLURB.md`
- `PHASE4_LAUNCH_CHECKLIST.md`
- `pass4_launch_smoke_test.py`
- `PASS4_LAUNCH_SMOKE_TEST.bat`
- `RUN_STRATEGIC_RADAR_FINAL.bat`
- `smoke_test.bat`

## Do not stage
- `.venv/`
- `.env`
- `.cache/`
- `__pycache__/`
- `backups/`
- old downloaded patch scripts
- screenshots unless you intentionally want to commit them
