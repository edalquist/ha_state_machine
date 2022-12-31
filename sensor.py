"""Sensor platform for State Machine integration."""
from __future__ import annotations

import logging
import json
import transitions
import dataclasses
from transitions import Machine
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, StateMachineEntityFeature

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class FsmConfig:
    """FSM Config Data Model"""

    initial: str
    states: list[str]
    transitions: list[dict[str, str]]


class StateMachine(Machine):
    """State Machine used in sensor"""

    def __init__(self, fsm_config: FsmConfig, after_state_change) -> None:
        Machine.__init__(
            self,
            states=fsm_config.states,
            transitions=fsm_config.transitions,
            initial=fsm_config.initial,
            ignore_invalid_triggers=True,
            after_state_change=after_state_change,
        )


def to_transitions_config(config_json: dict) -> FsmConfig:
    """Convert JSON fsm config to Transitions config"""
    initial = config_json["state"]["status"]
    states = set()
    trans = []

    for src, triggers in config_json["transitions"].items():
        states.add(src)
        for trigger, dst in triggers.items():
            states.add(dst)
            trans.append({"trigger": trigger, "source": src, "dest": dst})

    return FsmConfig(initial, list(states), trans)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    name = config_entry.title
    unique_id = config_entry.entry_id
    config_json = config_entry.options.get("schema_json", "{}")
    try:
        config_json = json.loads(config_json)
    except ValueError as exc:
        _LOGGER.error("Failed to parse FSM Config: %s\n%s", exc, config_json)
        config_json = {}

    fsm_config = to_transitions_config(config_json)

    sme = StateMachineSensorEntity(unique_id, name, fsm_config)
    # TODO add button for each transition?
    async_add_entities([sme])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "trigger",
        {vol.Required("trigger"): cv.string},
        async_trigger,
        [StateMachineEntityFeature.TRANSITION],
    )


async def async_trigger(entity: StateMachineSensorEntity, call: ServiceCall) -> None:
    """Handle Trigger Events"""
    entity.trigger(call.data["trigger"])


class StateMachineSensorEntity(SensorEntity):
    """state_machine Sensor."""

    # Our class is PUSH, so we tell HA that it should not be polled
    should_poll = False

    _attr_icon = "mdi:state-machine"

    # Declare supported features
    _attr_supported_features: StateMachineEntityFeature = (
        StateMachineEntityFeature.TRANSITION
    )

    def __init__(self, unique_id: str, name: str, fsm_config: FsmConfig) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        self._machine = StateMachine(
            fsm_config, after_state_change=self.schedule_update_ha_state
        )
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_value = self._machine.state

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self.name,
            "sw_version": "0.0.1",
        }

    def trigger(self, transition: str) -> None:
        """Executes trigger"""
        pre_state = self._machine.state

        try:
            self._machine.trigger(transition)
        except transitions.core.MachineError as exc:
            # TODO fire transition error event
            # event_data = {
            #     "device_id": "my-device-id",
            #     "type": "motion_detected",
            # }
            # hass.bus.async_fire("mydomain_event", event_data)
            # TODO support boolean toggle for ignoring invalid transitions
            _LOGGER.error(
                "Trigger Error %s on %s[%s]: %s", transition, self.name, self.state, exc
            )

        _LOGGER.info(
            "Trigger '%s' on '%s' [%s -> %s]",
            transition,
            self.name,
            pre_state,
            self._machine.state,
        )

    @property
    def native_value(self) -> str:
        return self._machine.state

    # @property
    # def available(self) -> bool:
    #     return True

    def update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        return self._machine.state
