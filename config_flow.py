"""Config flow for State Machine integration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, core, data_entry_flow
from homeassistant.config_entries import ConfigFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .const import DOMAIN

CONF_NAME = "name"
CONF_SCHEMA_JSON = "schema_json"

_LOGGER = logging.getLogger(__name__)


@dataclass
class FsmConfig:
    """Config Data."""

    name: str
    schema_str: str


class StateMachineConfigFlow(ConfigFlow, domain=DOMAIN):
    """State Machine config flow."""

    name: str = None
    schema_str: str = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""

        if user_input is None:
            _LOGGER.debug("No user input, showing setup form")
            return self.async_show_form(
                step_id="user",
                data_schema=_build_setup_schema(self.hass, self.name, self.schema_str),
            )

        # Capture user input
        self.name = user_input[CONF_NAME]
        self.schema_str = user_input[CONF_SCHEMA_JSON]

        errors = _validate_state_machine(self.schema_str)
        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=_build_setup_schema(self.hass, self.name, self.schema_str),
                errors=errors,
            )

        # No errors, create the entity
        return self.async_create_entry(
            title=self.name,
            data={},
            options={CONF_SCHEMA_JSON: self.schema_str},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow Handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        _LOGGER.debug("Init Options UI: %s", config_entry.as_dict())
        self.schema_str = config_entry.options[CONF_SCHEMA_JSON]
        self.name = config_entry.title

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Manage the options."""

        if user_input is None:
            _LOGGER.debug("No user input, showing setup form")
            return self.async_show_form(
                step_id="init",
                data_schema=_build_options_schema__states(self.hass, self.schema_str),
            )

        # Capture user input
        self.schema_str = user_input[CONF_SCHEMA_JSON]

        errors = _validate_state_machine(self.schema_str)
        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=_build_setup_schema(self.hass, self.name, self.schema_str),
                errors=errors,
            )

        # No errors, update the entity
        return self.async_create_entry(
            title=self.name,
            data={CONF_SCHEMA_JSON: self.schema_str},
        )


def _build_setup_schema(
    hass: core.HomeAssistant, name: str, schema_str: str
) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_NAME, default=name): cv.string}).extend(
        _build_options_schema__states(hass, schema_str).schema
    )


def _build_options_schema__states(
    hass: core.HomeAssistant, schema_str: str
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_SCHEMA_JSON, default=schema_str): TextSelector(
                TextSelectorConfig(multiline=True)
            )
        }
    )


def _validate_state_machine(schema_str: str) -> dict[str, str]:
    """Validate the state machine input."""
    errors = {}

    try:
        # Parse the schema
        schema = json.loads(schema_str)
        _LOGGER.debug("Parsed schema: %s", schema)

        # Validate schema structure
        if "state" not in schema or "status" not in schema["state"]:
            errors[CONF_SCHEMA_JSON] = "no_state_or_status"
        elif "transitions" not in schema or not schema["transitions"]:
            errors[CONF_SCHEMA_JSON] = "no_transitions"
    except ValueError as exc:
        _LOGGER.warning("Schema Parse Error: %s", exc)
        errors[CONF_SCHEMA_JSON] = "schema_parse_error"

    return errors
