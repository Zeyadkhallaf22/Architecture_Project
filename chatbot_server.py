"""SCADA operator chatbot prototype.

Runs on its own localhost, separate from the dashboard:

    Dashboard:  http://127.0.0.1:8000/
    Chatbot:    http://127.0.0.1:8001/

The chatbot only reads live tags from the dashboard. It never toggles servers
or writes setpoints.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8001
DASHBOARD = "http://127.0.0.1:8000"
POLL_SECONDS = 45
GEMINI_MODEL = "gemini-3.5-flash-lite"
BACKGROUND = Path(__file__).resolve().parent / "assets" / "chatbot-background.png"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>SCADA Operator Chatbot</title>
<style>
  :root {
    --bg: #0c1218;
    --panel: #141c26;
    --line: #2a3a4c;
    --text: #e7eef6;
    --muted: #8ea0b5;
    --accent: #3ddc97;
    --user: #1d4ed8;
    --bot: #1a2736;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: radial-gradient(1200px 600px at 20% -10%, #163024, var(--bg));
    color: var(--text);
    display: flex;
    justify-content: center;
    padding: 28px 16px;
  }
  .app {
    width: min(760px, 100%);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  header h1 { margin: 0 0 6px; font-size: 1.35rem; letter-spacing: 0.02em; }
  header p { margin: 0; color: var(--muted); font-size: 0.92rem; }
  .status { font-size: 0.82rem; color: var(--accent); }
  .log {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    min-height: 420px;
    max-height: 62vh;
    overflow: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .msg { max-width: 85%; padding: 10px 12px; border-radius: 12px; line-height: 1.45; white-space: pre-wrap; }
  .msg.user { align-self: flex-end; background: var(--user); }
  .msg.bot { align-self: flex-start; background: var(--bot); border: 1px solid var(--line); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chips button, form button {
    border: 1px solid var(--line);
    background: #101820;
    color: var(--text);
    border-radius: 999px;
    padding: 8px 12px;
    cursor: pointer;
  }
  .chips button:hover, form button:hover { border-color: var(--accent); }
  form { display: flex; gap: 8px; }
  input {
    flex: 1;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: #0e1620;
    color: var(--text);
    padding: 12px 14px;
    font: inherit;
  }
  form button {
    border-radius: 12px;
    background: var(--accent);
    color: #062016;
    font-weight: 700;
    border: none;
  }
  body.maximized {
    justify-content: flex-start;
    background: #061018;
  }
  body.maximized::before {
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    background: url("/assets/chatbot-background.png") right center / cover no-repeat;
    transform-origin: right center;
    animation: chatbot-drift 16s ease-in-out infinite alternate;
    pointer-events: none;
  }
  body.maximized::after {
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    background: linear-gradient(90deg, rgba(6,12,20,0.88) 0%, rgba(6,12,20,0.28) 46%, rgba(6,12,20,0) 68%);
    pointer-events: none;
  }
  body.maximized .app { position: relative; z-index: 1; width: min(1280px, 78%); margin-left: 28px; }
  body.maximized .log { min-height: 52vh; max-height: 68vh; }
  body.maximized .log,
  body.maximized header,
  body.maximized form,
  body.maximized .chips button,
  body.maximized input {
    background: rgba(12, 18, 28, 0.72);
    backdrop-filter: blur(8px);
  }
  @keyframes chatbot-drift {
    from { transform: scale(1); }
    to { transform: scale(1.04); }
  }
</style>
</head>
<body>
  <div class="app">
    <header>
      <h1>SCADA Operator Chatbot</h1>
      <p>Prototype on port 8001. It reads the live dashboard on port 8000 every 45 seconds, the same cycle the dashboard uses to load readings from the database. Read-only: this chat cannot start or stop servers.</p>
      <div class="status" id="status">Checking dashboard…</div>
    </header>
    <div class="log" id="log"></div>
    <div class="chips" id="chips"></div>
    <form id="form">
      <input id="input" autocomplete="off" placeholder="Ask anything about the live dashboard…" />
      <button type="submit">Send</button>
    </form>
  </div>
<script>
const log = document.getElementById("log");
const input = document.getElementById("input");
const statusEl = document.getElementById("status");
const prompts = [
  "What are the severe risks?",
  "Which server has the highest CPU?",
  "What is the OEE?",
  "What is the PUE and power use?",
  "Any active alarms?",
  "Summarize that"
];

function add(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function lastAnswer() {
  const nodes = [...log.querySelectorAll(".msg.bot")];
  for (let i = nodes.length - 1; i >= 0; i--) {
    const text = nodes[i].textContent || "";
    if (!text || text.startsWith("Checking live")) continue;
    if (text.startsWith("Ask anything about")) continue;
    if (text.startsWith("Ask a dashboard question first")) continue;
    if (text.includes("nothing in that data matches")) continue;
    return text;
  }
  return "";
}

async function ask(message) {
  const previous = lastAnswer();
  add("user", message);
  add("bot", "Checking live tags…");
  const pending = log.lastChild;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, previous })
    });
    const data = await res.json();
    pending.textContent = data.reply || "No reply.";
    const engineNote = data.engine === "gemini" ? "Gemini is wording the answer. " : "Rule answers are in use. Set GEMINI_API_KEY to use the free Gemini tier. ";
    const age = Number.isFinite(data.snapshot_age_seconds) ? Math.round(data.snapshot_age_seconds) : null;
    const fresh = age === null ? "" : ` Live dashboard readings are ${age}s old, refreshed every 45 seconds.`;
    statusEl.textContent = data.dashboard_online
      ? engineNote + "Dashboard data: http://127.0.0.1:8000/." + fresh
      : "Dashboard is not reachable on port 8000. Start server2.py, then ask again.";
  } catch (err) {
    pending.textContent = "Chatbot request failed: " + err.message;
  }
}

document.getElementById("chips").innerHTML = prompts.map(p => `<button type="button">${p}</button>`).join("");
document.getElementById("chips").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn) ask(btn.textContent);
});
document.getElementById("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  ask(message);
});
window.addEventListener("message", (event) => {
  if (event.origin !== "http://127.0.0.1:8000" && event.origin !== "http://localhost:8000") return;
  const data = event.data || {};
  if (data.type !== "chat-layout") return;
  document.body.classList.toggle("maximized", !!data.maximized);
});
add("bot", "Ask anything about the live dashboard: servers, severe risks, alarms, OEE, power, or sustainability. I only read data. I do not send control commands.");
fetch("/api/health").then(r => r.json()).then(data => {
  statusEl.textContent = data.gemini_configured
    ? "Gemini free tier is configured. Dashboard data: http://127.0.0.1:8000/"
    : data.dashboard_online
      ? "Rule answers are in use. Set GEMINI_API_KEY to use the free Gemini tier. Dashboard data: http://127.0.0.1:8000/"
      : "Dashboard is not reachable on port 8000. Start server2.py, then ask again.";
}).catch(() => {
  statusEl.textContent = "Could not check the dashboard.";
});
</script>
</body>
</html>
"""


READ_PATHS = (
    "/api/state",
    "/api/analytics",
    "/api/executive",
    "/api/sustainability",
    "/api/oee",
    "/api/alarms/history",
    "/api/db-status",
    "/api/info",
    "/api/ai/predictions",
)

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "and", "or",
    "for", "in", "on", "at", "what", "which", "who", "how", "me", "my", "i",
    "you", "do", "does", "did", "any", "there", "please", "tell", "show", "give",
    "about", "with", "from", "that", "this", "it", "its", "now", "right", "current",
}

SYNONYMS = {
    "severe": {"critical", "high", "risk", "danger", "alarm"},
    "risk": {"critical", "high", "severe", "danger"},
    "risks": {"critical", "high", "severe", "danger", "risk"},
    "problem": {"critical", "alarm", "issue", "recommendation"},
    "problems": {"critical", "alarm", "issue", "recommendation"},
    "issue": {"critical", "alarm", "problem", "risk"},
    "issues": {"critical", "alarm", "problem", "risk"},
    "danger": {"critical", "risk", "severe"},
    "dangerous": {"critical", "risk", "severe"},
    "worst": {"critical", "highest", "severe"},
    "hot": {"temperature", "temp", "thermal"},
    "hottest": {"temperature", "temp", "thermal", "highest"},
    "slow": {"latency"},
    "power": {"pue", "kw", "energy", "carbon", "sustainability", "cooling"},
    "energy": {"pue", "kw", "sustainability", "carbon"},
    "green": {"sustainability", "carbon", "pue", "wue", "water"},
    "efficiency": {"oee", "effectiveness", "dcie"},
    "oee": set(),
    "alarm": {"alarm"},
    "alarms": {"alarm"},
    "offline": {"offline", "down"},
    "down": {"offline", "down"},
    "recommend": {"recommendation", "recommendations", "action"},
    "recommendation": {"recommendations", "action"},
    "recommendations": {"recommendation", "action"},
    "fix": {"action", "recommendation"},
    "should": {"recommendation", "action"},
    "memory": {"ram"},
    "storage": {"disk"},
    "cpu": {"processor", "compute"},
    "health": {"risk", "oee", "online", "fleet"},
}


def fetch_dashboard(path: str) -> dict:
    url = DASHBOARD + path
    if path == "/api/alarms/history":
        url += "?per_server=3"
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not return an object")
    return payload


_cache_lock = threading.Lock()
_reload_lock = threading.Lock()
_cached_snapshot: dict | None = None
_cached_at = 0.0
_cached_token = ""


def published_token(state: dict | None) -> str:
    """Identity of the dashboard's current 45-second reading."""
    if not state:
        return ""
    return str(state.get("last_update") or "")


def store_snapshot(snapshot: dict) -> None:
    global _cached_snapshot, _cached_at, _cached_token
    state = snapshot.get("/api/state") or {}
    with _cache_lock:
        _cached_snapshot = snapshot
        _cached_at = time.time()
        _cached_token = published_token(state)


def current_snapshot() -> tuple[dict, float]:
    """Reuse one dashboard reading until the database publishes the next 45-second row."""
    now = time.time()
    with _cache_lock:
        cached = _cached_snapshot
        token = _cached_token
        age = now - _cached_at if cached is not None else 0.0
    if cached is not None and token:
        try:
            state = fetch_dashboard("/api/state")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return cached, age
        if published_token(state) == token:
            return cached, age

    with _reload_lock:
        with _cache_lock:
            cached = _cached_snapshot
            token = _cached_token
            age = time.time() - _cached_at if cached is not None else 0.0
        if cached is not None and token:
            try:
                state = fetch_dashboard("/api/state")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                return cached, age
            if published_token(state) == token:
                return cached, age
        snapshot = load_snapshot()
        if "/api/state" not in snapshot and cached is not None:
            return cached, age
        store_snapshot(snapshot)
        state = snapshot.get("/api/state") or {}
        print(f"[chatbot] dashboard snapshot pinned to {published_token(state) or 'no timestamp'}")
        return snapshot, 0.0


def _poll_loop() -> None:
    while True:
        try:
            current_snapshot()
        except Exception as error:  # noqa: BLE001
            print(f"[chatbot] dashboard poll failed ({error.__class__.__name__}: {error})")
        time.sleep(5)


def load_snapshot() -> dict:
    snapshot: dict[str, dict] = {}
    errors: dict[str, str] = {}

    def load(path: str) -> tuple[str, dict | None, str | None]:
        try:
            return path, fetch_dashboard(path), None
        except Exception as error:  # noqa: BLE001
            return path, None, f"{error.__class__.__name__}: {error}"

    with ThreadPoolExecutor(max_workers=len(READ_PATHS)) as pool:
        for path, payload, error in pool.map(load, READ_PATHS):
            if payload is not None:
                snapshot[path] = payload
            elif error:
                errors[path] = error
    snapshot["_errors"] = errors  # type: ignore[assignment]
    return snapshot


def as_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "up"}
    return False


def mentioned_server(text: str) -> int | None:
    match = re.search(r"server\s*([1-4])", text)
    if match:
        return int(match.group(1))
    return None


def server_line(tags: dict, number: int) -> str:
    online = as_bool(tags.get(f"Server{number}_Status"))
    state = "ONLINE" if online else "OFFLINE"
    alarms = []
    if as_bool(tags.get(f"Server{number}_CPU_Alarm")):
        alarms.append("CPU alarm")
    if as_bool(tags.get(f"Server{number}_Temp_Alarm")):
        alarms.append("temperature alarm")
    if as_bool(tags.get(f"Server{number}_Down_Alarm")):
        alarms.append("down alarm")
    alarm_text = ", ".join(alarms) if alarms else "CPU, temperature, and down tag flags are clear"
    return (
        f"Server {number} is {state}. "
        f"CPU {as_float(tags.get(f'Server{number}_CPU_Percent')):.1f}%, "
        f"RAM memory {as_float(tags.get(f'Server{number}_RAM_Percent')):.1f}%, "
        f"disk storage {as_float(tags.get(f'Server{number}_Disk_Percent')):.1f}%, "
        f"temperature {as_float(tags.get(f'Server{number}_Temp_C')):.1f}°C, "
        f"network {as_float(tags.get(f'Server{number}_Network_Mbps')):.1f} Mbps, "
        f"latency {as_float(tags.get(f'Server{number}_Latency_ms')):.1f} ms. "
        f"Alarms: {alarm_text}."
    )


def _up_down(value) -> str:
    return "UP" if as_bool(value) else "DOWN"


def live_dashboard_text(snapshot: dict, age_seconds: float) -> str:
    """Same live cards and AlarmEvents the dashboard alarm page shows."""
    state = snapshot.get("/api/state") or {}
    tags = state.get("tags") or {}
    alarms = snapshot.get("/api/alarms/history") or {}
    lines = [
        "LIVE DASHBOARD",
        (
            f"Snapshot age {age_seconds:.0f} seconds. "
            f"The dashboard reloads these readings from the database every {POLL_SECONDS:.0f} seconds. "
            f"State time {state.get('timestamp') or 'unknown'}. "
            f"Database last update {state.get('last_update') or 'unknown'}."
        ),
    ]
    if tags:
        online = [i for i in range(1, 5) if as_bool(tags.get(f"Server{i}_Status"))]
        offline = [i for i in range(1, 5) if i not in online]
        lines.append(
            "Fleet: online "
            + (", ".join(f"Server {i}" for i in online) if online else "none")
            + ". Offline: "
            + (", ".join(f"Server {i}" for i in offline) if offline else "none")
            + "."
        )

    servers = alarms.get("servers") or []
    if not servers and tags:
        servers = [
            {
                "server": number,
                "live": {
                    "cpu": tags.get(f"Server{number}_CPU_Percent"),
                    "ram": tags.get(f"Server{number}_RAM_Percent"),
                    "disk": tags.get(f"Server{number}_Disk_Percent"),
                    "temperature": tags.get(f"Server{number}_Temp_C"),
                    "network": tags.get(f"Server{number}_Network_Mbps"),
                    "latency": tags.get(f"Server{number}_Latency_ms"),
                    "status": tags.get(f"Server{number}_Status"),
                },
                "alarms": [],
            }
            for number in range(1, 5)
        ]

    for block in servers:
        number = block.get("server")
        live = block.get("live") or {}
        lines.append(
            f"Server {number} live readings: "
            f"CPU {as_float(live.get('cpu')):.1f}%, "
            f"RAM {as_float(live.get('ram')):.1f}%, "
            f"disk {as_float(live.get('disk')):.1f}%, "
            f"temperature {as_float(live.get('temperature')):.1f}°C, "
            f"network {as_float(live.get('network')):.1f} Mbps, "
            f"latency {as_float(live.get('latency')):.1f} ms, "
            f"status {_up_down(live.get('status'))}."
        )
        events = block.get("alarms") or []
        if not events:
            lines.append(f"Server {number} AlarmEvents: none in the current dashboard alarm list.")
            continue
        for event in events:
            lines.append(
                f"Server {number} alarm event: {event.get('event')}. "
                f"Severity {event.get('severity')}, status {event.get('status')}, "
                f"time {event.get('timestamp')}."
            )
    if alarms:
        lines.append(
            f"Alarm summary: {alarms.get('total_events', 0)} events shown, "
            f"{alarms.get('active_count', 0)} active."
        )
    elif not tags:
        lines.append("LIVE DASHBOARD has no server readings yet.")
    return "\n".join(lines)


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_facts(snapshot: dict) -> list[dict]:
    facts: list[dict] = []

    def add(section: str, text: str) -> None:
        cleaned = " ".join(text.split())
        if cleaned:
            facts.append({"section": section, "text": cleaned})

    state = snapshot.get("/api/state") or {}
    tags = state.get("tags") or {}
    analytics = snapshot.get("/api/analytics") or {}
    executive = snapshot.get("/api/executive") or {}
    sustainability = snapshot.get("/api/sustainability") or {}
    oee = snapshot.get("/api/oee") or {}
    alarms = snapshot.get("/api/alarms/history") or {}
    db_status = snapshot.get("/api/db-status") or {}
    info = snapshot.get("/api/info") or {}
    predictions = snapshot.get("/api/ai/predictions") or {}

    if db_status:
        connected = "connected" if db_status.get("database_connected") else "disconnected"
        add(
            "database",
            f"Database is {connected} to {db_status.get('database_name') or 'DataCenterKPI'}. "
            f"Status {db_status.get('status_label') or connected}. "
            f"History table {db_status.get('history_table') or 'unknown'}. "
            f"Error: {db_status.get('database_error') or 'none'}.",
        )
    elif info:
        connected = "connected" if info.get("database_connected") else "disconnected"
        add("database", f"Database is {connected}. Source {info.get('data_source') or info.get('mode')}.")

    if tags:
        online = [i for i in range(1, 5) if as_bool(tags.get(f"Server{i}_Status"))]
        offline = [i for i in range(1, 5) if i not in online]
        add(
            "fleet",
            "Fleet status: servers online "
            + (", ".join(f"Server {i}" for i in online) if online else "none")
            + f" ({len(online)}/4). Servers offline: "
            + (", ".join(f"Server {i}" for i in offline) if offline else "none")
            + f". Average CPU {as_float(tags.get('DC_Avg_CPU')):.1f}%. "
            f"Max temperature {as_float(tags.get('DC_Max_Temp')):.1f}°C. "
            f"Total network {as_float(tags.get('DC_Total_Network')):.1f} Mbps.",
        )
        for number in range(1, 5):
            add("server", server_line(tags, number))
            add("metric", f"Server {number} CPU is {as_float(tags.get(f'Server{number}_CPU_Percent')):.1f}%.")
            add("metric", f"Server {number} RAM memory is {as_float(tags.get(f'Server{number}_RAM_Percent')):.1f}%.")
            add("metric", f"Server {number} disk storage is {as_float(tags.get(f'Server{number}_Disk_Percent')):.1f}%.")
            add("metric", f"Server {number} temperature is {as_float(tags.get(f'Server{number}_Temp_C')):.1f}°C.")
            add("metric", f"Server {number} network is {as_float(tags.get(f'Server{number}_Network_Mbps')):.1f} Mbps.")
            add("metric", f"Server {number} latency is {as_float(tags.get(f'Server{number}_Latency_ms')):.1f} ms.")
        for metric, label in (
            ("CPU_Percent", "CPU"),
            ("RAM_Percent", "RAM memory"),
            ("Disk_Percent", "disk storage"),
            ("Temp_C", "temperature"),
            ("Latency_ms", "latency"),
            ("Network_Mbps", "network"),
        ):
            best = max(range(1, 5), key=lambda i: as_float(tags.get(f"Server{i}_{metric}")))
            value = as_float(tags.get(f"Server{best}_{metric}"))
            unit = {"CPU_Percent": "%", "RAM_Percent": "%", "Disk_Percent": "%", "Temp_C": "°C", "Latency_ms": " ms", "Network_Mbps": " Mbps"}[metric]
            add("ranking", f"Highest {label} is Server {best} at {value:.1f}{unit}.")

    system = analytics.get("system") or {}
    if system:
        drivers = ", ".join(system.get("risk_drivers") or []) or "none listed"
        add(
            "risk",
            f"Severe risk summary: business risk is {system.get('risk_label')} "
            f"with score {system.get('risk_score')}. Health score {system.get('health_score')}. "
            f"Drivers: {drivers}. "
            f"{system.get('critical_recommendations', 0)} critical recommendations and "
            f"{system.get('high_recommendations', 0)} high recommendations. "
            f"{system.get('servers_online')}/{system.get('total_servers')} servers online.",
        )
    for kpi in analytics.get("server_kpis") or []:
        if not isinstance(kpi, dict):
            continue
        add(
            "analytics",
            f"AI analytics Server {kpi.get('server')}: health {kpi.get('health_score')} "
            f"({kpi.get('health_label')}), headroom {kpi.get('capacity_headroom')}%, "
            f"risk {kpi.get('risk_score')}/100, CPU {kpi.get('cpu')}%, RAM {kpi.get('ram')}%, "
            f"disk {kpi.get('disk')}%, temperature {kpi.get('temperature')}°C, "
            f"network {kpi.get('network')} Mbps, latency {kpi.get('latency')} ms, "
            f"status {'online' if kpi.get('status') else 'offline'}.",
        )
    for item in analytics.get("recommendations") or []:
        steps = item.get("how_to_overcome") or []
        step_text = " ".join(str(step) for step in steps[:3])
        priority = str(item.get("priority") or "info")
        evidence = str(item.get("evidence") or "").strip().rstrip(".")
        action = str(item.get("recommended_action") or "").strip().rstrip(".")
        problem = str(item.get("problem") or "").strip().rstrip(".")
        add(
            "recommendation",
            f"AI recommendation {priority} for Server {item.get('server')}: {problem}. "
            f"Evidence: {evidence}. Action: {action}. "
            f"How to overcome: {step_text}. Confidence {item.get('confidence')}%.",
        )
    for challenge in analytics.get("challenges") or []:
        if challenge.get("active"):
            add(
                "risk",
                f"Active operational challenge {challenge.get('name')}: {challenge.get('description')}.",
            )

    kpis = executive.get("kpis") or {}
    if kpis:
        add(
            "executive",
            "Executive KPIs: "
            + ", ".join(f"{key.replace('_', ' ')} {_fmt(value)}" for key, value in kpis.items() if not isinstance(value, (dict, list))),
        )
    for row in executive.get("risk_heatmap") or []:
        cells = [cell for cell in row.get("cells") or [] if cell.get("level") in {"crit", "warn", "critical", "warning"}]
        if not cells:
            continue
        detail = "; ".join(
            f"{cell.get('label')} {cell.get('value')}{cell.get('unit') or ''} level {cell.get('level')}"
            for cell in cells
        )
        add("risk", f"Risk heatmap for {row.get('label') or 'Server'}: {detail}.")
    for row in executive.get("capacity_headroom") or []:
        if isinstance(row, dict):
            add(
                "executive",
                f"Capacity headroom Server {row.get('server', row.get('label'))}: "
                + ", ".join(f"{key.replace('_', ' ')} {_fmt(value)}" for key, value in row.items() if isinstance(value, (int, float))),
            )

    fleet = sustainability.get("fleet") or {}
    if fleet:
        add(
            "sustainability",
            "Sustainability and power: "
            f"IT {fleet.get('it_kw')} kW, facility {fleet.get('facility_kw')} kW, "
            f"cooling {fleet.get('cooling_kw')} kW, heat {fleet.get('heat_kw')} kW, "
            f"water {fleet.get('water_lph')} L/h. "
            f"PUE {fleet.get('pue')} ({fleet.get('pue_band')}), "
            f"DCiE {fleet.get('dcie')}, WUE {fleet.get('wue')} ({fleet.get('wue_band')}), "
            f"CUE carbon {fleet.get('cue')} ({fleet.get('cue_band')}).",
        )
    for alert in sustainability.get("alerts") or []:
        add("sustainability", f"Sustainability alert {alert.get('severity')}: {alert.get('message')}.")
    for pill in sustainability.get("kpi_pills") or []:
        if isinstance(pill, dict):
            add("sustainability", f"Sustainability KPI {pill.get('label') or pill.get('name')}: {pill.get('value')}.")

    gauges = oee.get("gauges") or {}
    if isinstance(gauges, dict) and gauges:
        parts = []
        for gauge in gauges.values():
            if isinstance(gauge, dict):
                parts.append(
                    f"{gauge.get('label')} {gauge.get('value_pct')}% status {gauge.get('status_label')} "
                    f"band {gauge.get('band')}"
                )
        if parts:
            add("oee", f"OEE over {oee.get('window') or 'the current window'}: " + ". ".join(parts) + ".")
    oee_fleet = oee.get("fleet") or {}
    if oee_fleet:
        add(
            "oee",
            f"Fleet OEE {oee_fleet.get('oee_pct')}%. Availability {oee_fleet.get('availability_pct')}%. "
            f"Performance {oee_fleet.get('performance_pct')}%. Quality {oee_fleet.get('quality_pct')}%. "
            f"{oee_fleet.get('servers_online')}/{oee_fleet.get('total_servers')} servers online.",
        )
    insights = oee.get("insights") or {}
    if isinstance(insights, dict) and insights:
        add(
            "oee",
            "OEE reliability insights: "
            + ", ".join(f"{key.replace('_', ' ')} {_fmt(value)}" for key, value in insights.items() if not isinstance(value, (dict, list)))
            + ".",
        )
    elif isinstance(insights, list):
        for insight in insights:
            if isinstance(insight, str):
                add("oee", f"OEE insight: {insight}.")
            elif isinstance(insight, dict):
                add("oee", f"OEE insight: {insight.get('title') or insight.get('label')}: {insight.get('text') or insight.get('message')}.")

    if alarms:
        add(
            "alarms",
            f"Alarm history has {alarms.get('total_events', 0)} events and {alarms.get('active_count', 0)} active.",
        )
    for event in alarms.get("events") or []:
        status = str(event.get("status") or "").strip().upper()
        kind = "Active alarm" if status == "ACTIVE" else "Cleared alarm"
        add(
            "alarms",
            f"{kind} on Server {event.get('server')} at {event.get('timestamp')}: {event.get('event')}. "
            f"Severity {event.get('severity')}.",
        )

    for item in predictions.get("predictions") or predictions.get("servers") or []:
        if isinstance(item, dict):
            add(
                "prediction",
                f"AI prediction Server {item.get('server')}: risk {item.get('risk')}, "
                f"predicted CPU {item.get('predicted_cpu')}. {item.get('recommendation') or ''}",
            )

    return facts


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def expand_query(message: str) -> tuple[set[str], set[str]]:
    raw = tokens(message) - STOPWORDS
    expanded = set(raw)
    for word in list(raw):
        expanded |= SYNONYMS.get(word, set())
    return raw, expanded


def servers_in(text: str) -> set[int]:
    return {int(number) for number in re.findall(r"Server ([1-4])", text)}


SUMMARY_WORDS = {"summarize", "summarise", "summary", "tldr", "shorten", "shorter", "recap", "brief"}


def wants_summary(message: str) -> bool:
    lowered = message.lower()
    if "in short" in lowered or "too long" in lowered or "sum up" in lowered:
        return True
    raw = tokens(message) - STOPWORDS
    content = raw - SUMMARY_WORDS - {"this", "that", "it", "last", "previous", "answer", "above", "me"}
    return bool(raw & SUMMARY_WORDS) and not content


def condense_bullet(text: str) -> str:
    text = re.sub(r"^[•\-\s]+", "", text).strip()
    text = text.replace("\u00c2\u00b0", "\u00b0")
    text = text.split(" How to overcome:")[0]
    text = text.split(" Impact:")[0]
    text = text.split(" Recommended action:")[0].strip().rstrip(".")

    level_match = re.match(
        r"(severe critical|high) risk on Server (\d+), category ([^.]+)\. Problem: ([^.]+)\.(?: Evidence: (.+))?$",
        text,
        re.IGNORECASE,
    )
    if level_match:
        level = "Critical" if "critical" in level_match.group(1).lower() else "High"
        evidence = (level_match.group(5) or "").strip().rstrip(".")
        line = f"Server {level_match.group(2)} {level}: {level_match.group(4).strip()}"
        if evidence:
            line += f". {evidence}"
        return line + "."

    if text.lower().startswith("severe risk summary:"):
        label = re.search(r"business risk is (\w+)", text, re.IGNORECASE)
        score = re.search(r"score (\d+)", text)
        critical = re.search(r"(\d+) critical", text)
        high = re.search(r"(\d+) high", text)
        head = "Risk " + (label.group(1) if label else "unknown")
        if score:
            head += f" (score {score.group(1)})"
        counts = []
        if critical:
            counts.append(f"{critical.group(1)} critical")
        if high:
            counts.append(f"{high.group(1)} high")
        if counts:
            head += ": " + ", ".join(counts)
        return head + "."

    sentence = re.split(r"(?<=\.)\s", text)[0].strip()
    if len(sentence) > 180:
        sentence = sentence[:177].rstrip() + "..."
    return sentence


def summarize_previous(previous: str) -> str:
    previous = (previous or "").strip()
    if not previous:
        return "Ask a dashboard question first. Then say summarize and I will shorten that answer."
    chunks = [part.strip() for part in re.split(r"\n+", previous) if part.strip()]
    if len(chunks) == 1:
        chunks = [part.strip() for part in re.split(r"(?=•)", previous) if part.strip()]
    lines = []
    for chunk in chunks:
        short = condense_bullet(chunk)
        if short and short not in lines:
            lines.append(short)
    if not lines:
        return "Ask a dashboard question first. Then say summarize and I will shorten that answer."
    shown = lines[:8]
    extra = len(lines) - len(shown)
    body = "\n".join(f"• {line}" for line in shown)
    if extra > 0:
        body += f"\n• {extra} more item(s) left out of this summary."
    return "Summary of the last answer:\n" + body


def _bullets(lines: list[str], limit: int = 8) -> str:
    unique: list[str] = []
    for line in lines:
        if line and line not in unique:
            unique.append(line)
        if len(unique) == limit:
            break
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "\n".join(f"• {line}" for line in unique)


def _section(facts: list[dict], section: str, server: int | None = None) -> list[str]:
    lines = []
    for fact in facts:
        if fact["section"] != section:
            continue
        if server is not None and f"Server {server}" not in fact["text"]:
            continue
        lines.append(fact["text"])
    return lines


def answer_from_facts(message: str, facts: list[dict]) -> str:
    raw, expanded = expand_query(message)
    if raw & {"help", "commands"} or "what can you" in message.lower():
        return (
            "I read the live dashboard and answer only the part you ask about: "
            "one server, one metric, active alarms, severe risks, recommendations, PUE, or OEE. "
            "I cannot start or stop equipment."
        )

    server = mentioned_server(message.lower())
    metric_words = raw & {"cpu", "ram", "memory", "disk", "storage", "temp", "temperature", "latency", "network"}

    if raw & {"online", "offline", "up"} and not (metric_words or raw & {"risk", "risks", "alarm", "alarms"}):
        fleet = next((fact["text"] for fact in facts if fact["text"].startswith("Fleet status")), None)
        if fleet:
            return fleet

    if raw & {"alarm", "alarms"}:
        alarm_lines = _section(facts, "alarms", server)
        summary = next((line for line in alarm_lines if line.startswith("Alarm history")), "")
        want_history = "history" in raw or "cleared" in raw or "all" in raw
        if want_history:
            body = _bullets(alarm_lines, 8)
            return body or "The dashboard alarm list is empty."
        active = [line for line in alarm_lines if line.startswith("Active alarm")]
        if not active:
            return summary or "No active alarms on the live dashboard."
        head = summary or f"{len(active)} active alarm(s) on the live dashboard."
        return head + "\n" + _bullets(active, 8)

    recommend_ask = bool(raw & {"recommend", "recommendation", "recommendations", "advice"})
    if recommend_ask:
        lines = _section(facts, "recommendation", server)
        if lines:
            return _bullets(lines, 12)
        return "The AI Analytics tab has no recommendation for that question."

    risk_ask = bool(raw & {"severe", "risk", "risks", "critical", "danger", "dangerous", "problem", "problems", "issue", "issues"})
    if risk_ask and not recommend_ask:
        summary = [fact["text"] for fact in facts if fact["text"].startswith("Severe risk summary")]
        heatmap = [fact["text"] for fact in facts if fact["text"].startswith("Risk heatmap")]
        if server is not None:
            heatmap = [line for line in heatmap if f"Server {server}" in line] or heatmap
        lines = summary[:1] + heatmap[:4]
        if lines:
            return _bullets(lines, 5)

    if raw & {"oee", "effectiveness", "availability", "quality"} and not metric_words:
        lines = _section(facts, "oee")
        if lines:
            return _bullets(lines, 4)

    if raw & {"pue", "wue", "cue", "sustainability", "carbon", "water", "power", "energy", "cooling"}:
        lines = _section(facts, "sustainability")
        if lines:
            return _bullets(lines, 5)

    if metric_words and (raw & {"highest", "lowest", "most", "which", "max", "maximum"} or "highest" in message.lower()):
        label = {
            "cpu": "CPU",
            "ram": "RAM",
            "memory": "RAM",
            "disk": "disk",
            "storage": "disk",
            "temp": "temperature",
            "temperature": "temperature",
            "latency": "latency",
            "network": "network",
        }
        wanted = next(label[word] for word in ("cpu", "ram", "memory", "disk", "storage", "temp", "temperature", "latency", "network") if word in raw)
        ranking = [fact["text"] for fact in facts if fact["section"] == "ranking" and wanted.lower() in fact["text"].lower()]
        if ranking:
            return ranking[0]

    if metric_words:
        lines = _section(facts, "metric", server)
        narrowed = []
        for line in lines:
            lowered = line.lower()
            if "cpu" in raw and "cpu" in lowered:
                narrowed.append(line)
            elif raw & {"ram", "memory"} and "ram" in lowered:
                narrowed.append(line)
            elif raw & {"disk", "storage"} and "disk" in lowered:
                narrowed.append(line)
            elif raw & {"temp", "temperature"} and "temperature" in lowered:
                narrowed.append(line)
            elif "latency" in raw and "latency" in lowered:
                narrowed.append(line)
            elif "network" in raw and "network" in lowered:
                narrowed.append(line)
        if narrowed:
            return _bullets(narrowed, 4)

    if server is not None and not metric_words and not risk_ask:
        status = [fact["text"] for fact in facts if fact["section"] == "server" and fact["text"].startswith(f"Server {server} is")]
        if status:
            return status[0]

    if raw & {"health", "fleet", "kpi", "kpis"} and not metric_words:
        fleet = [fact["text"] for fact in facts if fact["text"].startswith("Fleet status")]
        summary = [fact["text"] for fact in facts if fact["text"].startswith("Severe risk summary")]
        lines = fleet[:1] + summary[:1]
        if lines:
            return _bullets(lines, 2)

    if raw & {"everything", "overview", "briefing", "dashboard"}:
        seen = set()
        lines = []
        for fact in facts:
            if fact["section"] in seen or fact["section"] in {"metric", "prediction"}:
                continue
            seen.add(fact["section"])
            lines.append(fact["text"])
        if lines:
            return "Live dashboard briefing:\n" + "\n".join(f"• {line}" for line in lines[:6])

    ranked: list[tuple[int, str]] = []
    for fact in facts:
        fact_tokens = tokens(fact["text"])
        overlap = expanded & fact_tokens
        if not overlap:
            continue
        score = len(overlap) + (len(raw & fact_tokens) * 2)
        if server is not None and servers_in(fact["text"]) == {server}:
            score += 8
        elif server is not None and f"server {server}" in fact["text"].lower():
            score += 3
        ranked.append((score, fact["text"]))
    ranked.sort(key=lambda item: item[0], reverse=True)

    if not ranked or ranked[0][0] < 2:
        return (
            "I read the live dashboard (servers, alarms, severe risks, executive KPIs, sustainability, and OEE) "
            "but nothing in that data matches this question. "
            "Try a server number, a metric such as CPU or PUE, alarms, or severe risks."
        )

    top = ranked[0][0]
    unique: list[str] = []
    for score, text in ranked:
        if score < top:
            break
        if text not in unique:
            unique.append(text)
        if len(unique) == 3:
            break
    if len(unique) == 1:
        return unique[0]
    return "\n".join(f"• {line}" for line in unique)


def gemini_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def gemini_reply(message: str, facts: list[dict], previous: str, live_text: str = "") -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    summarizing = wants_summary(message)
    if summarizing and not previous.strip():
        return None
    if summarizing:
        system = (
            "You shorten a previous SCADA assistant answer. "
            "Keep server names and every number that was already stated. "
            "Drop repeated procedures. "
            "Do not add readings that are not in the previous answer. "
            "Do not suggest starting, stopping, or changing equipment."
        )
        user = "Previous answer:\n" + previous.strip()[:6000]
    else:
        system = (
            "You are a read-only operator assistant for a four-server data-center dashboard. "
            "The LIVE DASHBOARD section is the operator screen. "
            "It is reloaded from the database every 45 seconds. "
            "Answer only the operator's question. Do not add unrelated servers, metrics, or cleared alarms. "
            "Active alarms are the lines that say Active alarm. "
            "If the question is about one metric, reply with that metric only. "
            "Keep every number exactly as written. "
            "If the supplied dashboard text does not contain the answer, say that. "
            "When the operator asks for recommendations, answer from AI ANALYTICS RECOMMENDATIONS. "
            "Those lines are the same records as the AI Analytics tab. "
            "Do not invent readings. "
            "Refuse requests to start, stop, toggle, or change a setpoint. "
            "You cannot send control commands. "
            "Reply in a few plain sentences."
        )
        recommendations = [fact["text"] for fact in facts if fact["section"] == "recommendation"]
        analytics_notes = [fact["text"] for fact in facts if fact["section"] == "analytics"]
        notes = [
            fact["text"]
            for fact in facts
            if fact["section"] not in {"server", "alarms", "fleet", "ranking", "recommendation", "analytics"}
        ]
        note_text = "\n".join(f"- {text}" for text in notes)
        if len(note_text) > 4000:
            note_text = note_text[:4000]
        recommendation_text = "\n".join(f"- {text}" for text in recommendations)
        analytics_text = "\n".join(f"- {text}" for text in analytics_notes)
        user = (
            f"Operator question:\n{message}\n\n"
            f"{live_text}\n\n"
            "AI ANALYTICS RECOMMENDATIONS. Same records as the AI Analytics tab. "
            "Use these when the operator asks for recommendations:\n"
            f"{recommendation_text}\n\n"
            "AI Analytics server cards:\n"
            f"{analytics_text}\n\n"
            "Other dashboard notes. Do not use these in place of LIVE DASHBOARD readings or alarms:\n"
            f"{note_text}"
        )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
    }
    request = urllib.request.Request(
        GEMINI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(str(part.get("text") or "") for part in parts).strip()
        return text or None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
        print(f"[chatbot] Gemini unavailable, using rule answers ({error.__class__.__name__})")
        return None


def build_reply(message: str, previous: str = "") -> dict:
    if wants_summary(message):
        wording = gemini_reply(message, [], previous)
        if wording:
            return {"reply": wording, "dashboard_online": True, "engine": "gemini"}
        return {
            "reply": summarize_previous(previous),
            "dashboard_online": True,
            "engine": "rules",
        }

    try:
        snapshot, age = current_snapshot()
    except Exception as error:  # noqa: BLE001
        return {
            "reply": f"Could not read the dashboard ({error.__class__.__name__}: {error}).",
            "dashboard_online": False,
        }

    if "/api/state" not in snapshot:
        detail = (snapshot.get("_errors") or {}).get("/api/state", "connection refused")
        return {
            "reply": (
                "The dashboard is not reachable at http://127.0.0.1:8000/. "
                f"Start it with: python server2.py ({detail})"
            ),
            "dashboard_online": False,
        }

    facts = build_facts(snapshot)
    live_text = live_dashboard_text(snapshot, age)
    wording = gemini_reply(message, facts, previous, live_text)
    payload = {
        "dashboard_online": True,
        "sources": [path for path in READ_PATHS if path in snapshot],
        "snapshot_age_seconds": round(age, 1),
    }
    if wording:
        payload["reply"] = wording
        payload["engine"] = "gemini"
    else:
        payload["reply"] = answer_from_facts(message, facts)
        payload["engine"] = "rules"
    payload["evidence"] = [
        {"evidenceId": f"fact-{index}", "text": fact["text"]}
        for index, fact in enumerate(facts, start=1)
    ]
    payload["limitations"] = [
        "Security findings are listed only when a detection module recorded one.",
        "The answer uses the latest dashboard records only.",
    ]
    return payload


class ChatHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/assets/chatbot-background.png":
            if not BACKGROUND.is_file():
                self._send(404, b'{"error":"background missing"}', "application/json")
                return
            self._send(200, BACKGROUND.read_bytes(), "image/png")
            return
        if path == "/api/health":
            online = True
            try:
                fetch_dashboard("/api/state")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                online = False
            payload = json.dumps(
                {"ok": True, "dashboard_online": online, "gemini_configured": gemini_configured()}
            ).encode("utf-8")
            self._send(200, payload, "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in {"/api/chat", "/api/v1/queries"}:
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"invalid json"}', "application/json")
            return
        message = str(data.get("message") or "").strip()
        previous = str(data.get("previous") or "")
        if not message:
            self._send(400, b'{"error":"message is required"}', "application/json")
            return
        payload = json.dumps(build_reply(message, previous), ensure_ascii=False).encode("utf-8")
        self._send(200, payload, "application/json")

    def log_message(self, fmt: str, *args) -> None:
        print(f"[chatbot] {self.address_string()} {fmt % args}")


def main() -> None:
    threading.Thread(target=_poll_loop, name="dashboard-poll", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    print(f"SCADA chatbot: http://{HOST}:{PORT}/")
    print(f"Reads live data from {DASHBOARD}/ every {POLL_SECONDS:.0f}s (start server2.py separately).")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChatbot stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
