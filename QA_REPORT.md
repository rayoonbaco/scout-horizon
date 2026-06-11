# QA Report — Strategic Radar Scout Mode

## Current launch status
Phase 4 launch readiness package installed. Use `PASS4_LAUNCH_SMOKE_TEST.bat` as the final local green-light check before commit, Render deploy, or public sharing.

## Required checks covered by PASS4 smoke test
- `viewer_server.py` compiles.
- Render configuration exists and points to `viewer_server:app`.
- FastAPI server boots locally on port 8787.
- `/healthz` returns OK.
- `/viewer/index.html` loads.
- `/viewer/app.js` loads.
- `/api/state` returns JSON.
- `/api/signals` returns curated signal data.
- Default public first impression is capped to 8-12 curated executive signals.
- The first signal is not a raw CISA/CVE item.
- Public demo payload avoids private names, employer references, customer details, credentials, and regulated operational data.
- Scout Mode labels are present.

## Manual checks still recommended
- Open the help/instructions modal.
- Try a keyword filter and confirm the visible list changes.
- Click at least three watchlist items and confirm Active Signal updates.
- Capture screenshots of the hero, Scout Brief, Radar Snapshot, Active Signal, and GREEN LIGHT terminal.

## Deliberate demo-safe choices
- Hosted demo uses curated public/sample signals by default.
- Optional live search credentials must be set as environment variables, not exposed in the browser.
- Public language avoids claims of enterprise production readiness, FDA compliance, validated GxP status, or use by a named company/person.
