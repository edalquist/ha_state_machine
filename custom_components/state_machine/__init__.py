"""The State Machine integration."""

from __future__ import annotations

import json
import logging

try:
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_STATE,
    ATTR_TRIGGER,
    CONF_SCHEMA,
    CONF_SCHEMA_JSON,
    DOMAIN,
    SERVICE_SET_STATE,
    SERVICE_TRIGGER,
    StateMachineEntityFeature,
)
from .fsm import FsmConfig, FsmValidationError, parse_fsm_schema

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type StateMachineConfigEntry = ConfigEntry[FsmConfig]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the State Machine integration and register actions."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_TRIGGER,
        entity_domain=Platform.SENSOR,
        schema={vol.Required(ATTR_TRIGGER): cv.string},
        func="async_trigger_service",
        required_features=[StateMachineEntityFeature.TRANSITION],
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_STATE,
        entity_domain=Platform.SENSOR,
        schema={vol.Required(ATTR_STATE): cv.string},
        func="async_set_state_service",
        required_features=[StateMachineEntityFeature.TRANSITION],
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate a v1 config entry to v2."""
    if config_entry.version > 2:
        _LOGGER.error(
            "Cannot downgrade State Machine config entry %s from version %s",
            config_entry.entry_id,
            config_entry.version,
        )
        return False

    if config_entry.version == 1:
        _LOGGER.debug(
            "Migrating State Machine config entry %s from version 1 to 2",
            config_entry.entry_id,
        )
        new_options = dict(config_entry.options)
        raw_json = new_options.pop(CONF_SCHEMA_JSON, None)

        if isinstance(raw_json, str):
            try:
                parsed_schema = json.loads(raw_json)
            except ValueError as exc:
                _LOGGER.error(
                    "Failed to parse v1 schema JSON during migration of %s: %s",
                    config_entry.entry_id,
                    exc,
                )
                return False
        elif CONF_SCHEMA in new_options:
            parsed_schema = new_options[CONF_SCHEMA]
        else:
            _LOGGER.error(
                "Cannot migrate v1 config entry %s: missing '%s'",
                config_entry.entry_id,
                CONF_SCHEMA_JSON,
            )
            return False

        try:
            parse_fsm_schema(parsed_schema)
        except FsmValidationError as exc:
            _LOGGER.error(
                "Invalid v1 FSM schema during migration of %s: %s",
                config_entry.entry_id,
                exc,
            )
            return False

        new_options[CONF_SCHEMA] = parsed_schema
        hass.config_entries.async_update_entry(
            config_entry,
            options=new_options,
            version=2,
            minor_version=1,
        )

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: StateMachineConfigEntry
) -> bool:
    """Set up State Machine from a config entry."""
    _LOGGER.debug("Setting up State Machine entry %s", entry.entry_id)

    try:
        fsm_config = parse_fsm_schema(entry.options.get(CONF_SCHEMA))
    except FsmValidationError as exc:
        raise ConfigEntryError(f"Invalid State Machine configuration: {exc}") from exc

    entry.runtime_data = fsm_config

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    return True


async def config_entry_update_listener(
    hass: HomeAssistant, entry: StateMachineConfigEntry
) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: StateMachineConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _LOGGER.debug("Unloaded state_machine entry %s: %s", entry.entry_id, unload_ok)
    return unload_ok
