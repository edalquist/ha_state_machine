"""Shared fixtures and sample schemas for State Machine tests."""

from __future__ import annotations

from typing import Any

import pytest

DRYER_SCHEMA: dict[str, Any] = {
    "state": {"status": "IDLE"},
    "transitions": {
        "IDLE": {"above": "STARTING"},
        "STARTING": {
            "timeout": {"after": 1, "to": "RUNNING"},
            "below": "IDLE",
        },
        "RUNNING": {
            "below": "STOPPING",
            "pulse": "RUNNING",
        },
        "STOPPING": {
            "timeout": {"after": 120, "to": "DONE"},
            "above": "RUNNING",
            "middle": "RUNNING",
        },
        "DONE": {
            "timeout": {"after": 15, "to": "IDLE"},
        },
    },
}

TERMINAL_SCHEMA: dict[str, Any] = {
    "state": {"status": "READY"},
    "transitions": {
        "READY": {"start": "PROCESSING"},
        "PROCESSING": {
            "finish": "COMPLETED",
            "timeout": {"after": 30, "to": "FAILED"},
        },
    },
}

INITIAL_TIMEOUT_SCHEMA: dict[str, Any] = {
    "state": {"status": "ARMED"},
    "transitions": {
        "ARMED": {
            "timeout": {"after": 10, "to": "EXPIRED"},
            "disarm": "IDLE",
        },
        "IDLE": {"arm": "ARMED"},
        "EXPIRED": {},
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations for all tests."""
    return
