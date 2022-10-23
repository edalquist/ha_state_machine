"""Sensor platform for State Machine integration."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    registry = er.async_get(hass)
    _LOGGER.info("State Machine Config:\n%s", config_entry.as_dict())
    # Validate + resolve entity registry id to entity_id
    entity_id = er.async_validate_entity_id(
        registry, config_entry.options[CONF_ENTITY_ID]
    )
    # TODO Optionally validate config entry options before creating entity
    name = config_entry.title
    unique_id = config_entry.entry_id

    async_add_entities([state_machineSensorEntity(unique_id, name, entity_id)])


class state_machineSensorEntity(SensorEntity):
    """state_machine Sensor."""

    def __init__(self, unique_id: str, name: str, wrapped_entity_id: str) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        self._wrapped_entity_id = wrapped_entity_id
        self._attr_name = name
        self._attr_unique_id = unique_id
