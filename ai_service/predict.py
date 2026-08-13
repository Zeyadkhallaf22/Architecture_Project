"""
predict.py

AI Prediction Service

Loads trained model lazily and predicts future server condition.
Missing model artifacts do not crash the dashboard process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ai_service.database import load_current_state

ROOT = Path(__file__).resolve().parent.parent
MODEL_CANDIDATES = (
    ROOT / "model.pkl",
    ROOT / "ai_service" / "model.pkl",
    Path("model.pkl"),
)
SCALER_CANDIDATES = (
    ROOT / "scaler.pkl",
    ROOT / "ai_service" / "scaler.pkl",
    Path("scaler.pkl"),
)

FEATURES = [
    "CPU_Percent",
    "RAM_Percent",
    "Disk_Percent",
    "Temperature_C",
    "Network_Mbps",
    "Latency_ms",
    "Status",
]

_model = None
_scaler = None
_load_error: str | None = None
_loaded = False


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    for path in candidates:
        if path.is_file():
            return path
    return None


def ensure_model_loaded() -> bool:
    """Load model/scaler once. Returns True when ready."""
    global _model, _scaler, _load_error, _loaded
    if _loaded:
        return _model is not None and _scaler is not None

    _loaded = True
    model_path = _first_existing(MODEL_CANDIDATES)
    scaler_path = _first_existing(SCALER_CANDIDATES)
    if model_path is None or scaler_path is None:
        _load_error = (
            "Trained model not found. Run ai_service/train_model.py to create "
            "model.pkl and scaler.pkl in the project root."
        )
        return False

    try:
        _model = joblib.load(model_path)
        _scaler = joblib.load(scaler_path)
        _load_error = None
        return True
    except Exception as error:  # noqa: BLE001 — surface load failures to API
        _model = None
        _scaler = None
        _load_error = str(error)
        return False


def model_status() -> dict[str, Any]:
    available = ensure_model_loaded()
    return {
        "model_available": available,
        "model_error": None if available else _load_error,
    }


def calculate_risk(cpu: float, temp: float) -> str:
    if cpu >= 90 or temp >= 85:
        return "CRITICAL"
    if cpu >= 75 or temp >= 70:
        return "HIGH"
    if cpu >= 60 or temp >= 60:
        return "MEDIUM"
    return "LOW"


def calculate_health(cpu: float, temp: float) -> float:
    cpu_score = max(0.0, 100.0 - float(cpu))
    temp_score = max(0.0, 100.0 - float(temp))
    return round(cpu_score * 0.6 + temp_score * 0.4, 2)


def recommendation(risk: str) -> str:
    if risk == "CRITICAL":
        return "Immediate action required. Reduce workload or migrate services."
    if risk == "HIGH":
        return "Monitor server closely. Consider workload balancing."
    if risk == "MEDIUM":
        return "Performance is increasing. Keep monitoring resources."
    return "Server operating normally."


def predict_servers(state_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Predict future CPU / risk for each server.

    Returns a dict so callers can always check model_available without exceptions.
    Optional state_override lets the dashboard reuse its in-memory SQL tags.
    """
    status = model_status()
    if not status["model_available"]:
        return {
            **status,
            "predictions": [],
        }

    assert _model is not None and _scaler is not None

    if state_override is not None:
        rows = []
        for server in range(1, 5):
            rows.append(
                {
                    "ServerNumber": server,
                    "CPU_Percent": float(state_override.get(f"Server{server}_CPU_Percent") or 0),
                    "RAM_Percent": float(state_override.get(f"Server{server}_RAM_Percent") or 0),
                    "Disk_Percent": float(state_override.get(f"Server{server}_Disk_Percent") or 0),
                    "Temperature_C": float(state_override.get(f"Server{server}_Temp_C") or 0),
                    "Network_Mbps": float(state_override.get(f"Server{server}_Network_Mbps") or 0),
                    "Latency_ms": float(state_override.get(f"Server{server}_Latency_ms") or 0),
                    "Status": 1 if state_override.get(f"Server{server}_Status") else 0,
                }
            )
        servers = pd.DataFrame(rows)
    else:
        try:
            servers = load_current_state()
        except Exception as error:  # noqa: BLE001
            return {
                "model_available": True,
                "model_error": str(error),
                "predictions": [],
            }

    results = []
    for _, server in servers.iterrows():
        input_df = pd.DataFrame([server[FEATURES]])
        scaled = _scaler.transform(input_df)
        future_cpu = float(_model.predict(scaled)[0])
        temp = float(server["Temperature_C"])
        risk = calculate_risk(future_cpu, temp)
        results.append(
            {
                "server": int(server["ServerNumber"]),
                "current_cpu": round(float(server["CPU_Percent"]), 2),
                "predicted_cpu": round(future_cpu, 2),
                "temperature": round(temp, 2),
                "risk": risk,
                "health_score": calculate_health(future_cpu, temp),
                "recommendation": recommendation(risk),
            }
        )

    return {
        "model_available": True,
        "model_error": None,
        "predictions": results,
    }


if __name__ == "__main__":
    payload = predict_servers()
    print(payload)
    for item in payload.get("predictions", []):
        print("\n----------------")
        print(item)
