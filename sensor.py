"""Sensor platform for State Machine integration."""
from __future__ import annotations

import logging
import json
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class StateMachine(Machine):
    """State Machine used in sensor"""

    def __init__(self, states):
        Machine.__init__(
            self,
            states=["solid", "liquid", "gas", "plasma"],
            transitions=[
                {"trigger": "melt", "source": "solid", "dest": "liquid"},
                {"trigger": "evaporate", "source": "liquid", "dest": "gas"},
                {"trigger": "sublimate", "source": "solid", "dest": "gas"},
                {"trigger": "ionize", "source": "gas", "dest": "plasma"},
            ],
            initial="solid",
        )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    _LOGGER.warning("State Machine Config:\n%s", config_entry.as_dict())

    # TODO Optionally validate config entry options before creating entity
    name = config_entry.title
    unique_id = config_entry.entry_id
    config_json = config_entry.options.get("config", "{}")
    try:
        fsm_config = json.loads(config_json)
    except:
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

    def __init__(self, unique_id: str, name: str, fsm_config: list) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        _LOGGER.warning("State Machine Config:%s\n%s", type(fsm_config), fsm_config)
        self._machine = StateMachine(fsm_config)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_value = self._machine.state
        _LOGGER.warning("State Machine:\n%s", self._machine.state)

    # TODO(fill this out for the machine)
    # @property
    # def device_info(self) -> DeviceInfo:
    #     """Information about this entity/device."""
    #     return {
    #         "identifiers": {(DOMAIN, self._roller.roller_id)},
    #         # If desired, the name for the device could be different to the entity
    #         "name": self.name,
    #         "sw_version": self._roller.firmware_version,
    #         "model": self._roller.model,
    #         "manufacturer": self._roller.hub.manufacturer,
    #     }

    def transition(self, transition: str) -> None:
        """Executes transition"""
        self._machine.trigger(transition)
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
