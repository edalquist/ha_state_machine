"""Constants for the State Machine integration."""

from enum import IntFlag
from typing import Final

DOMAIN: Final = "state_machine"

CONF_NAME: Final = "name"
CONF_SCHEMA: Final = "schema"
CONF_SCHEMA_JSON: Final = "schema_json"

SERVICE_TRIGGER: Final = "trigger"
SERVICE_SET_STATE: Final = "set_state"

ATTR_TRIGGER: Final = "trigger"
ATTR_STATE: Final = "state"
ATTR_AVAILABLE_TRIGGERS: Final = "available_triggers"
ATTR_PREVIOUS_STATE: Final = "previous_state"
ATTR_TIMEOUT_AT: Final = "timeout_at"

EVENT_TIMEOUT: Final = "state_machine_timeout"


class StateMachineEntityFeature(IntFlag):
    """Supported features of the State Machine entity."""

    TRANSITION = 1
