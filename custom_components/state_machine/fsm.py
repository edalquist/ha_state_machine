"""Finite State Machine domain model, validation, and runtime wrapper."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from transitions import Machine, State

DEFAULT_FSM_SCHEMA: dict[str, Any] = {
    "state": {"status": "IDLE"},
    "transitions": {
        "IDLE": {"start": "ACTIVE"},
        "ACTIVE": {
            "stop": "IDLE",
            "timeout": {"after": 60, "to": "IDLE"},
        },
    },
}


class FsmValidationError(Exception):
    """Raised when an FSM configuration schema fails validation."""

    def __init__(self, error_key: str, message: str) -> None:
        """Initialize validation error with a translation error key."""
        super().__init__(message)
        self.error_key = error_key


@dataclass(frozen=True)
class TimeoutSpec:
    """Timeout configuration for a state."""

    after: float
    dest: str


@dataclass(frozen=True)
class FsmConfig:
    """Validated Finite State Machine configuration."""

    initial: str
    states: list[str]
    transitions: list[dict[str, str]]
    timeouts: dict[str, TimeoutSpec]
    user_triggers: frozenset[str]


def parse_fsm_schema(schema: Any) -> FsmConfig:
    """Validate and parse an FSM schema mapping into an FsmConfig."""
    if not isinstance(schema, dict):
        raise FsmValidationError("invalid_schema", "Schema must be a JSON/YAML object")

    state_obj = schema.get("state")
    if not isinstance(state_obj, dict):
        raise FsmValidationError(
            "no_state_or_status", "Schema does not have a valid 'state' mapping"
        )

    initial = state_obj.get("status")
    if not isinstance(initial, str) or not initial.strip():
        raise FsmValidationError(
            "no_state_or_status", "Schema does not specify a non-empty 'state.status'"
        )

    transitions_obj = schema.get("transitions")
    if not isinstance(transitions_obj, dict) or not transitions_obj:
        raise FsmValidationError(
            "no_transitions", "Schema must define a non-empty 'transitions' mapping"
        )

    discovered_states: dict[str, None] = {}
    if initial not in transitions_obj:
        discovered_states[initial] = None

    transitions: list[dict[str, str]] = []
    timeouts: dict[str, TimeoutSpec] = {}
    user_triggers: set[str] = set()

    for source_state, triggers in transitions_obj.items():
        if (
            not isinstance(source_state, str)
            or not source_state.strip()
            or not isinstance(triggers, dict)
        ):
            raise FsmValidationError(
                "invalid_transitions",
                f"Transitions for state {source_state!r} must be a mapping",
            )

        discovered_states[source_state] = None

        for trigger_name, target in triggers.items():
            if not isinstance(trigger_name, str) or not trigger_name.strip():
                raise FsmValidationError(
                    "invalid_transitions",
                    (
                        f"Trigger name {trigger_name!r} in state {source_state!r} "
                        "must be a non-empty string"
                    ),
                )

            if trigger_name == "timeout":
                if not isinstance(target, dict):
                    raise FsmValidationError(
                        "invalid_timeout",
                        (
                            f"Timeout in state {source_state!r} must be a mapping "
                            "with 'after' and 'to'"
                        ),
                    )
                after = target.get("after")
                dest = target.get("to")
                if (
                    isinstance(after, bool)
                    or not isinstance(after, (int, float))
                    or not math.isfinite(after)
                    or after <= 0
                    or not isinstance(dest, str)
                    or not dest.strip()
                ):
                    raise FsmValidationError(
                        "invalid_timeout",
                        (
                            f"Timeout in state {source_state!r} requires positive "
                            "numeric 'after' and non-empty string 'to'"
                        ),
                    )
                timeouts[source_state] = TimeoutSpec(after=float(after), dest=dest)
                discovered_states[dest] = None
                continue

            if not isinstance(target, str) or not target.strip():
                raise FsmValidationError(
                    "invalid_transitions",
                    (
                        f"Destination for trigger {trigger_name!r} in state "
                        f"{source_state!r} must be a non-empty string"
                    ),
                )

            transitions.append(
                {
                    "trigger": trigger_name,
                    "source": source_state,
                    "dest": target,
                }
            )
            user_triggers.add(trigger_name)
            discovered_states[target] = None

    if not transitions and not timeouts:
        raise FsmValidationError(
            "no_transitions", "Schema must define at least one transition or timeout"
        )

    return FsmConfig(
        initial=initial,
        states=list(discovered_states),
        transitions=transitions,
        timeouts=timeouts,
        user_triggers=frozenset(user_triggers),
    )


class StateMachine(Machine):
    """Finite State Machine wrapper backed by pytransitions."""

    state: str

    def __init__(self, fsm_config: FsmConfig) -> None:
        """Initialize the state machine without auto-transitions or threads."""
        super().__init__(
            states=[State(name) for name in fsm_config.states],
            transitions=fsm_config.transitions,
            initial=fsm_config.initial,
            auto_transitions=False,
            ignore_invalid_triggers=True,
        )
        self._fsm_config = fsm_config

    def has_trigger(self, trigger: str) -> bool:
        """Return whether the trigger is defined in the FSM configuration."""
        return trigger in self._fsm_config.user_triggers

    def available_triggers(self) -> list[str]:
        """Return sorted triggers valid from the current state."""
        return sorted(
            t
            for t in self.get_triggers(self.state)
            if t in self._fsm_config.user_triggers
        )

    def get_timeout(self, state: str | None = None) -> TimeoutSpec | None:
        """Return the timeout specification for the given or current state."""
        return self._fsm_config.timeouts.get(self.state if state is None else state)
