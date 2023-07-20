"""The State Machine integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, StateMachineEntityFeature
from .sensor import StateMachineSensorEntity

_LOGGER = logging.getLogger(__name__)

# List of platforms to support. There should be a matching .py file for each,
# eg <cover.py> and <sensor.py>
PLATFORMS: list[Platform] = [Platform.SENSOR]
SCAN_INTERVAL = timedelta(seconds=15)


# async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
#     """Track states and offer events for covers."""
#     component = hass.data[DOMAIN] = EntityComponent[StateMachineSensorEntity](
#         _LOGGER, DOMAIN, hass, SCAN_INTERVAL
#     )

#     await component.async_setup(config)

#     component.async_register_entity_service(
#         "trigger",
#         {
#             # TODO could put transition options in here?
#             vol.Required("trigger"): cv.string
#         },
#         "async_trigger",
#         [StateMachineEntityFeature.TRANSITION],
#     )

#     return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up State Machine from a config entry."""
    # TODO Optionally validate config entry options before setting up platform

    # Register platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the options flow
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if DOMAIN in hass.data:
            hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
