"""Maps each architecture component to a package, a module, or a service.

Packages are folders. Modules are single files inside a package.
Services are separate processes, each with its own port, on this PC.
"""

from __future__ import annotations

# component, kind, location
COMPONENTS: list[tuple[str, str, str]] = [
    ("Ingestion adapters", "package", "ingestion"),
    ("IT dataset adapter", "module", "ingestion/it_dataset.py"),
    ("Application and access", "package", "access"),
    ("Sign-in", "module", "access/auth.py"),
    ("Control gate", "module", "access/control_gate.py"),
    ("Evidence", "package", "evidence"),
    ("Event hub", "module", "evidence/hub.py"),
    ("Replay label", "module", "evidence/schema.py"),
    ("Detection modules", "package", "intelligence"),
    ("Correlation and evidence backend", "service", "server2.py"),
    ("Explanation and assistant", "service", "chatbot_server.py"),
    ("Dashboard frontend", "package", "frontend"),
    ("Gesture client", "service", "SCADAPROJECT/vision_web.py"),
]

# package -> other packages it must not import
FORBIDDEN_IMPORTS: dict[str, set[str]] = {
    "evidence": {"access", "ingestion"},
    "access": {"evidence", "ingestion"},
    "ingestion": {"access", "intelligence"},
    "intelligence": {"access"},
}

READ_ONLY_SERVICES = (
    "chatbot_server.py",
    "SCADAPROJECT/vision_web.py",
)
CONTROL_PATHS = ("/api/toggle", "/api/stress", "/api/reset")
