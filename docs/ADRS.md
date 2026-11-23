# Accepted architecture decisions

The team accepted the eight ADRs in `FAMMZ_SCADA_AI_LAYER_MILESTONE_2FINAL.docx` on 23 November 2026. This file records the decision and how this one-PC prototype implements it.

| ADR | Decision | This prototype |
|---|---|---|
| ADR-001 | Layered architecture plus event-driven updates for readings and findings. Login, reports, and control stay request-response. | `frontend`, `access`, `intelligence`, `evidence`, `ingestion`. The dashboard calls HTTP. Readings go through the event hub. |
| ADR-002 | RabbitMQ is the message broker. | `evidence/rabbit.py` publishes to `visionhmi.events` on `127.0.0.1:5672`. A repeated event id is not published again. |
| ADR-003 | PostgreSQL with TimescaleDB is the target store. | This PC uses SQL Server Express `DataCenterKPI`. Readings are still reached through the server functions, not from the pages. |
| ADR-004 | Read-only adapters publish one common event. | `ingestion/it_dataset.py` publishes the IF-02 envelope. A bad event is rejected. A repeated id is ignored. |
| ADR-005 | Control is a separate path. Chatbot, analytics, gestures, and detection cannot call it. | `access/control_gate.py`. Each attempt is audited and gets a request id. |
| ADR-006 | Independent detection modules behind one contract. A finding exists only when a module detects one. | `intelligence/ids.py`: Module A latency, Module B throughput, Module C CPU or temperature. They only record findings. |
| ADR-007 | Docker Compose is the target deployment. | This workstation starts with `.\start.ps1`: dashboard on 8000, camera on 8002, chatbot on 8001. |
| ADR-008 | Password and face, with an MFA fallback when the camera is unavailable. | Password `mariam1234` and the face camera. If port 8002 is down, choose the fallback code `face-fallback` or an emailed 6-digit code. The face line stays Access denied until the camera grants access. |

## Use cases

1. Sign in. Open http://127.0.0.1:8000/. The camera on port 8002 must show Access granted, and the password must match, before Sign in enables. If the camera is stopped, Access denied stays on the face line and the fallback code unlocks the button.
2. Live KPIs. After sign-in the dashboard reads the replayed IT dataset from SQL Server. Each row becomes one process event and one network event.
3. Read-only question. The chatbot on port 8001 answers from dashboard facts and lists those facts as evidence. It has no control route. A detection appears only when Module A, B, or C records one.

## Quality evidence

Run:

```powershell
python -m unittest tests.test_architecture_boundaries tests.test_architecture_conformance tests.test_cross_boundary tests.test_quality_measures
```

`tests/test_quality_measures.py` timed 200 replayed intakes at 1.91 ms total, 0.01 ms per event, on this PC. `tests/test_cross_boundary.py` stores one reading, records the Module C finding, rejects a chatbot control call, and accepts the fallback code.
