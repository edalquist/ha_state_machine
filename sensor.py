"""Sensor platform for State Machine integration."""
from __future__ import annotations

import logging
import json
import transitions
from transitions import Machine
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class StateMachine(Machine):
    """State Machine used in sensor"""

    def __init__(self, fsm_config: dict):
        initial = fsm_config["state"]["status"]
        states = set()
        transitions = []
        for src, triggers in fsm_config["transitions"].items():
            states.add(src)
            for trigger, dst in triggers.items():
                states.add(dst)
                transitions.append({"trigger": trigger, "source": src, "dest": dst})

        _LOGGER.warning("Initial: %s", initial)
        _LOGGER.warning("States: %s", list(states))
        _LOGGER.warning("Transitions: %s", transitions)

        Machine.__init__(
            self,
            states=list(states),
            transitions=transitions,
            initial=initial,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    _LOGGER.warning("State Machine Config:\n%s", config_entry.as_dict())

    name = config_entry.title
    unique_id = config_entry.entry_id
    config_json = config_entry.options.get("schema_json", "{}")
    try:
        fsm_config = json.loads(config_json)
    except ValueError as exc:
        _LOGGER.error("Failed to parse FSM Config:\n%s", config_json)
        fsm_config = {}

    # TODO make the Machine a device with an entity per state
    sme = StateMachineSensorEntity(unique_id, name, fsm_config)
    async_add_entities([sme])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "fsm_transition",
        {
            # TODO could put transition options in here!
            vol.Required("transition"): cv.string
        },
        async_fsm_transition,
    )


async def async_fsm_transition(
    entity: StateMachineSensorEntity, call: ServiceCall
) -> None:
    """Handle Transition Events"""
    _LOGGER.warning("State Change: %s", call)
    entity.transition(call.data["transition"])


class StateMachineSensorEntity(SensorEntity):
    """state_machine Sensor."""

    # Our class is PUSH, so we tell HA that it should not be polled
    should_poll = False

    def __init__(self, unique_id: str, name: str, fsm_config: dict) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        _LOGGER.warning("State Machine Config:%s\n%s", type(fsm_config), fsm_config)
        self._machine = StateMachine(fsm_config)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_value = self._machine.state
        _LOGGER.warning("State Machine:\n%s", self._machine.state)

    # TODO(fill this out for the machine)
    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self.name,
            "sw_version": "0.0.1",
        }

    def transition(self, transition: str) -> None:
        """Executes transition"""
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
            _LOGGER.error("Failed to execute transition: %s", exc)

        self._attr_native_value = self._machine.state
        # Notify HA the state has changed
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        return True

    def update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        _LOGGER.warning("Update: %s", self._machine.state)
        return self._machine.state
