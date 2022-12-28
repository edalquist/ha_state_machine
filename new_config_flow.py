"""Config flow for State Machine integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast, Optional

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.helpers import selector
from homeassistant import data_entry_flow, config_entries, core
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)
import homeassistant.helpers.config_validation as cv
import logging

from .const import DOMAIN

CONF_NAME = "name"
CONF_STATES = "states"
CONF_STATE_LIST = "state_list"

_LOGGER = logging.getLogger(__name__)


def normalize_input(user_input: Optional[dict[str, Any]]) -> dict[str, str]:
    """Validate states"""
    _LOGGER.warning("Validate: %s", user_input)

    errors = {}

    if CONF_STATES not in user_input:
        errors["base"] = "state_csv"
    else:
        states = [x.strip() for x in user_input[CONF_STATES].split(",")]
        if len(states) < 2:
            errors["base"] = "state_min_2"
        else:
            user_input[CONF_STATE_LIST] = states

    return errors


class StateMachineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """State Machine config flow."""

    data: dict[str, Any] = {}

    def __init__(self) -> None:
        """Initialize config flow."""
        self.options: dict[str, Any] = {}

    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        _LOGGER.warning("Show Setup UI & validate input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = normalize_input(user_input)

            self.options.update(user_input)

            if not errors:
                _LOGGER.warning("Show Triggers Form: %s", user_input)
                return self.async_show_form(
                    step_id="triggers",
                    data_schema=_build_options_schema__transitions(
                        self.hass, self.options, self.options[CONF_STATE_LIST]
                    ),
                    errors=errors,
                )

                # return self.async_create_entry(
                #     title=user_input["name"],
                #     data={},
                #     options=user_input,
                # )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_setup_schema(self.hass, self.options),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow Handler"""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        _LOGGER.warning("Init Options UI: %s", config_entry.as_dict())
        self.options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        """Manage the options."""
        _LOGGER.warning("Show Options UI & validate input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = normalize_input(user_input)

            self.options.update(user_input)

            if not errors:
                return self.async_create_entry(
                    title=user_input["name"],
                    data=self.options,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema__states(self.hass, self.options),
            errors=errors,
        )


def _build_setup_schema(
    hass: core.HomeAssistant, user_input: dict[str, Any]
) -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_NAME, default=user_input.get(CONF_NAME)): cv.string}
        # {vol.Required(CONF_NAME): cv.string}
    ).extend(_build_options_schema__states(hass, user_input).schema)


def _build_options_schema__states(
    hass: core.HomeAssistant, user_input: dict[str, Any]
) -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_STATES, default=user_input.get(CONF_STATES)): cv.string}
    )


def _build_options_schema__transitions(
    hass: core.HomeAssistant, user_input: dict[str, Any], states: list[str]
) -> vol.Schema:
    schema = {}

    for state in states:
        schema[vol.Required(state, default="Triggers for %s" % state)] = cv.string

    return vol.Schema(schema)


# List of States
#
#
#
