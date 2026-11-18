"""Unit tests for custom_components.state_machine.fsm."""

from __future__ import annotations

import math
from typing import Any

import pytest

from custom_components.state_machine.fsm import (
    DEFAULT_FSM_SCHEMA,
    FsmValidationError,
    StateMachine,
    parse_fsm_schema,
)

from .conftest import DRYER_SCHEMA, TERMINAL_SCHEMA


def test_parse_valid_cyclic_schema() -> None:
    """Test parsing a cyclic FSM schema with timeouts."""
    cfg = parse_fsm_schema(DRYER_SCHEMA)

    assert cfg.initial == "IDLE"
    assert cfg.states == ["IDLE", "STARTING", "RUNNING", "STOPPING", "DONE"]
    assert "timeout" not in cfg.user_triggers
    assert cfg.user_triggers == frozenset({"above", "below", "middle", "pulse"})
    assert cfg.timeouts["STARTING"].after == 1.0
    assert cfg.timeouts["STARTING"].dest == "RUNNING"
    assert all(t["trigger"] != "timeout" for t in cfg.transitions)


def test_parse_default_schema() -> None:
    """Test that DEFAULT_FSM_SCHEMA itself parses cleanly."""
    cfg = parse_fsm_schema(DEFAULT_FSM_SCHEMA)
    assert cfg.initial == "IDLE"
    assert cfg.states == ["IDLE", "ACTIVE"]


def test_parse_terminal_implicit_and_explicit_states() -> None:
    """Test terminal sink states both omitted and explicitly empty."""
    cfg = parse_fsm_schema(TERMINAL_SCHEMA)
    assert cfg.states == ["READY", "PROCESSING", "COMPLETED", "FAILED"]

    explicit_cfg = parse_fsm_schema(
        {
            "state": {"status": "INIT"},
            "transitions": {
                "INIT": {"go": "END"},
                "END": {},
            },
        }
    )
    assert explicit_cfg.states == ["INIT", "END"]

    machine = StateMachine(explicit_cfg)
    assert machine.state == "INIT"
    assert machine.trigger("go") is True
    assert machine.state == "END"
    assert machine.available_triggers() == []


def test_parse_initial_not_in_transitions_keys() -> None:
    """Test initial state omitted from transitions keys is still registered."""
    cfg = parse_fsm_schema(
        {
            "state": {"status": "BOOT"},
            "transitions": {
                "RUNNING": {"stop": "STOPPED"},
            },
        }
    )
    assert cfg.states[0] == "BOOT"
    assert "STOPPED" in cfg.states
    machine = StateMachine(cfg)
    assert machine.state == "BOOT"


@pytest.mark.parametrize(
    ("bad_schema", "expected_key"),
    [
        (None, "invalid_schema"),
        (["not", "a", "dict"], "invalid_schema"),
        ("string", "invalid_schema"),
        ({}, "no_state_or_status"),
        ({"state": None, "transitions": {"A": {"go": "B"}}}, "no_state_or_status"),
        ({"state": {}, "transitions": {"A": {"go": "B"}}}, "no_state_or_status"),
        (
            {"state": {"status": "  "}, "transitions": {"A": {"go": "B"}}},
            "no_state_or_status",
        ),
        ({"state": {"status": "A"}}, "no_transitions"),
        ({"state": {"status": "A"}, "transitions": {}}, "no_transitions"),
        (
            {"state": {"status": "A"}, "transitions": {"A": {}}},
            "no_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"A": "B"}},
            "invalid_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"": {"go": "B"}}},
            "invalid_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"A": {"": "B"}}},
            "invalid_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"A": {"go": ""}}},
            "invalid_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"A": {"go": 123}}},
            "invalid_transitions",
        ),
        (
            {"state": {"status": "A"}, "transitions": {"A": {"timeout": "B"}}},
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": 0, "to": "B"}}},
            },
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": -5, "to": "B"}}},
            },
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": True, "to": "B"}}},
            },
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": math.nan, "to": "B"}}},
            },
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": "5", "to": "B"}}},
            },
            "invalid_timeout",
        ),
        (
            {
                "state": {"status": "A"},
                "transitions": {"A": {"timeout": {"after": 5, "to": ""}}},
            },
            "invalid_timeout",
        ),
    ],
)
def test_parse_invalid_schemas(bad_schema: Any, expected_key: str) -> None:
    """Test invalid schemas raise FsmValidationError with expected keys."""
    with pytest.raises(FsmValidationError) as exc_info:
        parse_fsm_schema(bad_schema)
    assert exc_info.value.error_key == expected_key


def test_auto_transitions_and_timeout_trigger_disabled() -> None:
    """Test implicit to_<STATE> and literal timeout triggers are blocked."""
    cfg = parse_fsm_schema(DRYER_SCHEMA)
    machine = StateMachine(cfg)

    assert machine.has_trigger("above") is True
    assert machine.has_trigger("timeout") is False
    assert machine.has_trigger("to_DONE") is False
    assert machine.may_trigger("to_DONE") is False
    assert machine.may_trigger("timeout") is False
    assert machine.available_triggers() == ["above"]

    assert "to_DONE" not in machine.events
    assert "timeout" not in machine.events
    assert machine.trigger("to_DONE") is False
    assert machine.trigger("timeout") is False
    assert machine.state == "IDLE"
