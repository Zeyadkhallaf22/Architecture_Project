# SCADA_PROJECT

AI investigation layer for a SCADA dashboard. This prototype runs on one PC. It does not include an IDS.

# Schneider Electric · AVEVA — Data Center Monitoring Dashboard

Professional SCADA-style dashboard for monitoring a 4-server data center fleet. Live KPIs come from **SQL Server Express** (IT System Performance dataset playback). The UI is a dark mission-control layout with TOP LEVEL MANAGEMENT, live PLC-style charts, alarms, AI recommendations, workbench compare, and PDF/CSV reports.

**Repo:** [mariamsalem1/SCADA_PROJECT](https://github.com/mariamsalem1/SCADA_PROJECT)

## Features

- **TOP LEVEL MANAGEMENT** — executive KPIs, pies, server snapshot, capacity headroom, risk heatmap, monthly performance, alarm trends
- **Business Risk** — composite score from offline servers, active alarms, critical KPIs, and recent alarm events (opens Alarm Summary)
- **Server Live Monitor** — embedded neon PLC line charts with hover tooltips
- **Workbench Compare / Monitor** — SQL vs workbench tags vs AI predictions
- **Alarm Summary** — history from `AlarmEvents`
- **Report Builder** — executive / technical / capacity / alarms → preview + PDF/CSV export
- **AI Analytics** — rule-based AIOps recommendations (+ optional trained model)

## Stack

| Layer | Technology |
|--------|------------|
| Frontend | Vanilla HTML / CSS / JS (`index.html`) |
| Backend | Python `ThreadingHTTPServer` (`server2.py`) |
| Database | Microsoft SQL Server Express (`DataCenterKPI`) |
| Live data | `ITSystemDataset` → `CurrentServerState` (no InTouch required for playback) |
| Optional AI | `ai_service/` (`model.pkl`, `scaler.pkl` — ignored by git; train locally) |

## Requirements

- Windows (pyodbc / SQL Express / optional pywin32)
- Python 3.11+ recommended
- SQL Server Express with the `DataCenterKPI` database
- Packages: see `requirments.txt` and `ai_service/requirements.txt`  
  Typical extras for full features: `reportlab`, `flask`, `flask-cors` (if used by your local checkout)

## Quick start

```powershell
cd D:\AVEVA\backend2
python -m venv venv
.\venv\Scripts\activate
pip install -r requirments.txt
# optional for PDF reports / AI
pip install reportlab flask flask-cors
```

1. Confirm SQL Express is running and connection settings in `server2.py` match your instance (default uses Windows auth / Trusted Connection).
2. Load live dataset if needed:

```powershell
python prepare_and_load_it_dataset.py
```

3. Start everything on this PC with one command. Set `GEMINI_API_KEY` in the same PowerShell window first if the chatbot should use Gemini. The key stays in that window. It is not stored in the project.

```powershell
cd D:\AVEVA\backend2\backend2
.\start.ps1
```

4. Open **http://127.0.0.1:8000/** and sign in. The demo account is `mariamsalem` / `mariam1234`. The Admin role is read from `Grad_role.csv`.

The chatbot keeps answering from dashboard facts when Gemini is not configured. The dashboard and the replayed dataset keep running in that case.

## Quality attributes from Milestone 1

| Scenario | What this PC prototype does |
|---|---|
| 5.1 Performance | Replayed dataset rows become events with an id and a source time. A repeated id is ignored. |
| 5.2 Reliability | Each replayed row is marked `replayed`, not as a live plant signal. |
| 5.3 Security | Chatbot, analytics, and gestures cannot call toggle, stress, or reset. |
| 5.4 Usability | Gestures stay in the local camera app and do not command the servers. |
| 5.5 Traceability | Chatbot answers are built from dashboard records. Gemini only rewrites those facts when a key is set. |
| 5.6 Modifiability | A new replay source is a new module in the `ingestion` package. The dashboard pages stay unchanged. |

The running interfaces follow Milestone 2. `POST /api/login` and `POST /api/v1/auth/session` sign the user in. Replayed rows enter through the IF-02 envelope. `GET /api/v1/evidence` reads those records. `GET /api/v1/ids/evidence` returns unavailable and an empty list. `POST /api/v1/queries` on port 8001 answers from dashboard facts. A vertical hand move sends `scroll_up` or `scroll_down` and the dashboard scrolls. Toggle, stress, and reset stay on the separate control path and each attempt is audited.

```powershell
python -m unittest tests.test_architecture_boundaries tests.test_architecture_conformance
```

## Architecture conformance

Each component is a package (a folder), a module (one file in a package), or a service (its own process and port). IDS is not part of this prototype. Analysis stays inside the backend service on this one PC.

| Component | Kind | Where |
|---|---|---|
| Ingestion adapters | package | `ingestion/` |
| IT dataset adapter | module | `ingestion/it_dataset.py` |
| Application and access | package | `access/` |
| Sign-in | module | `access/auth.py` |
| Control gate | module | `access/control_gate.py` |
| Evidence | package | `evidence/` |
| Event hub | module | `evidence/hub.py` |
| Replay label | module | `evidence/schema.py` |
| Correlation and evidence backend | service | `server2.py` on port 8000 |
| Explanation and assistant | service | `chatbot_server.py` on port 8001 |
| Dashboard frontend | package | `frontend/` |
| Gesture client | service | `SCADAPROJECT/vision_web.py` on port 8002 |

`ingestion` may publish events. It cannot import `access`. `access` and `evidence` cannot import each other. The assistant service and the gesture service have no control route. `tests/test_architecture_conformance.py` checks those rules and fails if either service names `/api/toggle`, `/api/stress`, or `/api/reset`.

## Project layout

```
backend2/
├── frontend/                  # index.html, login.html, dashboard-client.js
├── server2.py                 # Dashboard service (port 8000)
├── chatbot_server.py          # Assistant service (port 8001)
├── access/                    # Sign-in and control gate
├── ingestion/                 # Replay adapter
├── evidence/                  # Event hub and replay label
├── datasets/                  # CSV files and the local database
├── models/                    # model.pkl and scaler.pkl
├── tools/                     # Load scripts and older server copies
├── assets/                    # Logos and backgrounds
├── ai_service/                # Train and predict helpers
└── database queries/          # SQL scripts
```

## Keyboard shortcuts

| Key | View |
|-----|------|
| `S` | TOP LEVEL MANAGEMENT |
| `O` | Overview |
| `1`–`4` | Server detail |
| `I` | AI Analytics |
| `C` | Workbench Compare |
| `W` | Workbench Monitor |
| `R` | Report Builder |
| `A` | Alarm Summary |

## Notes

- Large CSVs, `venv/`, `*.pkl`, and `*.db` are gitignored — keep datasets and trained models local.
- Server controls (toggle / stress / reset) write to SQL; live readings refresh on a short poll interval.
- Branding: Schneider Electric \| AVEVA

## License

Private project repository — all rights reserved by the authors unless otherwise stated.
