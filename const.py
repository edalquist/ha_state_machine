"""Constants for the State Machine integration."""

from enum import IntFlag
from typing import Final

DOMAIN: Final = "state_machine"


class StateMachineEntityFeature(IntFlag):
    """Supported features of the siren entity."""

    TRANSITION = 1
