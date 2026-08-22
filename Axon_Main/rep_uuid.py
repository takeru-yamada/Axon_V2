"""Boundary between app.py report payloads and UUID request generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from uuid_gen import generate_request_id


def transmit_report_request(report: dict[str, Any]) -> dict[str, Any]:
    """Attach request metadata before a report is handed to another service."""
    if not isinstance(report, dict):
        raise TypeError("report must be a dictionary")
    return {
        "request_id": generate_request_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": report,
    }