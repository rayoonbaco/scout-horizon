# Render Deployment Guide — Operation: Retrieve Gomez

## Render settings

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn viewer_server:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/healthz
```

## Public URLs

Landing page:

```text
https://YOUR-RENDER-SERVICE.onrender.com/
```

Dashboard:

```text
https://YOUR-RENDER-SERVICE.onrender.com/viewer/index.html
```

Executive brief:

```text
https://YOUR-RENDER-SERVICE.onrender.com/viewer/executive_brief.html
```

## Final local smoke test before pushing

```cmd
cd /d "C:\PROJECTS\strategic_radar_render"
PASS6_RENDER_SMOKE_TEST.bat
```

## Safe Git staging

Run `git status` first. If it looks clean, stage only intentional files:

```cmd
git add viewer_server.py
git add viewer/index.html
git add viewer/executive_brief.html
git add viewer/operation_retrieve_gomez.html
git add viewer/assets/operation_retrieve_gomez_scout_mode.png
git add viewer/assets/buffalo_bill_scout_mural.jpg
git add EXECUTIVE_SUMMARY.md
git add PORTFOLIO_PRESENTATION_BRIEF.md
git add LINKEDIN_FEATURED_PROJECT.md
git add LINKEDIN_LAUNCH_POST.md
git add RENDER_DEPLOYMENT_GUIDE.md
git add pass6_render_smoke_test.py
git add PASS6_RENDER_SMOKE_TEST.bat
git add RUN_OPERATION_RETRIEVE_GOMEZ.bat
git add smoke_test.bat
```

Then commit and push:

```cmd
git commit -m "Launch Operation Retrieve Gomez portfolio demo"
git push
```

Do not use `git add .`.
