"""
Professional Data Center Monitoring Dashboard

Architecture:
    Kaggle IT System Performance dataset (SQL Express live playback)
    <-> Python backend -> HTML/CSS/JS dashboard

Live readings come from dbo.ITSystemDataset → CurrentServerState (no AVEVA InTouch required).
Server controls (toggle / stress / reset) still write into the same SQL tables.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse
from flask import Flask, jsonify
import pyodbc
from flask_cors import CORS

try:
    from ai_service.predict import predict_servers
except Exception as _predict_import_error:  # noqa: BLE001 — keep server up without model
    def predict_servers(state_override=None):  # type: ignore[misc]
        return {
            "model_available": False,
            "model_error": str(_predict_import_error),
            "predictions": [],
        }

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


#============================================
# NOTE: this Flask app is no longer used to serve requests — main() runs
# ThreadingHTTPServer with DashboardHandler, not app.run(). The /api/ai/predictions
# route below is dead code; the live equivalent is in DashboardHandler.do_GET().
# Kept here only so predict_servers() has somewhere obvious to live if you want to
# migrate this whole backend to Flask properly later. Safe to delete if unused.
app = Flask(__name__)

CORS(app)
#====================================

# ============================================================
# CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 8000
POLL_SECONDS = 1.0
# Advance one Kaggle dataset row per server on this interval (live playback)
LIVE_DATASET_STEP_SECONDS = 5.0
DATA_SOURCE_MODE = "IT_SYSTEM_DATASET_LIVE"  # not InTouch

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=MARIAM\\MSSQLSERVER03;"
    "DATABASE=DataCenterKPI;"
    "Trusted_Connection=yes;"
)

ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT / "assets"
LOGO_CANDIDATES = (
    ASSETS_DIR / "schneider-aveva-logo.png",
    ASSETS_DIR / "schneider-aveva-logo.jpg",
    ASSETS_DIR / "brand-logo.png",
    ROOT / "schneider-aveva-logo.png",
)

LOCK = threading.RLock()

# These are project operational thresholds. They match the existing alarm logic.
THRESHOLDS = {
    "cpu_warning": 75.0,
    "cpu_critical": 90.0,
    "ram_warning": 80.0,
    "ram_critical": 90.0,
    "disk_warning": 80.0,
    "disk_critical": 90.0,
    "temp_warning": 60.0,
    "temp_critical": 75.0,
    "latency_warning": 30.0,
    "latency_critical": 50.0,
}

AI_SOURCES = [
    {
        "id": "SRE-GOLDEN-SIGNALS",
        "organization": "Google SRE",
        "title": "Monitoring Distributed Systems - The Four Golden Signals",
        "year": 2016,
        "url": "https://sre.google/sre-book/monitoring-distributed-systems/",
        "supports": "Latency, traffic, errors and saturation should be monitored together.",
    },
    {
        "id": "UPTIME-OUTAGE-2026",
        "organization": "Uptime Institute",
        "title": "Annual Data Center Outages Analysis 2026",
        "year": 2026,
        "url": "https://intelligence.uptimeinstitute.com/resource/annual-outage-analysis-2026",
        "supports": "Outage prevention, resilience, operational complexity and risk management.",
    },
    {
        "id": "ASHRAE-THERMAL",
        "organization": "ASHRAE TC 9.9",
        "title": "Equipment Thermal Guidelines for Data Processing Environments",
        "year": 2021,
        "url": "https://www.ashrae.org/file%20library/technical%20resources/bookstore/supplemental%20files/therm-gdlns-5th-r-e-refcard.pdf",
        "supports": "Thermal conditions must be monitored and managed within equipment/environment classes.",
    },
    {
        "id": "SCHNEIDER-DLC-210",
        "organization": "Schneider Electric",
        "title": "Direct Liquid Cooling System Challenges in Data Centers - White Paper 210",
        "year": 2025,
        "url": "https://www.se.com/ww/en/download/document/SPD_WP210_EN/",
        "supports": "Cooling architecture, deployment and operational risks for high-density compute.",
    },
    {
        "id": "SCHNEIDER-PUE",
        "organization": "Schneider Electric",
        "title": "Data Center KPIs: PUE and Holistic Performance Measurement",
        "year": 2012,
        "url": "https://blog.se.com/datacenter/architecture/2012/03/02/data-center-key-performance-indicators-a-look-at-pue-and-other-numbers-to-evaluate-performance/",
        "supports": "Use multiple KPIs rather than relying on a single metric.",
    },
]


def empty_state() -> dict[str, Any]:
    values: dict[str, Any] = {"Simulation_On": False}
    for server in range(1, 5):
        values.update(
            {
                f"Server{server}_CPU_Percent": 0.0,
                f"Server{server}_RAM_Percent": 0.0,
                f"Server{server}_Disk_Percent": 0.0,
                f"Server{server}_Temp_C": 0.0,
                f"Server{server}_Status": False,
                f"Server{server}_Network_Mbps": 0.0,
                f"Server{server}_Latency_ms": 0.0,
                f"Server{server}_CPU_Alarm": False,
                f"Server{server}_Temp_Alarm": False,
                f"Server{server}_Down_Alarm": True,
            }
        )
    values.update(
        {
            "DC_Servers_Up": 0,
            "DC_Avg_CPU": 0.0,
            "DC_Avg_RAM": 0.0,
            "DC_Avg_Disk": 0.0,
            "DC_Max_Temp": 0.0,
            "DC_Total_Network": 0.0,
            "DC_Avg_Latency": 0.0,
        }
    )
    return values


state = empty_state()
db_connected = False
last_update_time: datetime | None = None
last_database_error: str | None = None


# =====================================
# AI PREDICTIONS API
# =====================================

@app.route("/api/ai/predictions", methods=["GET"])
def ai_predictions():

    try:

        predictions = predict_servers()

        return jsonify(
            predictions
        )


    except Exception as e:

        return jsonify({

            "error": str(e)

        }), 500

# ============================================================
# GENERAL HELPERS
# ============================================================


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "up", "online"}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(CONNECTION_STRING, timeout=10)


def table_exists(cursor: pyodbc.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT CASE WHEN OBJECT_ID(?, 'U') IS NULL THEN 0 ELSE 1 END",
        (f"dbo.{table_name}",),
    )
    return bool(cursor.fetchone()[0])


def parse_tag_value(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return json_safe(value)
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return stripped


def find_logo() -> Path | None:
    for candidate in LOGO_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


# ============================================================
# DATABASE READS
# ============================================================


def resolve_history_table(cursor: Any) -> str | None:
    """
    Prefer ServerHistory when present — it stays aligned with CurrentServerState.
    ServerMonitoringHistory is used as fallback (some environments only have that table),
    but it has recently been storing CPU_Percent=0 while live state shows real CPU.
    """
    if table_exists(cursor, "ServerHistory"):
        return "ServerHistory"
    if table_exists(cursor, "ServerMonitoringHistory"):
        return "ServerMonitoringHistory"
    return None


def history_temp_column(cursor: Any, table_name: str) -> str:
    """Support Temperature_C (ServerHistory) and Temp_C (ServerMonitoringHistory)."""
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
        """,
        (table_name,),
    )
    columns = {str(row[0]).lower() for row in cursor.fetchall()}
    if "temperature_c" in columns:
        return "Temperature_C"
    if "temp_c" in columns:
        return "Temp_C"
    return "Temperature_C"


def history_cpu_column(cursor: Any, table_name: str) -> str:
    """Support CPU_Percent and alternate CPU column names."""
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
        """,
        (table_name,),
    )
    columns = {str(row[0]).lower(): str(row[0]) for row in cursor.fetchall()}
    for candidate in ("CPU_Percent", "CPU", "Cpu_Percent", "CPUUsage"):
        if candidate.lower() in columns:
            return columns[candidate.lower()]
    return "CPU_Percent"


def test_database_connection() -> bool:
    global db_connected, last_database_error
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            cursor.execute("SELECT DB_NAME()")
            database_name = cursor.fetchone()[0]
            required = ["CurrentServerState", "LatestTagValues"]
            missing = [name for name in required if not table_exists(cursor, name)]
            if resolve_history_table(cursor) is None:
                missing.append("ServerMonitoringHistory|ServerHistory")
            if missing:
                raise RuntimeError(f"Missing required SQL tables: {', '.join(missing)}")
        db_connected = True
        last_database_error = None
        print(f"Database connected: {database_name}")
        return True
    except Exception as error:  # pyodbc + schema errors
        db_connected = False
        last_database_error = str(error)
        print(f"Database connection unavailable: {error}")
        return False


def calculate_summary(target: dict[str, Any]) -> None:
    online = [i for i in range(1, 5) if as_bool(target.get(f"Server{i}_Status"))]
    target["DC_Servers_Up"] = len(online)

    def average(metric: str, servers: Iterable[int]) -> float:
        values = [as_float(target.get(f"Server{i}_{metric}")) for i in servers]
        return round(sum(values) / len(values), 1) if values else 0.0

    target["DC_Avg_CPU"] = average("CPU_Percent", online)
    target["DC_Avg_RAM"] = average("RAM_Percent", online)
    target["DC_Avg_Disk"] = average("Disk_Percent", online)
    target["DC_Avg_Latency"] = average("Latency_ms", online)

    temperatures = [as_float(target.get(f"Server{i}_Temp_C")) for i in online]
    target["DC_Max_Temp"] = round(max(temperatures), 1) if temperatures else 0.0
    target["DC_Total_Network"] = round(
        sum(as_float(target.get(f"Server{i}_Network_Mbps")) for i in range(1, 5)), 1
    )


def derive_alarm_flags(target: dict[str, Any]) -> None:
    for server in range(1, 5):
        status = as_bool(target.get(f"Server{server}_Status"))
        cpu = as_float(target.get(f"Server{server}_CPU_Percent"))
        temp = as_float(target.get(f"Server{server}_Temp_C"))
        target[f"Server{server}_CPU_Alarm"] = cpu >= THRESHOLDS["cpu_critical"]
        target[f"Server{server}_Temp_Alarm"] = temp >= THRESHOLDS["temp_critical"]
        target[f"Server{server}_Down_Alarm"] = not status


# Baseline “healthy” values used by Reset (aligned with known workbench defaults).
SERVER_BASELINES = {
    1: {"cpu": 35.0, "ram": 45.0, "disk": 52.0, "temp": 48.0, "net": 110.0, "lat": 10.0},
    2: {"cpu": 58.0, "ram": 62.0, "disk": 68.0, "temp": 60.0, "net": 150.0, "lat": 14.0},
    3: {"cpu": 22.0, "ram": 35.0, "disk": 41.0, "temp": 40.0, "net": 75.0, "lat": 8.0},
    4: {"cpu": 44.0, "ram": 50.0, "disk": 57.0, "temp": 52.0, "net": 125.0, "lat": 12.0},
}


def _server_snapshot_from_state(tags: dict[str, Any], server: int) -> dict[str, Any]:
    return {
        "cpu": as_float(tags.get(f"Server{server}_CPU_Percent")),
        "ram": as_float(tags.get(f"Server{server}_RAM_Percent")),
        "disk": as_float(tags.get(f"Server{server}_Disk_Percent")),
        "temp": as_float(tags.get(f"Server{server}_Temp_C")),
        "net": as_float(tags.get(f"Server{server}_Network_Mbps")),
        "lat": as_float(tags.get(f"Server{server}_Latency_ms")),
        "status": as_bool(tags.get(f"Server{server}_Status")),
        "cpu_alarm": as_bool(tags.get(f"Server{server}_CPU_Alarm")),
        "temp_alarm": as_bool(tags.get(f"Server{server}_Temp_Alarm")),
        "down_alarm": as_bool(tags.get(f"Server{server}_Down_Alarm")),
    }


def persist_server_control(server: int, tags: dict[str, Any], event: str | None = None, severity: str = "INFO") -> None:
    """Write one server's live metrics into the SQL tables the dashboard reads."""
    snap = _server_snapshot_from_state(tags, server)
    now = datetime.now()
    status_bit = 1 if snap["status"] else 0

    connection = get_connection()
    with connection:
        cursor = connection.cursor()

        if table_exists(cursor, "CurrentServerState"):
            cursor.execute(
                """
                MERGE dbo.CurrentServerState AS target
                USING (SELECT ? AS ServerNumber) AS source
                ON target.ServerNumber = source.ServerNumber
                WHEN MATCHED THEN UPDATE SET
                    CPU_Percent = ?, RAM_Percent = ?, Disk_Percent = ?,
                    Temperature_C = ?, Network_Mbps = ?, Latency_ms = ?, Status = ?
                WHEN NOT MATCHED THEN INSERT
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     Temperature_C, Network_Mbps, Latency_ms, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    server,
                    snap["cpu"], snap["ram"], snap["disk"], snap["temp"], snap["net"], snap["lat"], status_bit,
                    server,
                    snap["cpu"], snap["ram"], snap["disk"], snap["temp"], snap["net"], snap["lat"], status_bit,
                ),
            )

        if table_exists(cursor, "ServerMonitoringValues"):
            cursor.execute(
                """
                MERGE dbo.ServerMonitoringValues AS target
                USING (SELECT ? AS ServerNumber) AS source
                ON target.ServerNumber = source.ServerNumber
                WHEN MATCHED THEN UPDATE SET
                    CPU_Percent = ?, RAM_Percent = ?, Disk_Percent = ?,
                    Temp_C = ?, Network_Mbps = ?, Latency_ms = ?, Status = ?, UpdatedAt = ?
                WHEN NOT MATCHED THEN INSERT
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     Temp_C, Network_Mbps, Latency_ms, Status, UpdatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    server,
                    snap["cpu"], snap["ram"], snap["disk"], snap["temp"], snap["net"], snap["lat"], status_bit, now,
                    server,
                    snap["cpu"], snap["ram"], snap["disk"], snap["temp"], snap["net"], snap["lat"], status_bit, now,
                ),
            )

        if table_exists(cursor, "ServerCPUWorkbench"):
            cursor.execute(
                """
                MERGE dbo.ServerCPUWorkbench AS target
                USING (SELECT ? AS ServerNumber) AS source
                ON target.ServerNumber = source.ServerNumber
                WHEN MATCHED THEN UPDATE SET CPU_Percent = ?, UpdatedAt = ?
                WHEN NOT MATCHED THEN INSERT (ServerNumber, CPU_Percent, UpdatedAt)
                VALUES (?, ?, ?);
                """,
                (server, snap["cpu"], now, server, snap["cpu"], now),
            )

        if table_exists(cursor, "ServerHistory"):
            cursor.execute(
                """
                INSERT INTO dbo.ServerHistory
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     Temperature_C, Network_Mbps, Latency_ms, Status, RecordedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server, snap["cpu"], snap["ram"], snap["disk"],
                    snap["temp"], snap["net"], snap["lat"], status_bit, now,
                ),
            )

        if table_exists(cursor, "ServerMonitoringHistory"):
            # Support either Temperature_C or Temp_C
            temp_col = history_temp_column(cursor, "ServerMonitoringHistory")
            cursor.execute(
                f"""
                INSERT INTO dbo.ServerMonitoringHistory
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     {temp_col}, Network_Mbps, Latency_ms, Status, RecordedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server, snap["cpu"], snap["ram"], snap["disk"],
                    snap["temp"], snap["net"], snap["lat"], status_bit, now,
                ),
            )

        if table_exists(cursor, "LatestTagValues"):
            tag_pairs = [
                (f"Server{server}_CPU_Percent", str(snap["cpu"])),
                (f"Server{server}_RAM_Percent", str(snap["ram"])),
                (f"Server{server}_Disk_Percent", str(snap["disk"])),
                (f"Server{server}_Temp_C", str(snap["temp"])),
                (f"Server{server}_Network_Mbps", str(snap["net"])),
                (f"Server{server}_Latency_ms", str(snap["lat"])),
                (f"Server{server}_Status", "true" if snap["status"] else "false"),
                (f"Server{server}_CPU_Alarm", "true" if snap["cpu_alarm"] else "false"),
                (f"Server{server}_Temp_Alarm", "true" if snap["temp_alarm"] else "false"),
                (f"Server{server}_Down_Alarm", "true" if snap["down_alarm"] else "false"),
            ]
            for tag_name, value in tag_pairs:
                cursor.execute(
                    """
                    MERGE dbo.LatestTagValues AS target
                    USING (SELECT ? AS TagName) AS source
                    ON target.TagName = source.TagName
                    WHEN MATCHED THEN UPDATE SET Value = ?, UpdatedAt = ?
                    WHEN NOT MATCHED THEN INSERT (TagName, Value, UpdatedAt)
                    VALUES (?, ?, ?);
                    """,
                    (tag_name, value, now, tag_name, value, now),
                )

        if event and table_exists(cursor, "AlarmEvents"):
            cursor.execute(
                """
                INSERT INTO dbo.AlarmEvents (ServerNumber, EventName, Severity, EventTime)
                VALUES (?, ?, ?, ?)
                """,
                (server, event, severity, now),
            )

        connection.commit()


def toggle_server(server: int) -> dict[str, Any]:
    server = int(clamp(server, 1, 4))
    with LOCK:
        tags = state
        was_up = as_bool(tags.get(f"Server{server}_Status"))
        now_up = not was_up
        tags[f"Server{server}_Status"] = now_up
        if now_up:
            base = SERVER_BASELINES[server]
            tags[f"Server{server}_CPU_Percent"] = round(base["cpu"] + random.uniform(-3, 3), 1)
            tags[f"Server{server}_RAM_Percent"] = round(base["ram"] + random.uniform(-2, 2), 1)
            tags[f"Server{server}_Disk_Percent"] = base["disk"]
            tags[f"Server{server}_Temp_C"] = round(base["temp"] + random.uniform(-2, 2), 1)
            tags[f"Server{server}_Network_Mbps"] = round(base["net"] + random.uniform(-5, 5), 1)
            tags[f"Server{server}_Latency_ms"] = round(base["lat"] + random.uniform(-1, 1), 1)
            event = f"Server {server} restored (dashboard toggle ON)"
            severity = "RECOVERY"
            message = f"Server {server} is now UP."
        else:
            tags[f"Server{server}_CPU_Percent"] = 0.0
            tags[f"Server{server}_RAM_Percent"] = 0.0
            tags[f"Server{server}_Disk_Percent"] = 0.0
            tags[f"Server{server}_Temp_C"] = 25.0
            tags[f"Server{server}_Network_Mbps"] = 0.0
            tags[f"Server{server}_Latency_ms"] = 0.0
            event = f"Server {server} taken offline (dashboard toggle OFF)"
            severity = "CRITICAL"
            message = f"Server {server} is now DOWN."
        derive_alarm_flags(tags)
        calculate_summary(tags)
        snapshot = tags.copy()

    persist_server_control(server, snapshot, event=event, severity=severity)
    return {"success": True, "server": server, "status": now_up, "message": message}


def stress_server(server: int) -> dict[str, Any]:
    server = int(clamp(server, 1, 4))
    with LOCK:
        tags = state
        if not as_bool(tags.get(f"Server{server}_Status")):
            return {
                "success": False,
                "server": server,
                "message": f"Server {server} is OFF — turn it on before running a stress test.",
            }
        tags[f"Server{server}_CPU_Percent"] = round(
            min(100.0, as_float(tags.get(f"Server{server}_CPU_Percent")) + random.uniform(22, 38)), 1
        )
        tags[f"Server{server}_RAM_Percent"] = round(
            min(100.0, as_float(tags.get(f"Server{server}_RAM_Percent")) + random.uniform(8, 18)), 1
        )
        tags[f"Server{server}_Temp_C"] = round(
            min(100.0, as_float(tags.get(f"Server{server}_Temp_C")) + random.uniform(8, 14)), 1
        )
        tags[f"Server{server}_Latency_ms"] = round(
            min(80.0, as_float(tags.get(f"Server{server}_Latency_ms")) + random.uniform(3, 8)), 1
        )
        derive_alarm_flags(tags)
        calculate_summary(tags)
        snapshot = tags.copy()
        cpu = as_float(snapshot.get(f"Server{server}_CPU_Percent"))

    persist_server_control(
        server,
        snapshot,
        event=f"CPU stress test applied on Server {server} (CPU now {cpu}%)",
        severity="WARNING" if cpu < THRESHOLDS["cpu_critical"] else "CRITICAL",
    )
    return {
        "success": True,
        "server": server,
        "message": f"Stress applied to Server {server}. CPU is now {cpu}%.",
        "cpu": cpu,
    }


def reset_server(server: int) -> dict[str, Any]:
    server = int(clamp(server, 1, 4))
    base = SERVER_BASELINES[server]
    with LOCK:
        tags = state
        tags[f"Server{server}_Status"] = True
        tags[f"Server{server}_CPU_Percent"] = base["cpu"]
        tags[f"Server{server}_RAM_Percent"] = base["ram"]
        tags[f"Server{server}_Disk_Percent"] = base["disk"]
        tags[f"Server{server}_Temp_C"] = base["temp"]
        tags[f"Server{server}_Network_Mbps"] = base["net"]
        tags[f"Server{server}_Latency_ms"] = base["lat"]
        derive_alarm_flags(tags)
        calculate_summary(tags)
        snapshot = tags.copy()

    persist_server_control(
        server,
        snapshot,
        event=f"Server {server} reset to baseline from dashboard",
        severity="RECOVERY",
    )
    return {
        "success": True,
        "server": server,
        "message": f"Server {server} reset to normal baseline values.",
    }


def read_latest_data_from_database() -> bool:
    global state, db_connected, last_update_time, last_database_error

    try:
        connection = get_connection()
        next_state = empty_state()
        newest_timestamp: datetime | None = None

        with connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                       Temperature_C, Network_Mbps, Latency_ms, Status
                FROM dbo.CurrentServerState
                WHERE ServerNumber BETWEEN 1 AND 4
                ORDER BY ServerNumber
                """
            )
            for row in cursor.fetchall():
                server = int(row[0])
                next_state[f"Server{server}_CPU_Percent"] = as_float(row[1])
                next_state[f"Server{server}_RAM_Percent"] = as_float(row[2])
                next_state[f"Server{server}_Disk_Percent"] = as_float(row[3])
                next_state[f"Server{server}_Temp_C"] = as_float(row[4])
                next_state[f"Server{server}_Network_Mbps"] = as_float(row[5])
                next_state[f"Server{server}_Latency_ms"] = as_float(row[6])
                next_state[f"Server{server}_Status"] = as_bool(row[7])

            if table_exists(cursor, "LatestTagValues"):
                cursor.execute("SELECT TagName, Value FROM dbo.LatestTagValues")
                for tag_name, raw_value in cursor.fetchall():
                    if tag_name in next_state:
                        next_state[tag_name] = parse_tag_value(raw_value)

            # Use explicit alarm rows if the optional table exists; otherwise derive them.
            derive_alarm_flags(next_state)
            if table_exists(cursor, "ServerMetrics"):
                cursor.execute(
                    """
                    WITH Latest AS (
                        SELECT ServerNumber, CPU_Alarm, Temp_Alarm, Down_Alarm,
                               ROW_NUMBER() OVER (PARTITION BY ServerNumber ORDER BY Id DESC) AS rn
                        FROM dbo.ServerMetrics
                        WHERE ServerNumber BETWEEN 1 AND 4
                    )
                    SELECT ServerNumber, CPU_Alarm, Temp_Alarm, Down_Alarm
                    FROM Latest WHERE rn = 1
                    """
                )
                for row in cursor.fetchall():
                    server = int(row[0])
                    next_state[f"Server{server}_CPU_Alarm"] = as_bool(row[1])
                    next_state[f"Server{server}_Temp_Alarm"] = as_bool(row[2])
                    next_state[f"Server{server}_Down_Alarm"] = as_bool(row[3])

            history_table = resolve_history_table(cursor)
            if history_table:
                cursor.execute(f"SELECT MAX(RecordedAt) FROM dbo.{history_table}")
                newest_timestamp = cursor.fetchone()[0]

        calculate_summary(next_state)
        with LOCK:
            state = next_state
            last_update_time = newest_timestamp or datetime.now()
            db_connected = True
            last_database_error = None
        return True
    except Exception as error:
        with LOCK:
            db_connected = False
            last_database_error = str(error)
        print(f"Live SQL read failed: {error}")
        return False


def data_poller() -> None:
    """Advance live Kaggle playback into SQL, then refresh in-memory state."""
    last_step = 0.0
    while True:
        now = time.time()
        if now - last_step >= LIVE_DATASET_STEP_SECONDS:
            try:
                advance_it_dataset_live()
            except Exception as error:  # noqa: BLE001
                print(f"IT dataset live step failed: {error}")
            last_step = now
        read_latest_data_from_database()
        time.sleep(POLL_SECONDS)


def advance_it_dataset_live() -> bool:
    """
    Push the next ITSystemDataset row for each server into CurrentServerState /
    history / tags so the dashboard stays live without AVEVA InTouch.
    """
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "ITSystemDataset"):
                return False
            if not table_exists(cursor, "ITSystemLiveCursor"):
                return False

            now = datetime.now()
            for server in range(1, 5):
                cursor.execute(
                    "SELECT LastId FROM dbo.ITSystemLiveCursor WHERE ServerNumber = ?",
                    (server,),
                )
                crow = cursor.fetchone()
                last_id = int(crow[0]) if crow else 0

                cursor.execute(
                    """
                    SELECT TOP 1 Id, CPU_Percent, RAM_Percent, Disk_Percent, Temperature_C,
                           Network_Mbps, Latency_ms, Status, CPU_Alarm, Temp_Alarm, Down_Alarm
                    FROM dbo.ITSystemDataset
                    WHERE ServerNumber = ? AND Id > ?
                    ORDER BY Id
                    """,
                    (server, last_id),
                )
                row = cursor.fetchone()
                if not row:
                    # Loop to the beginning for continuous live playback
                    cursor.execute(
                        """
                        SELECT TOP 1 Id, CPU_Percent, RAM_Percent, Disk_Percent, Temperature_C,
                               Network_Mbps, Latency_ms, Status, CPU_Alarm, Temp_Alarm, Down_Alarm
                        FROM dbo.ITSystemDataset
                        WHERE ServerNumber = ?
                        ORDER BY Id
                        """,
                        (server,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        continue

                rid, cpu, ram, disk, temp, net, lat, status, cpu_a, temp_a, down_a = row

                cursor.execute(
                    """
                    MERGE dbo.CurrentServerState AS t
                    USING (SELECT ? AS ServerNumber) AS s
                    ON t.ServerNumber = s.ServerNumber
                    WHEN MATCHED THEN UPDATE SET
                        CPU_Percent=?, RAM_Percent=?, Disk_Percent=?, Temperature_C=?,
                        Network_Mbps=?, Latency_ms=?, Status=?
                    WHEN NOT MATCHED THEN INSERT
                        (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                         Temperature_C, Network_Mbps, Latency_ms, Status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (server, cpu, ram, disk, temp, net, lat, status,
                     server, cpu, ram, disk, temp, net, lat, status),
                )

                if table_exists(cursor, "ServerMonitoringValues"):
                    cursor.execute(
                        """
                        MERGE dbo.ServerMonitoringValues AS t
                        USING (SELECT ? AS ServerNumber) AS s
                        ON t.ServerNumber = s.ServerNumber
                        WHEN MATCHED THEN UPDATE SET
                            CPU_Percent=?, RAM_Percent=?, Disk_Percent=?, Temp_C=?,
                            Network_Mbps=?, Latency_ms=?, Status=?, UpdatedAt=?
                        WHEN NOT MATCHED THEN INSERT
                            (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                             Temp_C, Network_Mbps, Latency_ms, Status, UpdatedAt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (server, cpu, ram, disk, temp, net, lat, status, now,
                         server, cpu, ram, disk, temp, net, lat, status, now),
                    )

                if table_exists(cursor, "ServerHistory"):
                    cursor.execute(
                        """
                        INSERT INTO dbo.ServerHistory
                            (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                             Temperature_C, Network_Mbps, Latency_ms, Status, RecordedAt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (server, cpu, ram, disk, temp, net, lat, status, now),
                    )

                if table_exists(cursor, "ServerMonitoringHistory"):
                    temp_col = history_temp_column(cursor, "ServerMonitoringHistory")
                    cursor.execute(
                        f"""
                        INSERT INTO dbo.ServerMonitoringHistory
                            (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                             {temp_col}, Network_Mbps, Latency_ms, Status, RecordedAt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (server, cpu, ram, disk, temp, net, lat, status, now),
                    )

                if table_exists(cursor, "LatestTagValues"):
                    tag_pairs = [
                        (f"Server{server}_CPU_Percent", str(cpu)),
                        (f"Server{server}_RAM_Percent", str(ram)),
                        (f"Server{server}_Disk_Percent", str(disk)),
                        (f"Server{server}_Temp_C", str(temp)),
                        (f"Server{server}_Network_Mbps", str(net)),
                        (f"Server{server}_Latency_ms", str(lat)),
                        (f"Server{server}_Status", "true" if status else "false"),
                        (f"Server{server}_CPU_Alarm", "true" if cpu_a else "false"),
                        (f"Server{server}_Temp_Alarm", "true" if temp_a else "false"),
                        (f"Server{server}_Down_Alarm", "true" if down_a else "false"),
                    ]
                    for tag_name, value in tag_pairs:
                        cursor.execute(
                            """
                            MERGE dbo.LatestTagValues AS t
                            USING (SELECT ? AS TagName) AS s
                            ON t.TagName = s.TagName
                            WHEN MATCHED THEN UPDATE SET Value=?, UpdatedAt=?
                            WHEN NOT MATCHED THEN INSERT (TagName, Value, UpdatedAt)
                            VALUES (?, ?, ?);
                            """,
                            (tag_name, value, now, tag_name, value, now),
                        )

                cursor.execute(
                    """
                    MERGE dbo.ITSystemLiveCursor AS t
                    USING (SELECT ? AS ServerNumber) AS s
                    ON t.ServerNumber = s.ServerNumber
                    WHEN MATCHED THEN UPDATE SET LastId=?, UpdatedAt=?
                    WHEN NOT MATCHED THEN INSERT (ServerNumber, LastId, UpdatedAt)
                    VALUES (?, ?, ?);
                    """,
                    (server, rid, now, server, rid, now),
                )
        return True
    except Exception as error:
        print(f"advance_it_dataset_live failed: {error}")
        return False


def read_history(server: int, limit: int = 120) -> list[dict[str, Any]]:
    server = int(clamp(server, 1, 4))
    limit = int(clamp(limit, 1, 1000))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            table_name = resolve_history_table(cursor)
            if not table_name:
                return []
            temp_col = history_temp_column(cursor, table_name)
            cpu_col = history_cpu_column(cursor, table_name)
            cursor.execute(
                f"""
                SELECT TOP {limit}
                    RecordedAt, {cpu_col}, RAM_Percent, Disk_Percent,
                    {temp_col}, Network_Mbps, Latency_ms, Status
                FROM dbo.{table_name}
                WHERE ServerNumber = ?
                ORDER BY RecordedAt DESC
                """,
                (server,),
            )
            rows = cursor.fetchall()
        samples = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "cpu": as_float(row[1]),
                "ram": as_float(row[2]),
                "disk": as_float(row[3]),
                "temperature": as_float(row[4]),
                "network": as_float(row[5]),
                "latency": as_float(row[6]),
                "status": as_bool(row[7]),
            }
            for row in reversed(rows)
        ]

        # Keep chart "now" aligned with Key Metrics (CurrentServerState), even if a
        # secondary history table briefly stores CPU as 0.
        with LOCK:
            tags = state.copy()
        live_cpu = as_float(tags.get(f"Server{server}_CPU_Percent"))
        if samples:
            newest = samples[-1]
            if live_cpu > 0 and newest.get("cpu", 0) == 0:
                newest["cpu"] = live_cpu
            # Soft-align other live fields when history is stale/zeroed
            for field, suffix in (
                ("ram", "RAM_Percent"),
                ("disk", "Disk_Percent"),
                ("temperature", "Temp_C"),
                ("network", "Network_Mbps"),
                ("latency", "Latency_ms"),
            ):
                live = as_float(tags.get(f"Server{server}_{suffix}"))
                if live > 0 and as_float(newest.get(field)) == 0:
                    newest[field] = live
            newest["status"] = as_bool(tags.get(f"Server{server}_Status"))
        elif live_cpu or as_bool(tags.get(f"Server{server}_Status")):
            samples = [
                {
                    "timestamp": datetime.now().isoformat(),
                    "cpu": live_cpu,
                    "ram": as_float(tags.get(f"Server{server}_RAM_Percent")),
                    "disk": as_float(tags.get(f"Server{server}_Disk_Percent")),
                    "temperature": as_float(tags.get(f"Server{server}_Temp_C")),
                    "network": as_float(tags.get(f"Server{server}_Network_Mbps")),
                    "latency": as_float(tags.get(f"Server{server}_Latency_ms")),
                    "status": as_bool(tags.get(f"Server{server}_Status")),
                }
            ]
        return samples
    except Exception as error:
        print(f"History read failed: {error}")
        return []


def read_monitoring_values_row(server: int) -> dict[str, Any] | None:
    """Latest workbench snapshot from ServerMonitoringValues for one server."""
    server = int(clamp(server, 1, 4))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "ServerMonitoringValues"):
                return None
            cursor.execute(
                """
                SELECT TOP 1
                    ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                    Temp_C, Network_Mbps, Latency_ms, Status, UpdatedAt
                FROM dbo.ServerMonitoringValues
                WHERE ServerNumber = ?
                ORDER BY UpdatedAt DESC, ID DESC
                """,
                (server,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "server": int(row[0]),
            "cpu": as_float(row[1]),
            "ram": as_float(row[2]),
            "disk": as_float(row[3]),
            "temperature": as_float(row[4]),
            "network": as_float(row[5]),
            "latency": as_float(row[6]),
            "status": as_bool(row[7]),
            "updated_at": row[8].isoformat() if row[8] else None,
        }
    except Exception as error:
        print(f"ServerMonitoringValues read failed: {error}")
        return None


def read_server_monitoring_history(server: int, limit: int = 120) -> list[dict[str, Any]]:
    """
    Always reads dbo.ServerMonitoringHistory (workbench monitor source).
    Does not fall back to ServerHistory.
    """
    server = int(clamp(server, 1, 4))
    limit = int(clamp(limit, 1, 1000))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "ServerMonitoringHistory"):
                return []
            temp_col = history_temp_column(cursor, "ServerMonitoringHistory")
            cpu_col = history_cpu_column(cursor, "ServerMonitoringHistory")
            cursor.execute(
                f"""
                SELECT TOP {limit}
                    RecordedAt, {cpu_col}, RAM_Percent, Disk_Percent,
                    {temp_col}, Network_Mbps, Latency_ms, Status
                FROM dbo.ServerMonitoringHistory
                WHERE ServerNumber = ?
                ORDER BY RecordedAt DESC
                """,
                (server,),
            )
            rows = cursor.fetchall()
        samples = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "cpu": as_float(row[1]),
                "ram": as_float(row[2]),
                "disk": as_float(row[3]),
                "temperature": as_float(row[4]),
                "network": as_float(row[5]),
                "latency": as_float(row[6]),
                "status": as_bool(row[7]),
            }
            for row in reversed(rows)
        ]

        # History often stores CPU_Percent=0; overlay newest point from ServerMonitoringValues
        live = read_monitoring_values_row(server)
        if samples and live:
            newest = samples[-1]
            if as_float(newest.get("cpu")) == 0 and as_float(live.get("cpu")) > 0:
                newest["cpu"] = live["cpu"]
            for field in ("ram", "disk", "temperature", "network", "latency"):
                if as_float(newest.get(field)) == 0 and as_float(live.get(field)) > 0:
                    newest[field] = live[field]
            newest["status"] = live.get("status", newest.get("status"))
        elif not samples and live:
            samples = [
                {
                    "timestamp": live.get("updated_at") or datetime.now().isoformat(),
                    "cpu": live["cpu"],
                    "ram": live["ram"],
                    "disk": live["disk"],
                    "temperature": live["temperature"],
                    "network": live["network"],
                    "latency": live["latency"],
                    "status": live["status"],
                }
            ]
        return samples
    except Exception as error:
        print(f"ServerMonitoringHistory read failed: {error}")
        return []


def build_workbench_monitor_payload(server: int, limit: int = 60) -> dict[str, Any]:
    server = int(clamp(server, 1, 4))
    limit = int(clamp(limit, 1, 500))
    history = read_server_monitoring_history(server, limit)
    latest = history[-1] if history else None
    live = read_monitoring_values_row(server)

    servers_with_rows: list[dict[str, Any]] = []
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if table_exists(cursor, "ServerMonitoringHistory"):
                cursor.execute(
                    """
                    SELECT ServerNumber, COUNT(*) AS SampleRows, MAX(RecordedAt) AS LastAt
                    FROM dbo.ServerMonitoringHistory
                    WHERE ServerNumber BETWEEN 1 AND 4
                    GROUP BY ServerNumber
                    ORDER BY ServerNumber
                    """
                )
                for row in cursor.fetchall():
                    servers_with_rows.append(
                        {
                            "server": int(row[0]),
                            "row_count": int(row[1]),
                            "last_recorded_at": row[2].isoformat() if row[2] else None,
                        }
                    )
    except Exception as error:
        print(f"Workbench monitor summary failed: {error}")

    return {
        "table": "ServerMonitoringHistory",
        "server": server,
        "limit": limit,
        "sample_count": len(history),
        "history": history,
        "latest": latest,
        "live_values": live,
        "servers_summary": servers_with_rows,
        "database_connected": db_connected,
        "generated_at": datetime.now().isoformat(),
        "refresh_hint_seconds": 45,
    }


def read_latest_tag_values() -> list[dict[str, Any]]:
    """Union of LatestTagValues + WB_ServerNTags + ServerMonitoringValues (as tags)."""
    by_tag: dict[str, dict[str, Any]] = {}

    def upsert(tag: str, value: Any, updated_at: Any = None, source: str = "") -> None:
        if not tag:
            return
        key = str(tag)
        if isinstance(value, Decimal):
            parsed: Any = float(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            parsed = value
        else:
            parsed = parse_tag_value(value)
        by_tag[key] = {
            "tag": key,
            "value": parsed,
            "raw_value": str(value) if value is not None else None,
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else (updated_at or None),
            "source": source,
        }

    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()

            # 1) Columnar workbench snapshot → tag names the UI already expects
            if table_exists(cursor, "ServerMonitoringValues"):
                cursor.execute(
                    """
                    SELECT ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                           Temp_C, Network_Mbps, Latency_ms, Status, UpdatedAt
                    FROM dbo.ServerMonitoringValues
                    WHERE ServerNumber BETWEEN 1 AND 4
                    ORDER BY ServerNumber
                    """
                )
                for row in cursor.fetchall():
                    server = int(row[0])
                    updated = row[8]
                    upsert(f"Server{server}_CPU_Percent", row[1], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_RAM_Percent", row[2], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_Disk_Percent", row[3], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_Temp_C", row[4], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_Network_Mbps", row[5], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_Latency_ms", row[6], updated, "ServerMonitoringValues")
                    upsert(f"Server{server}_Status", row[7], updated, "ServerMonitoringValues")

            # 2) Classic LatestTagValues (often empty in this environment)
            if table_exists(cursor, "LatestTagValues"):
                cursor.execute(
                    """
                    SELECT TagName, Value, UpdatedAt
                    FROM dbo.LatestTagValues
                    ORDER BY TagName
                    """
                )
                for tag_name, raw_value, updated in cursor.fetchall():
                    upsert(str(tag_name), raw_value, updated, "LatestTagValues")

            # 3) Per-server workbench tag tables: WB_Server1Tags … WB_Server4Tags
            for server in range(1, 5):
                table_name = f"WB_Server{server}Tags"
                if not table_exists(cursor, table_name):
                    continue
                # Column casing can vary (Tagname vs TagName)
                cursor.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
                    """,
                    (table_name,),
                )
                colmap = {str(r[0]).lower(): str(r[0]) for r in cursor.fetchall()}
                tag_col = colmap.get("tagname") or colmap.get("tag_name") or colmap.get("name")
                val_col = colmap.get("value")
                ts_col = colmap.get("timestamp") or colmap.get("updatedat") or colmap.get("updated_at")
                if not tag_col or not val_col:
                    continue
                select_ts = f", [{ts_col}]" if ts_col else ", NULL"
                cursor.execute(
                    f"""
                    SELECT [{tag_col}], [{val_col}]{select_ts}
                    FROM dbo.[{table_name}]
                    """
                )
                for row in cursor.fetchall():
                    raw_tag = str(row[0] or "").strip()
                    if not raw_tag:
                        continue
                    # Normalize short names (CPU_Percent) to ServerN_CPU_Percent
                    if raw_tag.startswith(f"Server{server}_"):
                        full_tag = raw_tag
                    elif raw_tag.startswith("Server") and "_" in raw_tag:
                        full_tag = raw_tag
                    else:
                        full_tag = f"Server{server}_{raw_tag}"
                    upsert(full_tag, row[1], row[2] if len(row) > 2 else None, table_name)

    except Exception as error:
        print(f"Tag read failed: {error}")
        return []

    return [by_tag[k] for k in sorted(by_tag.keys())]


def read_cpu_workbench() -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            # Prefer ServerMonitoringValues CPU as the live workbench CPU when present
            if table_exists(cursor, "ServerMonitoringValues"):
                cursor.execute(
                    """
                    SELECT ServerNumber, CPU_Percent, UpdatedAt
                    FROM dbo.ServerMonitoringValues
                    WHERE ServerNumber BETWEEN 1 AND 4
                    ORDER BY ServerNumber
                    """
                )
                for row in cursor.fetchall():
                    server = int(row[0])
                    result[server] = {
                        "cpu": as_float(row[1]),
                        "updated_at": row[2].isoformat() if row[2] else None,
                        "source": "ServerMonitoringValues",
                    }

            if table_exists(cursor, "ServerCPUWorkbench"):
                cursor.execute(
                    """
                    SELECT ServerNumber, CPU_Percent, UpdatedAt
                    FROM dbo.ServerCPUWorkbench
                    WHERE ServerNumber BETWEEN 1 AND 4
                    ORDER BY ServerNumber
                    """
                )
                for row in cursor.fetchall():
                    server = int(row[0])
                    # Keep APPLY-table value available; do not wipe MonitoringValues if
                    # APPLY table is older — still expose it when MonitoringValues missing.
                    if server not in result:
                        result[server] = {
                            "cpu": as_float(row[1]),
                            "updated_at": row[2].isoformat() if row[2] else None,
                            "source": "ServerCPUWorkbench",
                        }
                    else:
                        result[server]["cpu_apply"] = as_float(row[1])
                        result[server]["cpu_apply_updated_at"] = (
                            row[2].isoformat() if row[2] else None
                        )
    except Exception as error:
        print(f"Workbench read failed: {error}")
    return result


METRIC_TAG_SUFFIX = {
    "cpu": ("CPU_Percent", "%"),
    "ram": ("RAM_Percent", "%"),
    "disk": ("Disk_Percent", "%"),
    "temperature": ("Temp_C", "°C"),
    "network": ("Network_Mbps", "Mbps"),
    "latency": ("Latency_ms", "ms"),
    "status": ("Status", ""),
}


def build_compare_payload() -> dict[str, Any]:
    with LOCK:
        tags = state.copy()
        connected = db_connected
        db_error = last_database_error

    tag_rows = read_latest_tag_values()
    tag_map = {item["tag"]: item for item in tag_rows}
    workbench = read_cpu_workbench()
    prediction_payload = predict_servers(tags)
    predictions = {
        int(item["server"]): item for item in prediction_payload.get("predictions", [])
    }

    servers: list[dict[str, Any]] = []
    for number in range(1, 5):
        metrics = []
        for key, (suffix, unit) in METRIC_TAG_SUFFIX.items():
            tag_name = f"Server{number}_{suffix}"
            sql_value = tags.get(tag_name)
            tag_item = tag_map.get(tag_name)
            workbench_value = None
            workbench_updated = None
            if key == "cpu" and number in workbench:
                workbench_value = workbench[number]["cpu"]
                workbench_updated = workbench[number]["updated_at"]

            tag_value = tag_item["value"] if tag_item else None
            delta_sql_tag = None
            if isinstance(sql_value, (int, float, bool)) and isinstance(tag_value, (int, float, bool)):
                delta_sql_tag = round(float(sql_value) - float(tag_value), 2)
            delta_sql_workbench = None
            if key == "cpu" and isinstance(sql_value, (int, float)) and workbench_value is not None:
                delta_sql_workbench = round(float(sql_value) - float(workbench_value), 2)

            metrics.append(
                {
                    "metric": key,
                    "unit": unit,
                    "tag_name": tag_name,
                    "sql_value": sql_value,
                    "workbench_tag_value": tag_value,
                    "workbench_tag_updated_at": tag_item["updated_at"] if tag_item else None,
                    "cpu_workbench_value": workbench_value,
                    "cpu_workbench_updated_at": workbench_updated,
                    "delta_sql_minus_tag": delta_sql_tag,
                    "delta_sql_minus_workbench": delta_sql_workbench,
                }
            )

        pred = predictions.get(number)
        servers.append(
            {
                "server": number,
                "metrics": metrics,
                "ai": pred,
            }
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "database_connected": connected,
        "database_error": db_error,
        "model_available": bool(prediction_payload.get("model_available")),
        "model_error": prediction_payload.get("model_error"),
        "servers": servers,
        "tags": tag_rows,
        "workbench": [
            {"server": number, **payload} for number, payload in sorted(workbench.items())
        ],
    }


def build_db_status() -> dict[str, Any]:
    global db_connected, last_database_error
    tables_checked = [
        "CurrentServerState",
        "LatestTagValues",
        "ServerMonitoringValues",
        "WB_Server1Tags",
        "WB_Server2Tags",
        "WB_Server3Tags",
        "WB_Server4Tags",
        "ServerMonitoringHistory",
        "ServerHistory",
        "ServerCPUWorkbench",
        "AlarmEvents",
        "ServerMetrics",
    ]
    present: list[str] = []
    missing: list[str] = []
    database_name = None
    history_table = None
    probe_ok = False
    probe_error = None

    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            cursor.execute("SELECT DB_NAME()")
            database_name = cursor.fetchone()[0]
            for name in tables_checked:
                if table_exists(cursor, name):
                    present.append(name)
                else:
                    missing.append(name)
            history_table = resolve_history_table(cursor)
            probe_ok = True
    except Exception as error:  # noqa: BLE001
        probe_error = str(error)

    with LOCK:
        last_error = last_database_error or probe_error
        last_update = last_update_time.isoformat() if last_update_time else None
        if probe_ok:
            db_connected = True
            if probe_error is None:
                last_database_error = None
        connected = bool(probe_ok)

    age_seconds = None
    if last_update_time:
        age_seconds = max(0, int((datetime.now() - last_update_time).total_seconds()))

    return {
        "database_connected": connected,
        "database_name": database_name or "DataCenterKPI",
        "database_error": None if connected else last_error,
        "last_update": last_update,
        "last_update_age_seconds": age_seconds,
        "history_table": history_table,
        "tables_present": present,
        "tables_missing": missing,
        "required_ok": (
            "CurrentServerState" in present
            and "LatestTagValues" in present
            and history_table is not None
        ),
        "timestamp": datetime.now().isoformat(),
        "status_label": (
            f"Connected to {database_name or 'DataCenterKPI'}"
            if connected
            else "Disconnected"
        ),
    }


def normalize_event_status(severity: Any, event_name: Any) -> str:
    severity_text = str(severity or "").strip().upper()
    event_text = str(event_name or "").strip().lower()
    if severity_text in {"RECOVERY", "CLEARED", "NORMAL", "RESOLVED"}:
        return "CLEARED"
    if any(word in event_text for word in ("returned to normal", "restored", "cleared", "resolved")):
        return "CLEARED"
    if severity_text in {"CRITICAL", "HIGH", "ACTIVE", "ALARM", "WARNING"}:
        return "ACTIVE"
    return severity_text or "INFO"


def read_events(limit: int = 50) -> list[dict[str, Any]]:
    limit = int(clamp(limit, 1, 500))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "AlarmEvents"):
                return []
            cursor.execute(
                f"""
                SELECT TOP {limit} EventTime, ServerNumber, EventName, Severity
                FROM dbo.AlarmEvents
                ORDER BY EventTime DESC
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "server": int(row[1]) if row[1] is not None else None,
                "event": str(row[2] or "System event"),
                "severity": str(row[3] or "INFO").upper(),
                "status": normalize_event_status(row[3], row[2]),
            }
            for row in rows
        ]
    except Exception as error:
        print(f"Alarm event read failed: {error}")
        return []


def read_top_alarms_per_server(per_server: int = 3) -> list[dict[str, Any]]:
    """Latest N AlarmEvents rows for each of servers 1–4 (newest first)."""
    per_server = int(clamp(per_server, 1, 20))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "AlarmEvents"):
                return []
            cursor.execute(
                f"""
                WITH Ranked AS (
                    SELECT
                        EventTime,
                        ServerNumber,
                        EventName,
                        Severity,
                        ROW_NUMBER() OVER (
                            PARTITION BY ServerNumber
                            ORDER BY EventTime DESC
                        ) AS rn
                    FROM dbo.AlarmEvents
                    WHERE ServerNumber BETWEEN 1 AND 4
                )
                SELECT EventTime, ServerNumber, EventName, Severity, rn
                FROM Ranked
                WHERE rn <= {per_server}
                ORDER BY ServerNumber, EventTime DESC
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "server": int(row[1]) if row[1] is not None else None,
                "event": str(row[2] or "System event"),
                "severity": str(row[3] or "INFO").upper(),
                "status": normalize_event_status(row[3], row[2]),
                "rank": int(row[4]),
            }
            for row in rows
        ]
    except Exception as error:
        print(f"Per-server alarm read failed: {error}")
        return []


def build_executive_payload() -> dict[str, Any]:
    """CEO / Top Level Management aggregates: pies, monthly trend, top performers."""
    with LOCK:
        tags = state.copy()
        connected = db_connected

    analytics = build_ai_analysis(tags)
    servers = []
    for number in range(1, 5):
        cpu = as_float(tags.get(f"Server{number}_CPU_Percent"))
        ram = as_float(tags.get(f"Server{number}_RAM_Percent"))
        disk = as_float(tags.get(f"Server{number}_Disk_Percent"))
        temp = as_float(tags.get(f"Server{number}_Temp_C"))
        net = as_float(tags.get(f"Server{number}_Network_Mbps"))
        lat = as_float(tags.get(f"Server{number}_Latency_ms"))
        status = as_bool(tags.get(f"Server{number}_Status"))
        cpu_alarm = as_bool(tags.get(f"Server{number}_CPU_Alarm"))
        temp_alarm = as_bool(tags.get(f"Server{number}_Temp_Alarm"))
        down_alarm = as_bool(tags.get(f"Server{number}_Down_Alarm"))

        # Higher score = better for executives (capacity headroom + availability)
        pressure = (
            clamp(cpu / 100.0, 0, 1) * 0.35
            + clamp(ram / 100.0, 0, 1) * 0.20
            + clamp(disk / 100.0, 0, 1) * 0.15
            + clamp(temp / 90.0, 0, 1) * 0.20
            + clamp(lat / 100.0, 0, 1) * 0.10
        )
        score = round(max(0.0, 100.0 * (1.0 - pressure) * (1.0 if status else 0.35)), 1)
        if cpu_alarm or temp_alarm or down_alarm:
            score = round(score * 0.75, 1)

        servers.append(
            {
                "server": number,
                "label": f"Server {number}",
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "temperature": temp,
                "network": net,
                "latency": lat,
                "status": status,
                "performance_score": score,
                "alarms": int(cpu_alarm) + int(temp_alarm) + int(down_alarm),
            }
        )

    total_cpu = sum(s["cpu"] for s in servers) or 1.0
    pie_load = [
        {
            "server": s["server"],
            "label": s["label"],
            "value": round(s["cpu"], 1),
            "share_pct": round(100.0 * s["cpu"] / total_cpu, 1),
        }
        for s in servers
    ]
    online = sum(1 for s in servers if s["status"])
    pie_status = [
        {"label": "Online", "value": online, "color": "#2bb673"},
        {"label": "Offline", "value": 4 - online, "color": "#e55353"},
    ]
    healthy = sum(1 for s in servers if s["alarms"] == 0 and s["status"])
    warning = sum(1 for s in servers if s["alarms"] > 0 and s["status"])
    critical = sum(1 for s in servers if not s["status"] or s["alarms"] >= 2)
    pie_health = [
        {"label": "Healthy", "value": healthy, "color": "#2bb673"},
        {"label": "Watch", "value": warning, "color": "#e8a838"},
        {"label": "Critical", "value": critical, "color": "#e55353"},
    ]

    monthly = _executive_monthly_performance()
    ranked = sorted(servers, key=lambda s: s["performance_score"], reverse=True)
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx

    fleet_avg_score = round(sum(s["performance_score"] for s in servers) / max(len(servers), 1), 1)
    risk_heatmap = _executive_risk_heatmap(servers)
    capacity_headroom = _executive_capacity_headroom(servers)
    alarm_trend = _executive_alarm_trend()

    return {
        "generated_at": datetime.now().isoformat(),
        "database_connected": connected,
        "title": "TOP LEVEL MANAGEMENT",
        "kpis": {
            "health_score": analytics.get("system", {}).get("health_score"),
            "risk_label": analytics.get("system", {}).get("risk_label"),
            "risk_score": analytics.get("system", {}).get("risk_score"),
            "risk_drivers": analytics.get("system", {}).get("risk_drivers") or [],
            "servers_online": online,
            "total_servers": 4,
            "fleet_performance": fleet_avg_score,
            "avg_cpu": round(sum(s["cpu"] for s in servers) / 4, 1),
            "avg_temp": round(sum(s["temperature"] for s in servers) / 4, 1),
            "total_network": round(sum(s["network"] for s in servers), 1),
            "fleet_cpu_headroom": capacity_headroom.get("fleet_cpu_headroom"),
            "hotspots": sum(1 for row in risk_heatmap for cell in row["cells"] if cell["level"] != "ok"),
        },
        "pie_load_share": pie_load,
        "pie_status": pie_status,
        "pie_health": pie_health,
        "monthly_performance": monthly,
        "top_performance": ranked,
        "risk_heatmap": risk_heatmap,
        "capacity_headroom": capacity_headroom,
        "alarm_trend": alarm_trend,
        "servers": servers,
    }


def _metric_risk_level(value: float, warn: float, crit: float, *, higher_is_worse: bool = True) -> str:
    if not higher_is_worse:
        if value <= crit:
            return "crit"
        if value <= warn:
            return "warn"
        return "ok"
    if value >= crit:
        return "crit"
    if value >= warn:
        return "warn"
    return "ok"


def _executive_risk_heatmap(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Servers × KPI risk matrix for CEO 'where is the fire?' view."""
    metrics = [
        ("cpu", "CPU", "cpu", THRESHOLDS["cpu_warning"], THRESHOLDS["cpu_critical"], "%"),
        ("ram", "RAM", "ram", THRESHOLDS["ram_warning"], THRESHOLDS["ram_critical"], "%"),
        ("disk", "Disk", "disk", THRESHOLDS["disk_warning"], THRESHOLDS["disk_critical"], "%"),
        ("temperature", "Temp", "temperature", THRESHOLDS["temp_warning"], THRESHOLDS["temp_critical"], "°C"),
        ("latency", "Latency", "latency", THRESHOLDS["latency_warning"], THRESHOLDS["latency_critical"], "ms"),
    ]
    rows = []
    for s in servers:
        cells = []
        for key, label, field, warn, crit, unit in metrics:
            value = as_float(s.get(field))
            level = "crit" if not s.get("status") and key == "cpu" else _metric_risk_level(value, warn, crit)
            if not s.get("status") and key in {"cpu", "ram", "disk", "temperature", "latency"}:
                # Offline server is always a hotspot for availability-sensitive KPIs
                if key == "latency":
                    level = "crit"
            cells.append(
                {
                    "metric": key,
                    "label": label,
                    "value": round(value, 1),
                    "unit": unit,
                    "level": level,
                    "warn": warn,
                    "crit": crit,
                }
            )
        rows.append(
            {
                "server": s["server"],
                "label": s["label"],
                "status": s["status"],
                "cells": cells,
            }
        )
    return rows


def _executive_capacity_headroom(servers: list[dict[str, Any]]) -> dict[str, Any]:
    """Remaining room before warning thresholds (higher = safer)."""
    per_server = []
    for s in servers:
        cpu = as_float(s.get("cpu"))
        ram = as_float(s.get("ram"))
        disk = as_float(s.get("disk"))
        temp = as_float(s.get("temperature"))
        lat = as_float(s.get("latency"))

        def room(value: float, warn: float) -> float:
            if warn <= 0:
                return 0.0
            return round(max(0.0, min(100.0, ((warn - value) / warn) * 100.0)), 1)

        cpu_h = room(cpu, THRESHOLDS["cpu_warning"])
        ram_h = room(ram, THRESHOLDS["ram_warning"])
        disk_h = room(disk, THRESHOLDS["disk_warning"])
        temp_h = room(temp, THRESHOLDS["temp_warning"])
        lat_h = room(lat, THRESHOLDS["latency_warning"])
        if not s.get("status"):
            cpu_h = ram_h = disk_h = temp_h = lat_h = 0.0
        overall = round((cpu_h * 0.35 + ram_h * 0.2 + disk_h * 0.15 + temp_h * 0.2 + lat_h * 0.1), 1)
        per_server.append(
            {
                "server": s["server"],
                "label": s["label"],
                "cpu_headroom": cpu_h,
                "ram_headroom": ram_h,
                "disk_headroom": disk_h,
                "temp_headroom": temp_h,
                "latency_headroom": lat_h,
                "overall_headroom": overall,
                "status": s["status"],
            }
        )

    fleet_cpu = round(sum(p["cpu_headroom"] for p in per_server) / max(len(per_server), 1), 1)
    fleet_overall = round(sum(p["overall_headroom"] for p in per_server) / max(len(per_server), 1), 1)
    return {
        "fleet_cpu_headroom": fleet_cpu,
        "fleet_overall_headroom": fleet_overall,
        "thresholds": {
            "cpu_warning": THRESHOLDS["cpu_warning"],
            "ram_warning": THRESHOLDS["ram_warning"],
            "disk_warning": THRESHOLDS["disk_warning"],
            "temp_warning": THRESHOLDS["temp_warning"],
            "latency_warning": THRESHOLDS["latency_warning"],
        },
        "servers": per_server,
    }


def _executive_alarm_trend() -> dict[str, Any]:
    """ACTIVE vs CLEARED alarm counts over last 24h (hourly) and 7d (daily)."""
    empty = {
        "hours_24": [],
        "days_7": [],
        "active_24h": 0,
        "cleared_24h": 0,
        "active_7d": 0,
        "cleared_7d": 0,
    }
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            if not table_exists(cursor, "AlarmEvents"):
                return empty

            cursor.execute(
                """
                SELECT EventTime, Severity, EventName
                FROM dbo.AlarmEvents
                WHERE EventTime >= DATEADD(day, -7, GETDATE())
                ORDER BY EventTime
                """
            )
            rows = cursor.fetchall()

        now = datetime.now()
        hours = [
            {
                "label": (now - timedelta(hours=23 - i)).strftime("%H:00"),
                "hour_start": (now - timedelta(hours=23 - i)).replace(minute=0, second=0, microsecond=0),
                "active": 0,
                "cleared": 0,
            }
            for i in range(24)
        ]
        days = [
            {
                "label": (now - timedelta(days=6 - i)).strftime("%a"),
                "day_start": (now - timedelta(days=6 - i)).replace(hour=0, minute=0, second=0, microsecond=0),
                "active": 0,
                "cleared": 0,
            }
            for i in range(7)
        ]

        active_24h = cleared_24h = active_7d = cleared_7d = 0
        cutoff_24 = now - timedelta(hours=24)
        for event_time, severity, event_name in rows:
            if not event_time:
                continue
            if isinstance(event_time, str):
                try:
                    event_time = datetime.fromisoformat(event_time)
                except ValueError:
                    continue
            status = normalize_event_status(severity, event_name)
            is_active = status == "ACTIVE"
            # 7d daily
            day_key = event_time.replace(hour=0, minute=0, second=0, microsecond=0)
            for bucket in days:
                if bucket["day_start"] == day_key:
                    if is_active:
                        bucket["active"] += 1
                        active_7d += 1
                    else:
                        bucket["cleared"] += 1
                        cleared_7d += 1
                    break
            # 24h hourly
            if event_time >= cutoff_24:
                hour_key = event_time.replace(minute=0, second=0, microsecond=0)
                for bucket in hours:
                    if bucket["hour_start"] == hour_key:
                        if is_active:
                            bucket["active"] += 1
                            active_24h += 1
                        else:
                            bucket["cleared"] += 1
                            cleared_24h += 1
                        break

        for bucket in hours:
            bucket.pop("hour_start", None)
        for bucket in days:
            bucket.pop("day_start", None)

        return {
            "hours_24": hours,
            "days_7": days,
            "active_24h": active_24h,
            "cleared_24h": cleared_24h,
            "active_7d": active_7d,
            "cleared_7d": cleared_7d,
        }
    except Exception as error:
        print(f"Executive alarm trend failed: {error}")
        return empty


def _executive_monthly_performance() -> list[dict[str, Any]]:
    """Monthly avg CPU / performance for CEO trend chart."""
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            history_table = resolve_history_table(cursor)
            rows: list[tuple[Any, ...]] = []
            if history_table:
                temp_col = history_temp_column(cursor, history_table)
                cursor.execute(
                    f"""
                    SELECT
                        YEAR(RecordedAt) AS Y,
                        MONTH(RecordedAt) AS M,
                        AVG(CAST(CPU_Percent AS FLOAT)) AS AvgCPU,
                        AVG(CAST(RAM_Percent AS FLOAT)) AS AvgRAM,
                        AVG(CAST({temp_col} AS FLOAT)) AS AvgTemp,
                        COUNT(*) AS Samples
                    FROM dbo.{history_table}
                    WHERE ServerNumber BETWEEN 1 AND 4
                      AND RecordedAt IS NOT NULL
                    GROUP BY YEAR(RecordedAt), MONTH(RecordedAt)
                    ORDER BY Y, M
                    """
                )
                rows = cursor.fetchall()

            if len(rows) >= 2:
                out = []
                for y, m, avg_cpu, avg_ram, avg_temp, samples in rows[-12:]:
                    cpu = as_float(avg_cpu)
                    score = round(max(0.0, 100.0 - cpu * 0.55 - as_float(avg_temp) * 0.25), 1)
                    out.append(
                        {
                            "year": int(y),
                            "month": int(m),
                            "label": f"{month_names[int(m) - 1]} {int(y)}",
                            "avg_cpu": round(cpu, 1),
                            "avg_ram": round(as_float(avg_ram), 1),
                            "avg_temp": round(as_float(avg_temp), 1),
                            "performance_score": score,
                            "samples": int(samples or 0),
                        }
                    )
                return out

            # Fallback: bucket ITSystemDataset into 12 executive months
            if table_exists(cursor, "ITSystemDataset"):
                cursor.execute(
                    """
                    SELECT
                        ((SourceRow - 1) % 12) + 1 AS MonthBucket,
                        AVG(CAST(CPU_Percent AS FLOAT)),
                        AVG(CAST(RAM_Percent AS FLOAT)),
                        AVG(CAST(Temperature_C AS FLOAT)),
                        COUNT(*)
                    FROM dbo.ITSystemDataset
                    GROUP BY ((SourceRow - 1) % 12) + 1
                    ORDER BY MonthBucket
                    """
                )
                year = datetime.now().year
                out = []
                for m, avg_cpu, avg_ram, avg_temp, samples in cursor.fetchall():
                    cpu = as_float(avg_cpu)
                    score = round(max(0.0, 100.0 - cpu * 0.55 - as_float(avg_temp) * 0.25), 1)
                    out.append(
                        {
                            "year": year,
                            "month": int(m),
                            "label": month_names[int(m) - 1],
                            "avg_cpu": round(cpu, 1),
                            "avg_ram": round(as_float(avg_ram), 1),
                            "avg_temp": round(as_float(avg_temp), 1),
                            "performance_score": score,
                            "samples": int(samples or 0),
                        }
                    )
                return out
    except Exception as error:
        print(f"Executive monthly aggregate failed: {error}")

    # Last-resort synthetic months from live tags
    with LOCK:
        tags = state.copy()
    base_cpu = as_float(tags.get("DC_Avg_CPU")) or 45.0
    out = []
    for i, name in enumerate(month_names):
        wobble = math.sin(i / 2.2) * 8 + ((i * 3) % 7)
        cpu = clamp(base_cpu + wobble, 5, 95)
        out.append(
            {
                "year": datetime.now().year,
                "month": i + 1,
                "label": name,
                "avg_cpu": round(cpu, 1),
                "avg_ram": round(clamp(base_cpu + 5 + wobble * 0.6, 10, 95), 1),
                "avg_temp": round(clamp(50 + wobble * 0.4, 30, 90), 1),
                "performance_score": round(max(0.0, 100.0 - cpu * 0.55), 1),
                "samples": 0,
            }
        )
    return out


def build_alarm_history_payload(per_server: int = 3) -> dict[str, Any]:
    """Top alarms per server + live metric readings from CurrentServerState/tags."""
    per_server = int(clamp(per_server, 1, 20))
    events = read_top_alarms_per_server(per_server)
    with LOCK:
        tags = state.copy()
        connected = db_connected

    by_server: dict[int, list[dict[str, Any]]] = {i: [] for i in range(1, 5)}
    for item in events:
        server = item.get("server")
        if server in by_server:
            # Attach live readings at event-list time so the UI can show current values
            item = {
                **item,
                "live": {
                    "cpu": as_float(tags.get(f"Server{server}_CPU_Percent")),
                    "ram": as_float(tags.get(f"Server{server}_RAM_Percent")),
                    "disk": as_float(tags.get(f"Server{server}_Disk_Percent")),
                    "temperature": as_float(tags.get(f"Server{server}_Temp_C")),
                    "network": as_float(tags.get(f"Server{server}_Network_Mbps")),
                    "latency": as_float(tags.get(f"Server{server}_Latency_ms")),
                    "status": as_bool(tags.get(f"Server{server}_Status")),
                },
            }
            by_server[server].append(item)

    servers = []
    for number in range(1, 5):
        live = {
            "cpu": as_float(tags.get(f"Server{number}_CPU_Percent")),
            "ram": as_float(tags.get(f"Server{number}_RAM_Percent")),
            "disk": as_float(tags.get(f"Server{number}_Disk_Percent")),
            "temperature": as_float(tags.get(f"Server{number}_Temp_C")),
            "network": as_float(tags.get(f"Server{number}_Network_Mbps")),
            "latency": as_float(tags.get(f"Server{number}_Latency_ms")),
            "status": as_bool(tags.get(f"Server{number}_Status")),
            "cpu_alarm": as_bool(tags.get(f"Server{number}_CPU_Alarm")),
            "temp_alarm": as_bool(tags.get(f"Server{number}_Temp_Alarm")),
            "down_alarm": as_bool(tags.get(f"Server{number}_Down_Alarm")),
        }
        servers.append(
            {
                "server": number,
                "live": live,
                "alarms": by_server[number],
                "alarm_count": len(by_server[number]),
            }
        )

    flat = [alarm for block in servers for alarm in block["alarms"]]
    return {
        "table": "AlarmEvents",
        "per_server": per_server,
        "database_connected": connected,
        "generated_at": datetime.now().isoformat(),
        "servers": servers,
        "events": flat,
        "total_events": len(flat),
        "active_count": sum(1 for item in flat if item.get("status") == "ACTIVE"),
    }


# ============================================================
# EXPLAINABLE AIOPS ANALYTICS
# ============================================================


def classify(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "healthy"


def calculate_health_score(server: dict[str, Any]) -> int:
    if not server["status"]:
        return 0

    score = 100.0
    score -= max(0.0, server["cpu"] - 65.0) * 0.60
    score -= max(0.0, server["ram"] - 70.0) * 0.45
    score -= max(0.0, server["disk"] - 75.0) * 0.35
    score -= max(0.0, server["temperature"] - 55.0) * 0.80
    score -= max(0.0, server["latency"] - 20.0) * 0.40
    return int(round(clamp(score, 0.0, 100.0)))


def health_label(score: int) -> str:
    if score >= 85:
        return "Healthy"
    if score >= 65:
        return "Watch"
    if score >= 40:
        return "Degraded"
    return "Critical"


def compute_business_risk(servers: list[dict[str, Any]], tags: dict[str, Any]) -> dict[str, Any]:
    """Composite business risk from offline, alarms, critical KPIs — not a static value.

    Previously risk was only ``100 - average_health``, which stayed High whenever the
    live dataset stressed CPUs/temps. This score weights operational signals that
    map to Alarm Summary / availability.
    """
    score = 0.0
    drivers: list[str] = []

    offline = [s["server"] for s in servers if not s.get("status")]
    if offline:
        score += min(40.0, len(offline) * 22.0)
        drivers.append(f"{len(offline)} offline")

    active_tag_alarms = 0
    for number in range(1, 5):
        for kind in ("CPU_Alarm", "Temp_Alarm", "Down_Alarm"):
            if as_bool(tags.get(f"Server{number}_{kind}")):
                active_tag_alarms += 1
    if active_tag_alarms:
        score += min(35.0, active_tag_alarms * 11.0)
        drivers.append(f"{active_tag_alarms} active alarms")

    critical_kpi = 0
    warning_kpi = 0
    for s in servers:
        if not s.get("status"):
            continue
        for key in ("cpu_state", "ram_state", "disk_state", "thermal_state", "latency_state"):
            state = s.get(key)
            if state == "critical":
                critical_kpi += 1
            elif state == "warning":
                warning_kpi += 1
    if critical_kpi:
        score += min(28.0, critical_kpi * 8.0)
        drivers.append(f"{critical_kpi} critical KPIs")
    if warning_kpi:
        score += min(12.0, warning_kpi * 2.0)

    # Soft contribution from fleet health (capped) so mild load alone is not "High"
    average_health = sum(float(s.get("health_score") or 0) for s in servers) / max(len(servers), 1)
    health_risk = max(0.0, 100.0 - average_health)
    score += min(18.0, health_risk * 0.22)

    # Recent ACTIVE alarm events (when history is available)
    try:
        events = read_events(80)
        cutoff = datetime.now() - timedelta(hours=24)
        active_events = 0
        for event in events:
            if str(event.get("status", "")).upper() != "ACTIVE":
                continue
            ts = event.get("timestamp")
            if isinstance(ts, str) and ts:
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone().replace(tzinfo=None)
                    if parsed < cutoff:
                        continue
                except ValueError:
                    pass
            elif isinstance(ts, datetime):
                if ts < cutoff:
                    continue
            active_events += 1
        if active_events:
            score += min(20.0, active_events * 4.0)
            if "active alarms" not in " ".join(drivers).lower():
                drivers.append(f"{active_events} alarm events (24h)")
    except Exception:  # noqa: BLE001
        pass

    risk_score = int(round(clamp(score, 0.0, 100.0)))
    if risk_score >= 70:
        risk_label = "Critical"
    elif risk_score >= 45:
        risk_label = "High"
    elif risk_score >= 20:
        risk_label = "Moderate"
    else:
        risk_label = "Low"

    if not drivers:
        drivers.append("no active operational threats")

    return {
        "risk_score": risk_score,
        "risk_label": risk_label,
        "risk_drivers": drivers,
    }


def server_snapshot(tags: dict[str, Any], server: int) -> dict[str, Any]:
    snapshot = {
        "server": server,
        "status": as_bool(tags.get(f"Server{server}_Status")),
        "cpu": as_float(tags.get(f"Server{server}_CPU_Percent")),
        "ram": as_float(tags.get(f"Server{server}_RAM_Percent")),
        "disk": as_float(tags.get(f"Server{server}_Disk_Percent")),
        "temperature": as_float(tags.get(f"Server{server}_Temp_C")),
        "network": as_float(tags.get(f"Server{server}_Network_Mbps")),
        "latency": as_float(tags.get(f"Server{server}_Latency_ms")),
        "alarms": {
            "cpu": as_bool(tags.get(f"Server{server}_CPU_Alarm")),
            "temperature": as_bool(tags.get(f"Server{server}_Temp_Alarm")),
            "down": as_bool(tags.get(f"Server{server}_Down_Alarm")),
        },
    }
    score = calculate_health_score(snapshot)
    snapshot.update(
        {
            "health_score": score,
            "health_label": health_label(score),
            "risk_score": 100 - score,
            "capacity_headroom": round(
                max(0.0, 100.0 - max(snapshot["cpu"], snapshot["ram"], snapshot["disk"])), 1
            ),
            "cpu_state": classify(
                snapshot["cpu"], THRESHOLDS["cpu_warning"], THRESHOLDS["cpu_critical"]
            ),
            "ram_state": classify(
                snapshot["ram"], THRESHOLDS["ram_warning"], THRESHOLDS["ram_critical"]
            ),
            "disk_state": classify(
                snapshot["disk"], THRESHOLDS["disk_warning"], THRESHOLDS["disk_critical"]
            ),
            "thermal_state": classify(
                snapshot["temperature"], THRESHOLDS["temp_warning"], THRESHOLDS["temp_critical"]
            ),
            "latency_state": classify(
                snapshot["latency"],
                THRESHOLDS["latency_warning"],
                THRESHOLDS["latency_critical"],
            ),
        }
    )
    return snapshot


def recommendation(
    *,
    server: int | None,
    priority: str,
    category: str,
    problem: str,
    evidence: str,
    impact: str,
    action: str,
    overcome: list[str],
    source_ids: list[str],
    confidence: int,
) -> dict[str, Any]:
    return {
        "server": server,
        "priority": priority,
        "category": category,
        "problem": problem,
        "evidence": evidence,
        "impact": impact,
        "recommended_action": action,
        "how_to_overcome": overcome,
        "source_ids": source_ids,
        "confidence": confidence,
    }


def build_ai_analysis(tags: dict[str, Any]) -> dict[str, Any]:
    servers = [server_snapshot(tags, i) for i in range(1, 5)]
    recommendations: list[dict[str, Any]] = []

    online_cpus = [s["cpu"] for s in servers if s["status"]]
    average_cpu = sum(online_cpus) / len(online_cpus) if online_cpus else 0.0

    for item in servers:
        number = item["server"]

        if not item["status"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Availability and resilience",
                    problem=f"Server {number} is offline",
                    evidence="Status is DOWN and the server-down alarm is active.",
                    impact="Loss of capacity can overload the remaining servers and may cause a cascading service failure.",
                    action="Start the incident recovery procedure and shift workload to healthy capacity.",
                    overcome=[
                        "Confirm power, network reachability and host/OS health.",
                        "Fail over or rebalance workloads to available servers.",
                        "Document the cause and validate redundancy after recovery.",
                    ],
                    source_ids=["UPTIME-OUTAGE-2026", "SRE-GOLDEN-SIGNALS"],
                    confidence=99,
                )
            )
            continue

        if item["cpu"] >= THRESHOLDS["cpu_critical"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Compute saturation",
                    problem=f"Server {number} CPU saturation",
                    evidence=f"CPU is {item['cpu']:.1f}% (critical threshold {THRESHOLDS['cpu_critical']:.0f}%).",
                    impact="Sustained saturation increases response time and raises the risk of timeout or overload.",
                    action="Identify the highest CPU consumers and move or scale the workload immediately.",
                    overcome=[
                        "Inspect top processes/services and recent workload changes.",
                        "Rebalance traffic to a lower-utilization server.",
                        "Add capacity or apply CPU limits after validating service requirements.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=98,
                )
            )
        elif item["cpu"] >= THRESHOLDS["cpu_warning"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="high",
                    category="Capacity management",
                    problem=f"Server {number} has low CPU headroom",
                    evidence=f"CPU is {item['cpu']:.1f}% and capacity headroom is {item['capacity_headroom']:.1f}%.",
                    impact="A traffic spike may push the server into saturation.",
                    action="Review workload growth and prepare load balancing or scaling before the critical limit.",
                    overcome=[
                        "Compare current CPU with the recent SQL history trend.",
                        "Schedule heavy jobs outside peak time.",
                        "Set an early-warning alert and confirm spare capacity.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS", "SCHNEIDER-PUE"],
                    confidence=93,
                )
            )

        if item["ram"] >= THRESHOLDS["ram_critical"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Memory pressure",
                    problem=f"Server {number} memory is critically utilized",
                    evidence=f"RAM is {item['ram']:.1f}%.",
                    impact="Memory pressure can cause paging, latency growth or application termination.",
                    action="Find memory-heavy services or leaks and reduce pressure before performance degrades.",
                    overcome=[
                        "Check process memory and swap/page-file activity.",
                        "Restart only the verified leaking service under change control.",
                        "Increase memory or move workloads if demand is legitimate and sustained.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=97,
                )
            )
        elif item["ram"] >= THRESHOLDS["ram_warning"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="high",
                    category="Memory capacity",
                    problem=f"Server {number} memory headroom is narrowing",
                    evidence=f"RAM is {item['ram']:.1f}%.",
                    impact="Reduced headroom makes the server sensitive to workload bursts.",
                    action="Review memory trend and workload placement.",
                    overcome=[
                        "Compare the last hour/day of RAM history.",
                        "Remove unnecessary resident services or rebalance workloads.",
                        "Plan additional memory if usage is consistently high.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=90,
                )
            )

        if item["disk"] >= THRESHOLDS["disk_critical"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Storage capacity",
                    problem=f"Server {number} disk utilization is critical",
                    evidence=f"Disk is {item['disk']:.1f}% full.",
                    impact="Full storage can stop logging, database writes, updates and application services.",
                    action="Free or extend storage immediately using an approved retention and capacity plan.",
                    overcome=[
                        "Identify the largest and fastest-growing files/directories.",
                        "Archive or delete data according to retention policy.",
                        "Extend the volume and add forecast alerts for future growth.",
                    ],
                    source_ids=["UPTIME-OUTAGE-2026", "SCHNEIDER-PUE"],
                    confidence=98,
                )
            )
        elif item["disk"] >= THRESHOLDS["disk_warning"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="high",
                    category="Storage forecasting",
                    problem=f"Server {number} disk capacity is approaching the limit",
                    evidence=f"Disk is {item['disk']:.1f}% full.",
                    impact="Continued growth can create an avoidable availability incident.",
                    action="Forecast time-to-full and schedule cleanup or expansion.",
                    overcome=[
                        "Review database, log and backup growth.",
                        "Apply retention/rotation rules.",
                        "Reserve expansion capacity before the critical threshold.",
                    ],
                    source_ids=["UPTIME-OUTAGE-2026"],
                    confidence=92,
                )
            )

        if item["temperature"] >= THRESHOLDS["temp_critical"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Thermal management",
                    problem=f"Server {number} temperature is critical",
                    evidence=f"The server sensor is {item['temperature']:.1f}Â°C and the thermal alarm threshold is {THRESHOLDS['temp_critical']:.0f}Â°C.",
                    impact="High component temperature can cause throttling, hardware stress or shutdown.",
                    action="Reduce compute load and inspect airflow/cooling immediately.",
                    overcome=[
                        "Verify fan operation, airflow obstruction and rack hot spots.",
                        "Reduce or migrate high-load workloads until temperature stabilizes.",
                        "Review cooling capacity and containment for recurring events.",
                    ],
                    source_ids=["ASHRAE-THERMAL", "SCHNEIDER-DLC-210"],
                    confidence=99,
                )
            )
        elif item["temperature"] >= THRESHOLDS["temp_warning"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="high",
                    category="Thermal headroom",
                    problem=f"Server {number} is running warm",
                    evidence=f"The server sensor is {item['temperature']:.1f}Â°C.",
                    impact="Reduced thermal headroom increases the chance of throttling during a load spike.",
                    action="Inspect cooling effectiveness and correlate temperature with CPU load.",
                    overcome=[
                        "Check rack airflow and nearby equipment heat output.",
                        "Compare temperature and CPU history for correlation.",
                        "Clean filters/vents and validate cooling setpoints under approved procedures.",
                    ],
                    source_ids=["ASHRAE-THERMAL", "SCHNEIDER-DLC-210"],
                    confidence=94,
                )
            )

        if item["latency"] >= THRESHOLDS["latency_critical"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="critical",
                    category="Network performance",
                    problem=f"Server {number} network latency is critical",
                    evidence=f"Latency is {item['latency']:.1f} ms.",
                    impact="High latency reduces application responsiveness and may trigger timeout/retry storms.",
                    action="Trace the network path and isolate congestion, packet loss or interface errors.",
                    overcome=[
                        "Check switch/interface utilization, errors and packet drops.",
                        "Compare latency with traffic volume and application errors.",
                        "Reroute or add capacity after locating the bottleneck.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=96,
                )
            )
        elif item["latency"] >= THRESHOLDS["latency_warning"]:
            recommendations.append(
                recommendation(
                    server=number,
                    priority="medium",
                    category="Network latency",
                    problem=f"Server {number} latency is elevated",
                    evidence=f"Latency is {item['latency']:.1f} ms.",
                    impact="Performance may degrade during higher traffic periods.",
                    action="Monitor latency trend together with network throughput and errors.",
                    overcome=[
                        "Compare peak and off-peak latency.",
                        "Check network queueing and interface utilization.",
                        "Define a service-specific latency objective.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=88,
                )
            )

        if (
            len(online_cpus) >= 2
            and item["cpu"] - average_cpu >= 25.0
            and min(online_cpus) <= 50.0
        ):
            recommendations.append(
                recommendation(
                    server=number,
                    priority="high",
                    category="Load balancing",
                    problem=f"Server {number} carries an uneven share of compute load",
                    evidence=f"CPU is {item['cpu']:.1f}% versus the online-server average of {average_cpu:.1f}%.",
                    impact="Load imbalance wastes available capacity and can create a localized overload.",
                    action="Redistribute eligible workloads or traffic to lower-utilization servers.",
                    overcome=[
                        "Confirm that the workload is horizontally movable.",
                        "Adjust load-balancer weights gradually.",
                        "Validate latency and error rates after redistribution.",
                    ],
                    source_ids=["SRE-GOLDEN-SIGNALS"],
                    confidence=91,
                )
            )

    if not recommendations:
        recommendations.append(
            recommendation(
                server=None,
                priority="low",
                category="Preventive operations",
                problem="No immediate KPI risk detected",
                evidence="All four servers are within the project warning thresholds.",
                impact="The environment is stable, but preventive monitoring is still required.",
                action="Continue trend review, capacity forecasting and resilience testing.",
                overcome=[
                    "Review weekly CPU, RAM, disk, temperature and latency trends.",
                    "Test alert routing and recovery procedures.",
                    "Keep documented capacity and cooling headroom targets.",
                ],
                source_ids=["UPTIME-OUTAGE-2026", "SCHNEIDER-PUE"],
                confidence=95,
            )
        )

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda item: (priority_order.get(item["priority"], 9), item["server"] or 0))

    average_health = round(sum(s["health_score"] for s in servers) / len(servers), 1)
    business_risk = compute_business_risk(servers, tags)
    system_risk = business_risk["risk_score"]
    critical_count = sum(1 for r in recommendations if r["priority"] == "critical")
    high_count = sum(1 for r in recommendations if r["priority"] == "high")

    challenges = [
        {
            "name": "Availability and outage resilience",
            "active": any(not s["status"] for s in servers),
            "description": "A server outage reduces capacity and can increase load on remaining assets.",
            "source_ids": ["UPTIME-OUTAGE-2026"],
        },
        {
            "name": "Compute and memory saturation",
            "active": any(s["cpu_state"] != "healthy" or s["ram_state"] != "healthy" for s in servers),
            "description": "Saturation is a core reliability signal and should be reviewed with latency and traffic.",
            "source_ids": ["SRE-GOLDEN-SIGNALS"],
        },
        {
            "name": "Thermal management",
            "active": any(s["thermal_state"] != "healthy" for s in servers),
            "description": "Thermal headroom and cooling effectiveness directly affect stable server operation.",
            "source_ids": ["ASHRAE-THERMAL", "SCHNEIDER-DLC-210"],
        },
        {
            "name": "Storage exhaustion",
            "active": any(s["disk_state"] != "healthy" for s in servers),
            "description": "Storage growth must be forecast before full disks interrupt logs, databases or services.",
            "source_ids": ["UPTIME-OUTAGE-2026"],
        },
        {
            "name": "Network latency and traffic",
            "active": any(s["latency_state"] != "healthy" for s in servers),
            "description": "Latency and traffic should be monitored together to locate user-visible degradation.",
            "source_ids": ["SRE-GOLDEN-SIGNALS"],
        },
        {
            "name": "Balanced, holistic KPI management",
            "active": any(abs(s["cpu"] - average_cpu) >= 25 for s in servers if s["status"]),
            "description": "No single KPI is enough; operational decisions should combine capacity, thermal and network signals.",
            "source_ids": ["SCHNEIDER-PUE", "SRE-GOLDEN-SIGNALS"],
        },
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "engine": {
            "name": "Explainable AIOps Recommendation Engine",
            "type": "Deterministic rule-based decision support",
            "data_source": "Live SQL Server values written by AVEVA",
            "note": "Recommendations are evidence-based operational guidance, not autonomous control actions.",
        },
        "system": {
            "health_score": average_health,
            "risk_score": system_risk,
            "risk_label": business_risk["risk_label"],
            "risk_drivers": business_risk["risk_drivers"],
            "critical_recommendations": critical_count,
            "high_recommendations": high_count,
            "servers_online": sum(1 for s in servers if s["status"]),
            "total_servers": 4,
        },
        "server_kpis": servers,
        "challenges": challenges,
        "recommendations": recommendations,
        "sources": AI_SOURCES,
        "thresholds": THRESHOLDS,
    }


# ============================================================
# REPORT DATA
# ============================================================


def parse_iso_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is not None:
            result = result.astimezone().replace(tzinfo=None)
        return result
    except ValueError:
        try:
            result = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                result = result + timedelta(days=1) - timedelta(microseconds=1)
            return result
        except ValueError:
            return None


def resolve_range(range_name: str, date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    now = datetime.now()
    if range_name == "1h":
        return now - timedelta(hours=1), now
    if range_name == "24h":
        return now - timedelta(hours=24), now
    if range_name == "7d":
        return now - timedelta(days=7), now
    if range_name == "30d":
        return now - timedelta(days=30), now
    if range_name == "custom":
        return parse_iso_datetime(date_from), parse_iso_datetime(date_to, end_of_day=True)
    return None, None


def read_report_rows(
    *,
    server_scope: int | None,
    range_name: str,
    date_from: str | None,
    date_to: str | None,
    max_rows: int = 10000,
) -> list[dict[str, Any]]:
    start_time, end_time = resolve_range(range_name, date_from, date_to)

    if range_name == "current":
        with LOCK:
            tags = state.copy()
        selected = [server_scope] if server_scope else list(range(1, 5))
        rows = []
        for number in selected:
            item = server_snapshot(tags, number)
            rows.append(
                {
                    "timestamp": last_update_time or datetime.now(),
                    "server": number,
                    "cpu": item["cpu"],
                    "ram": item["ram"],
                    "disk": item["disk"],
                    "temperature": item["temperature"],
                    "network": item["network"],
                    "latency": item["latency"],
                    "status": item["status"],
                    "health_score": item["health_score"],
                }
            )
        return rows

    clauses = ["1 = 1"]
    params: list[Any] = []
    if server_scope:
        clauses.append("ServerNumber = ?")
        params.append(server_scope)
    if start_time:
        clauses.append("RecordedAt >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("RecordedAt <= ?")
        params.append(end_time)

    max_rows = int(clamp(max_rows, 1, 50000))
    try:
        connection = get_connection()
        with connection:
            cursor = connection.cursor()
            table_name = resolve_history_table(cursor)
            if not table_name:
                return []
            temp_col = history_temp_column(cursor, table_name)
            cursor.execute(
                f"""
                SELECT TOP {max_rows}
                    RecordedAt, ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                    {temp_col}, Network_Mbps, Latency_ms, Status
                FROM dbo.{table_name}
                WHERE {' AND '.join(clauses)}
                ORDER BY RecordedAt ASC
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "timestamp": row[0],
                "server": int(row[1]),
                "cpu": as_float(row[2]),
                "ram": as_float(row[3]),
                "disk": as_float(row[4]),
                "temperature": as_float(row[5]),
                "network": as_float(row[6]),
                "latency": as_float(row[7]),
                "status": as_bool(row[8]),
            }
            for row in rows
        ]
    except Exception as error:
        print(f"Report history read failed: {error}")
        return []


def aggregate_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["server"]), []).append(row)

    result = []
    for server, items in sorted(grouped.items()):
        def avg(key: str) -> float:
            values = [as_float(item.get(key)) for item in items]
            return round(sum(values) / len(values), 2) if values else 0.0

        result.append(
            {
                "server": server,
                "samples": len(items),
                "cpu_avg": avg("cpu"),
                "cpu_max": round(max(as_float(i.get("cpu")) for i in items), 2),
                "ram_avg": avg("ram"),
                "disk_avg": avg("disk"),
                "disk_max": round(max(as_float(i.get("disk")) for i in items), 2),
                "temp_avg": avg("temperature"),
                "temp_max": round(max(as_float(i.get("temperature")) for i in items), 2),
                "network_avg": avg("network"),
                "latency_avg": avg("latency"),
                "latency_max": round(max(as_float(i.get("latency")) for i in items), 2),
                "availability_percent": round(
                    100.0 * sum(1 for i in items if as_bool(i.get("status"))) / len(items), 2
                ),
            }
        )
    return result


def build_report_briefing(
    analytics: dict[str, Any],
    options: dict[str, Any],
    aggregates: list[dict[str, Any]],
    row_count: int,
) -> dict[str, Any]:
    """Executive narrative + per-server status snapshot for preview/PDF."""
    system = analytics.get("system") or {}
    servers = analytics.get("server_kpis") or []
    selected = (
        [options["server_scope"]] if options.get("server_scope") else list(range(1, 5))
    )
    scoped = [s for s in servers if s.get("server") in selected]

    offline = [s["server"] for s in scoped if not s.get("status")]
    hot = [
        s["server"]
        for s in scoped
        if s.get("status")
        and (
            s.get("cpu_state") == "critical"
            or s.get("thermal_state") == "critical"
            or s.get("disk_state") == "critical"
        )
    ]
    risk_label = system.get("risk_label") or "Unknown"
    online = system.get("servers_online", 0)
    total = system.get("total_servers", 4)
    health = float(system.get("health_score") or 0)

    parts: list[str] = []
    parts.append(
        f"Fleet health is {health:.1f}/100 with business risk marked {risk_label} "
        f"({system.get('risk_score', 0)}/100). {online}/{total} servers are online."
    )
    if offline:
        parts.append(
            "Offline: "
            + ", ".join(f"Server {n}" for n in offline)
            + " — restore power/status tags before trusting capacity readings."
        )
    if hot:
        parts.append(
            "Critical KPI pressure on "
            + ", ".join(f"Server {n}" for n in hot)
            + "."
        )
    if not offline and not hot:
        parts.append("No servers are offline; continue monitoring headroom and alarm trend.")
    if row_count:
        parts.append(f"This report includes {row_count} SQL history samples for the selected range.")
    else:
        parts.append("No history samples matched the selected range — figures use the live snapshot.")

    status_rows = []
    for s in scoped:
        status_rows.append(
            {
                "server": s.get("server"),
                "status": "Online" if s.get("status") else "Offline",
                "health_score": round(float(s.get("health_score") or 0), 1),
                "cpu": round(float(s.get("cpu") or 0), 1),
                "ram": round(float(s.get("ram") or 0), 1),
                "disk": round(float(s.get("disk") or 0), 1),
                "temperature": round(float(s.get("temperature") or 0), 1),
                "latency": round(float(s.get("latency") or 0), 1),
                "headroom": round(float(s.get("capacity_headroom") or 0), 1),
                "risk_score": int(s.get("risk_score") or 0),
                "flags": ", ".join(
                    [
                        name
                        for name, key in (
                            ("CPU", "cpu_state"),
                            ("RAM", "ram_state"),
                            ("Disk", "disk_state"),
                            ("Temp", "thermal_state"),
                            ("Latency", "latency_state"),
                        )
                        if s.get(key) in {"warning", "critical"}
                    ]
                )
                or ("OFFLINE" if not s.get("status") else "OK"),
            }
        )

    events = read_events(80)
    if options.get("server_scope"):
        events = [e for e in events if e.get("server") == options["server_scope"]]
    active = sum(1 for e in events if str(e.get("status", "")).upper() == "ACTIVE")
    cleared = sum(1 for e in events if str(e.get("status", "")).upper() == "CLEARED")

    return {
        "narrative": " ".join(parts),
        "offline_servers": offline,
        "hot_servers": hot,
        "status_rows": status_rows,
        "alarm_active": active,
        "alarm_cleared": cleared,
        "alarm_sample": events[:12],
        "thresholds": analytics.get("thresholds") or THRESHOLDS,
        "aggregates_count": len(aggregates),
    }


def build_report_preview(options: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        tags = state.copy()
    analytics = build_ai_analysis(tags)
    rows = read_report_rows(
        server_scope=options["server_scope"],
        range_name=options["range"],
        date_from=options["date_from"],
        date_to=options["date_to"],
        max_rows=5000,
    )
    aggregates = aggregate_report_rows(rows)
    selected_servers = (
        [options["server_scope"]] if options["server_scope"] else list(range(1, 5))
    )
    relevant_recommendations = [
        item
        for item in analytics["recommendations"]
        if item["server"] is None or item["server"] in selected_servers
    ]

    include_workbench = "workbench" in options["metrics"]
    compare = build_compare_payload() if include_workbench else None
    sql_sample = rows[-100:] if rows else read_history(options["server_scope"] or 1, 50)
    # Normalize timestamps for JSON
    sql_table = []
    for row in sql_sample[-50:]:
        sql_table.append(
            {
                "timestamp": format_timestamp(row.get("timestamp")),
                "server": row.get("server", options["server_scope"] or None),
                "cpu": row.get("cpu"),
                "ram": row.get("ram"),
                "disk": row.get("disk"),
                "temperature": row.get("temperature"),
                "network": row.get("network"),
                "latency": row.get("latency"),
                "status": row.get("status"),
            }
        )

    briefing = build_report_briefing(analytics, options, aggregates, len(rows))

    return {
        "generated_at": datetime.now().isoformat(),
        "options": options,
        "row_count": len(rows),
        "aggregates": aggregates,
        "recommendations": relevant_recommendations[:12],
        "system": analytics["system"],
        "logo_available": find_logo() is not None,
        "workbench_compare": compare,
        "sql_rows": sql_table,
        "history_table": build_db_status().get("history_table"),
        "briefing": briefing,
    }


def report_options(query: dict[str, list[str]]) -> dict[str, Any]:
    report_type = query.get("report_type", ["executive"])[0]
    if report_type not in {"executive", "technical", "capacity", "alarms"}:
        report_type = "executive"

    scope = query.get("scope", ["all"])[0]
    server_scope: int | None = None
    if scope.startswith("server"):
        try:
            value = int(scope.replace("server", ""))
            if value in range(1, 5):
                server_scope = value
        except ValueError:
            server_scope = None

    range_name = query.get("range", ["current"])[0]
    if range_name not in {"current", "1h", "24h", "7d", "30d", "custom"}:
        range_name = "current"

    allowed_metrics = {
        "cpu",
        "ram",
        "disk",
        "temperature",
        "network",
        "latency",
        "status",
        "health",
        "recommendations",
        "alarms",
        "workbench",
    }
    raw_metrics = query.get(
        "metrics",
        ["cpu,ram,disk,temperature,network,latency,status,health,recommendations"],
    )[0]
    metrics = [item for item in raw_metrics.split(",") if item in allowed_metrics]
    if not metrics:
        metrics = ["cpu", "ram", "disk", "temperature", "network", "latency", "status"]

    return {
        "report_type": report_type,
        "scope": scope,
        "server_scope": server_scope,
        "range": range_name,
        "date_from": query.get("date_from", [None])[0],
        "date_to": query.get("date_to", [None])[0],
        "metrics": metrics,
    }


# ============================================================
# REPORT EXPORTERS
# ============================================================


def format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if value:
        return str(value)
    return "-"


def build_csv(options: dict[str, Any]) -> bytes:
    rows = read_report_rows(
        server_scope=options["server_scope"],
        range_name=options["range"],
        date_from=options["date_from"],
        date_to=options["date_to"],
    )
    with LOCK:
        analytics = build_ai_analysis(state.copy())
    rec_by_server: dict[int, str] = {}
    for item in analytics["recommendations"]:
        if item["server"] and item["server"] not in rec_by_server:
            rec_by_server[item["server"]] = item["recommended_action"]

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "RecordedAt",
            "ServerNumber",
            "CPU_Percent",
            "RAM_Percent",
            "Disk_Percent",
            "Temperature_C",
            "Network_Mbps",
            "Latency_ms",
            "Status",
            "HealthScore",
            "PrimaryRecommendation",
        ]
    )
    for row in rows:
        snapshot = {
            "status": row["status"],
            "cpu": row["cpu"],
            "ram": row["ram"],
            "disk": row["disk"],
            "temperature": row["temperature"],
            "network": row["network"],
            "latency": row["latency"],
        }
        writer.writerow(
            [
                format_timestamp(row["timestamp"]),
                row["server"],
                f"{row['cpu']:.2f}",
                f"{row['ram']:.2f}",
                f"{row['disk']:.2f}",
                f"{row['temperature']:.2f}",
                f"{row['network']:.2f}",
                f"{row['latency']:.2f}",
                "UP" if row["status"] else "DOWN",
                row.get("health_score", calculate_health_score(snapshot)),
                rec_by_server.get(int(row["server"]), "No immediate action"),
            ]
        )

    if "workbench" in options.get("metrics", []):
        compare = build_compare_payload()
        writer.writerow([])
        writer.writerow(["WORKBENCH_COMPARE"])
        writer.writerow(
            [
                "Server",
                "Metric",
                "TagName",
                "SqlValue",
                "WorkbenchTagValue",
                "DeltaSqlMinusTag",
                "CpuWorkbench",
                "PredictedCpu",
                "AiRisk",
            ]
        )
        for server in compare.get("servers", []):
            pred = server.get("ai") or {}
            for metric in server.get("metrics", []):
                writer.writerow(
                    [
                        server["server"],
                        metric["metric"],
                        metric["tag_name"],
                        metric["sql_value"],
                        metric["workbench_tag_value"],
                        metric["delta_sql_minus_tag"],
                        metric["cpu_workbench_value"],
                        pred.get("predicted_cpu"),
                        pred.get("risk"),
                    ]
                )

    return output.getvalue().encode("utf-8-sig")


def build_pdf(options: dict[str, Any]) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF export requires reportlab. Run: pip install reportlab")

    rows = read_report_rows(
        server_scope=options["server_scope"],
        range_name=options["range"],
        date_from=options["date_from"],
        date_to=options["date_to"],
    )
    aggregates = aggregate_report_rows(rows)
    with LOCK:
        analytics = build_ai_analysis(state.copy())

    selected_servers = (
        [options["server_scope"]] if options["server_scope"] else list(range(1, 5))
    )
    relevant_recommendations = [
        item
        for item in analytics["recommendations"]
        if item["server"] is None or item["server"] in selected_servers
    ]

    buffer = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=24 * mm,
        bottomMargin=16 * mm,
        title="Data Center Monitoring Report",
        author="Data Center Monitoring Dashboard",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0a3d52"),
            alignment=TA_LEFT,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#0b4f6c"),
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallText",
            parent=styles["BodyText"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Narrative",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Recommendation",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=4,
        )
    )

    logo = find_logo()
    briefing = build_report_briefing(analytics, options, aggregates, len(rows))

    def header_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        width, height = page_size
        # Dark SCADA-style header band
        canvas.setFillColor(colors.HexColor("#0b1c2c"))
        canvas.rect(0, height - 18 * mm, width, 18 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#3de0ff"))
        canvas.rect(0, height - 18.6 * mm, width, 0.6 * mm, fill=1, stroke=0)
        if logo:
            try:
                image = Image(str(logo), width=42 * mm, height=11 * mm, kind="proportional")
                image.wrapOn(canvas, 42 * mm, 11 * mm)
                image.drawOn(canvas, 14 * mm, height - 15 * mm)
            except Exception:
                canvas.setFont("Helvetica-Bold", 9)
                canvas.setFillColor(colors.white)
                canvas.drawString(14 * mm, height - 11 * mm, "Schneider Electric | AVEVA")
        else:
            canvas.setFont("Helvetica-Bold", 9)
            canvas.setFillColor(colors.HexColor("#54e6a8"))
            canvas.drawString(14 * mm, height - 11 * mm, "Schneider Electric")
            canvas.setFillColor(colors.HexColor("#c4b5fd"))
            canvas.drawString(52 * mm, height - 11 * mm, "| AVEVA")

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawRightString(width - 14 * mm, height - 11 * mm, "Data Center Control Room")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(14 * mm, 8 * mm, "Live SQL · AVEVA / Schneider Electric monitoring")
        canvas.drawRightString(width - 14 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    story: list[Any] = []
    report_name = {
        "executive": "Executive Data Center Health Report",
        "technical": "Technical KPI Report",
        "capacity": "Capacity and Risk Report",
        "alarms": "Alarm and Incident Report",
    }[options["report_type"]]

    story.append(Paragraph(report_name, styles["ReportTitle"]))
    story.append(
        Paragraph(
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S} · Scope: {options['scope']} · "
            f"Range: {options['range']} · Samples: {len(rows)} · Type: {options['report_type']}",
            styles["SmallText"],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(briefing["narrative"], styles["Narrative"]))

    system = analytics["system"]
    risk_label = str(system.get("risk_label") or "")
    risk_fill = colors.HexColor("#fecaca") if risk_label in {"High", "Critical"} else (
        colors.HexColor("#fde68a") if risk_label == "Moderate" else colors.HexColor("#bbf7d0")
    )
    summary_data = [
        ["System Health", "Business Risk", "Servers Online", "Critical Actions", "High-Priority Actions"],
        [
            f"{system['health_score']:.1f}/100",
            f"{system['risk_label']} ({system['risk_score']}/100)",
            f"{system['servers_online']}/{system['total_servers']}",
            system["critical_recommendations"],
            system["high_recommendations"],
        ],
    ]
    summary_table = Table(summary_data, colWidths=[43 * mm] * 5)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1c2c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7dd3fc")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#e0f2fe")),
                ("BACKGROUND", (1, 1), (1, 1), risk_fill),
                ("BACKGROUND", (2, 1), (-1, 1), colors.HexColor("#f8fafc")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 3 * mm))

    # Live per-server status
    story.append(Paragraph("Live Server Status", styles["SectionTitle"]))
    status_data = [["Server", "State", "Health", "CPU", "RAM", "Disk", "Temp", "Headroom", "Flags"]]
    for row in briefing["status_rows"]:
        status_data.append(
            [
                f"Server {row['server']}",
                row["status"],
                f"{row['health_score']:.1f}",
                f"{row['cpu']:.1f}%",
                f"{row['ram']:.1f}%",
                f"{row['disk']:.1f}%",
                f"{row['temperature']:.1f}C",
                f"{row['headroom']:.1f}%",
                row["flags"],
            ]
        )
    if len(status_data) > 1:
        status_table = Table(
            status_data,
            repeatRows=1,
            colWidths=[22 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 22 * mm, 54 * mm],
        )
        status_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4f6c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("FONTSIZE", (0, 0), (-1, -1), 7.4),
            ("ALIGN", (2, 1), (7, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, row in enumerate(briefing["status_rows"], start=1):
            if row["status"] != "Online":
                status_style.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#b91c1c")))
                status_style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
        status_table.setStyle(TableStyle(status_style))
        story.append(status_table)
    else:
        story.append(Paragraph("No live server status available.", styles["SmallText"]))

    if options["report_type"] == "capacity":
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Capacity Thresholds (warning / critical)", styles["SectionTitle"]))
        th = briefing["thresholds"]
        cap_data = [
            ["Metric", "Warning", "Critical"],
            ["CPU %", th.get("cpu_warning"), th.get("cpu_critical")],
            ["RAM %", th.get("ram_warning"), th.get("ram_critical")],
            ["Disk %", th.get("disk_warning"), th.get("disk_critical")],
            ["Temperature C", th.get("temp_warning"), th.get("temp_critical")],
            ["Latency ms", th.get("latency_warning"), th.get("latency_critical")],
        ]
        cap_table = Table(cap_data, colWidths=[50 * mm, 40 * mm, 40 * mm])
        cap_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1c2c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7dd3fc")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        story.append(cap_table)

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Server KPI Summary (history range)", styles["SectionTitle"]))
    if aggregates:
        table_data = [
            [
                "Server",
                "Samples",
                "CPU Avg / Max",
                "RAM Avg",
                "Disk Avg / Max",
                "Temp Avg / Max",
                "Network Avg",
                "Latency Avg / Max",
                "Availability",
            ]
        ]
        for item in aggregates:
            table_data.append(
                [
                    f"Server {item['server']}",
                    item["samples"],
                    f"{item['cpu_avg']:.1f}% / {item['cpu_max']:.1f}%",
                    f"{item['ram_avg']:.1f}%",
                    f"{item['disk_avg']:.1f}% / {item['disk_max']:.1f}%",
                    f"{item['temp_avg']:.1f}C / {item['temp_max']:.1f}C",
                    f"{item['network_avg']:.1f} Mbps",
                    f"{item['latency_avg']:.1f} / {item['latency_max']:.1f} ms",
                    f"{item['availability_percent']:.2f}%",
                ]
            )
        kpi_table = Table(
            table_data,
            repeatRows=1,
            colWidths=[22 * mm, 16 * mm, 31 * mm, 20 * mm, 31 * mm, 31 * mm, 27 * mm, 34 * mm, 24 * mm],
        )
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4f6c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(kpi_table)
    else:
        story.append(Paragraph("No SQL history rows matched the selected filters.", styles["SmallText"]))

    if "recommendations" in options["metrics"] or options["report_type"] in {"executive", "capacity"}:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("AI Operations Recommendations", styles["SectionTitle"]))
        for index, item in enumerate(relevant_recommendations[:12], start=1):
            server_text = f"Server {item['server']}" if item["server"] else "Data Center"
            steps = "; ".join(item["how_to_overcome"])
            text = (
                f"<b>{index}. [{item['priority'].upper()}] {server_text} - {item['problem']}</b><br/>"
                f"Evidence: {item['evidence']}<br/>"
                f"Action: {item['recommended_action']}<br/>"
                f"Implementation: {steps}<br/>"
                f"Evidence sources: {', '.join(item['source_ids'])} | Confidence: {item['confidence']}%"
            )
            story.append(KeepTogether([Paragraph(text, styles["Recommendation"]), Spacer(1, 1.5 * mm)]))

    if options["report_type"] == "alarms" or "alarms" in options["metrics"]:
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"Alarm Snapshot — Active {briefing['alarm_active']} · Cleared {briefing['alarm_cleared']} (recent window)",
                styles["SectionTitle"],
            )
        )
        events = briefing["alarm_sample"]
        if events:
            event_data = [["Time", "Server", "Event", "Severity", "State"]]
            for event in events:
                event_data.append(
                    [
                        format_timestamp(event["timestamp"]),
                        event["server"] or "-",
                        Paragraph(event["event"], styles["SmallText"]),
                        event["severity"],
                        event["status"],
                    ]
                )
            event_table = Table(
                event_data,
                repeatRows=1,
                colWidths=[40 * mm, 20 * mm, 110 * mm, 30 * mm, 25 * mm],
            )
            event_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1c2c")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#fca5a5")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ]
                )
            )
            story.append(event_table)
        else:
            story.append(Paragraph("No alarm events matched the selected scope.", styles["SmallText"]))

    if "workbench" in options["metrics"]:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Workbench / Tag Updates vs SQL vs AI", styles["SectionTitle"]))
        compare = build_compare_payload()
        if not compare.get("model_available"):
            story.append(
                Paragraph(
                    f"AI model unavailable: {compare.get('model_error') or 'train model.pkl first.'}",
                    styles["SmallText"],
                )
            )
        wb_data = [["Server", "Metric", "SQL", "Tag", "Delta", "CPU WB", "AI Pred CPU", "AI Risk"]]
        for server in compare.get("servers", []):
            if options["server_scope"] and server["server"] != options["server_scope"]:
                continue
            pred = server.get("ai") or {}
            for metric in server.get("metrics", []):
                if metric["metric"] not in {"cpu", "ram", "disk", "temperature", "status"}:
                    continue
                wb_data.append(
                    [
                        server["server"],
                        metric["metric"],
                        str(metric.get("sql_value")),
                        str(metric.get("workbench_tag_value")),
                        str(metric.get("delta_sql_minus_tag")),
                        str(metric.get("cpu_workbench_value") if metric["metric"] == "cpu" else "-"),
                        str(pred.get("predicted_cpu", "-")),
                        str(pred.get("risk", "-")),
                    ]
                )
        if len(wb_data) > 1:
            wb_table = Table(
                wb_data,
                repeatRows=1,
                colWidths=[18 * mm, 28 * mm, 28 * mm, 28 * mm, 22 * mm, 22 * mm, 28 * mm, 25 * mm],
            )
            wb_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4f6c")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                    ]
                )
            )
            story.append(wb_table)
        else:
            story.append(Paragraph("No workbench comparison rows available.", styles["SmallText"]))

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Research Basis", styles["SectionTitle"]))
    for source in AI_SOURCES:
        story.append(
            Paragraph(
                f"<b>{source['id']}</b> - {source['organization']}: {source['title']} ({source['year']}). {source['supports']}",
                styles["SmallText"],
            )
        )

    story.append(
        Paragraph(
            "Threshold note: ASHRAE guidance describes equipment/environment classes. The dashboard's Temperature_C limit is the project's existing server-sensor alarm threshold, not an ASHRAE inlet-air limit.",
            styles["SmallText"],
        )
    )

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buffer.getvalue()


# ============================================================
# HTTP HANDLER
# ============================================================


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{datetime.now():%H:%M:%S}] {format_string % args}")

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(json_safe(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_dashboard_html(self, requested_path: str) -> None:
        page = ROOT / "index.html" if requested_path in {"", "/"} else ROOT / requested_path.lstrip("/")
        if not page.is_file() or page.suffix.lower() != ".html":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = page.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request = urlparse(self.path)
        query = parse_qs(request.query)

        if request.path == "/api/state":
            with LOCK:
                payload = {
                    "timestamp": datetime.now().isoformat(),
                    "last_update": last_update_time.isoformat() if last_update_time else None,
                    "database_connected": db_connected,
                    "database_error": last_database_error,
                    "read_only": True,
                    "tags": state.copy(),
                }
            self.send_json(payload)
            return

        if request.path == "/api/refresh":
            success = read_latest_data_from_database()
            self.send_json(
                {
                    "success": success,
                    "database_connected": db_connected,
                    "last_update": last_update_time.isoformat() if last_update_time else None,
                    "error": None if success else last_database_error,
                },
                HTTPStatus.OK if success else HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        if request.path == "/api/history":
            try:
                server = int(query.get("server", ["1"])[0])
                limit = int(query.get("limit", ["120"])[0])
            except ValueError:
                self.send_json({"error": "Invalid server or limit"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json(read_history(server, limit))
            return

        if request.path == "/api/workbench-monitor":
            try:
                server = int(query.get("server", ["1"])[0])
                limit = int(query.get("limit", ["60"])[0])
            except ValueError:
                self.send_json({"error": "Invalid server or limit"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json(build_workbench_monitor_payload(server, limit))
            return

        if request.path == "/api/events":
            try:
                limit = int(query.get("limit", ["50"])[0])
            except ValueError:
                limit = 50
            # Optional: top N alarms per server with live readings
            if query.get("per_server") or query.get("grouped", ["0"])[0] in {"1", "true", "yes"}:
                try:
                    per_server = int(query.get("per_server", ["3"])[0])
                except ValueError:
                    per_server = 3
                self.send_json(build_alarm_history_payload(per_server))
            else:
                self.send_json(read_events(limit))
            return

        if request.path == "/api/alarms/history":
            try:
                per_server = int(query.get("per_server", ["3"])[0])
            except ValueError:
                per_server = 3
            self.send_json(build_alarm_history_payload(per_server))
            return

        if request.path == "/api/executive":
            self.send_json(build_executive_payload())
            return

        if request.path == "/api/analytics":
            with LOCK:
                tags = state.copy()
            self.send_json(build_ai_analysis(tags))
            return

        if request.path == "/api/ai/predictions":
            with LOCK:
                tags = state.copy()
            try:
                self.send_json(predict_servers(tags))
            except Exception as error:
                self.send_json(
                    {
                        "model_available": False,
                        "model_error": str(error),
                        "predictions": [],
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if request.path == "/api/tags":
            tags = read_latest_tag_values()
            grouped: dict[str, list[dict[str, Any]]] = {"servers": [], "other": []}
            by_server: dict[int, list[dict[str, Any]]] = {i: [] for i in range(1, 5)}
            for item in tags:
                matched = False
                for number in range(1, 5):
                    if item["tag"].startswith(f"Server{number}_"):
                        by_server[number].append(item)
                        matched = True
                        break
                if not matched:
                    grouped["other"].append(item)
            grouped["servers"] = [
                {"server": number, "tags": by_server[number]} for number in range(1, 5)
            ]
            self.send_json(
                {
                    "database_connected": db_connected,
                    "count": len(tags),
                    "tags": tags,
                    "grouped": grouped,
                }
            )
            return

        if request.path == "/api/compare":
            self.send_json(build_compare_payload())
            return

        if request.path == "/api/db-status":
            self.send_json(build_db_status())
            return

        if request.path == "/api/report/preview":
            options = report_options(query)
            self.send_json(build_report_preview(options))
            return

        if request.path == "/api/report":
            options = report_options(query)
            export_format = query.get("format", ["pdf"])[0].lower()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                if export_format == "csv":
                    body = build_csv(options)
                    self.send_download(body, "text/csv; charset=utf-8", f"DataCenter_Report_{timestamp}.csv")
                elif export_format == "pdf":
                    body = build_pdf(options)
                    self.send_download(body, "application/pdf", f"DataCenter_Report_{timestamp}.pdf")
                else:
                    self.send_json({"error": "Format must be pdf or csv"}, HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self.send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if request.path == "/api/info":
            self.send_json(
                {
                    "mode": "LIVE SQL — IT System Performance dataset (no InTouch)",
                    "data_source": DATA_SOURCE_MODE,
                    "database_connected": db_connected,
                    "database_type": "SQL Server Express 2022",
                    "live_step_seconds": LIVE_DATASET_STEP_SECONDS,
                    "last_update": last_update_time.isoformat() if last_update_time else None,
                    "timestamp": datetime.now().isoformat(),
                    "total_tags": len(state),
                    "server_count": 4,
                    "ai_engine": "Explainable rule-based AIOps decision support",
                    "report_formats": ["pdf", "csv"],
                    "logo_available": find_logo() is not None,
                    "database_error": last_database_error,
                }
            )
            return

        # Operational controls — write into SQL so all dashboard views update.
        if request.path == "/api/toggle":
            try:
                server = int(query.get("server", ["1"])[0])
            except ValueError:
                self.send_json({"success": False, "message": "Invalid server parameter"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json(toggle_server(server))
            except Exception as error:
                self.send_json({"success": False, "message": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if request.path == "/api/stress":
            try:
                server = int(query.get("server", ["1"])[0])
            except ValueError:
                self.send_json({"success": False, "message": "Invalid server parameter"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = stress_server(server)
                status = HTTPStatus.OK if result.get("success") else HTTPStatus.CONFLICT
                self.send_json(result, status)
            except Exception as error:
                self.send_json({"success": False, "message": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if request.path == "/api/reset":
            try:
                server = int(query.get("server", ["1"])[0])
            except ValueError:
                self.send_json({"success": False, "message": "Invalid server parameter"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json(reset_server(server))
            except Exception as error:
                self.send_json({"success": False, "message": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if request.path == "/api/toggle_simulation":
            self.send_json(
                {
                    "success": False,
                    "message": "Simulation toggle is not used in live SQL mode.",
                },
                HTTPStatus.CONFLICT,
            )
            return

        if request.path in {"", "/"} or request.path.endswith(".html"):
            self.send_dashboard_html(request.path)
            return

        super().do_GET()


# ============================================================
# ENTRY POINT
# ============================================================


def main() -> None:
    print("=" * 72)
    print("DATA CENTER DASHBOARD — IT System Performance LIVE (SQL Express)")
    print("=" * 72)
    test_database_connection()
    if db_connected:
        # Prefer dataset playback when table exists; otherwise read whatever is present
        try:
            advance_it_dataset_live()
        except Exception as error:  # noqa: BLE001
            print(f"Initial dataset step skipped: {error}")
        read_latest_data_from_database()

    poller = threading.Thread(target=data_poller, daemon=True, name="sql-data-poller")
    poller.start()

    print(f"Dashboard: http://{HOST}:{PORT}/")
    print(f"Live source: {DATA_SOURCE_MODE} every {LIVE_DATASET_STEP_SECONDS:.0f}s")
    print("AVEVA InTouch is not required for live readings.")
    print("Press Ctrl+C to stop.")

    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
