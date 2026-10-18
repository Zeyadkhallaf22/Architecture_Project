# Schneider Electric · AVEVA — Data Center Monitoring Dashboard

Professional SCADA-style dashboard for monitoring a 4-server data center fleet. Live KPIs come from **SQL Server Express** (IT System Performance dataset playback). The UI is a dark mission-control layout with TOP LEVEL MANAGEMENT, live PLC-style charts, alarms, AI recommendations, workbench compare, and PDF/CSV reports.

**Repo:** [mariamsalem1/Schneider-Electric-project-](https://github.com/mariamsalem1/Schneider-Electric-project-)

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

3. Start the dashboard:

```powershell
python server2.py
```

4. Open **http://127.0.0.1:8000/**

## Project layout

```
backend2/
├── index.html                 # Full dashboard UI
├── server2.py                 # Main API + static server (port 8000)
├── prepare_and_load_it_dataset.py
├── assets/                    # Logos & SCADA backgrounds
├── ai_service/                # Train / predict helpers
├── database queries/          # SQL scripts
└── requirments.txt
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
