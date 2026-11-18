"""Config flow for State Machine integration."""

from __future__ import annotations

import logging
from typing import Any

try:
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import ObjectSelector

from .const import CONF_NAME, CONF_SCHEMA, DOMAIN
from .fsm import DEFAULT_FSM_SCHEMA, FsmValidationError, parse_fsm_schema

_LOGGER = logging.getLogger(__name__)

OPTIONS_SCHEMA = vol.Schema({vol.Required(CONF_SCHEMA): ObjectSelector()})
USER_SCHEMA = vol.Schema({vol.Required(CONF_NAME): cv.string}).extend(
    OPTIONS_SCHEMA.schema
)


class StateMachineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for State Machine."""

    VERSION = 2
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"

            schema = user_input[CONF_SCHEMA]
            try:
                parse_fsm_schema(schema)
            except FsmValidationError as err:
                _LOGGER.debug("FSM schema validation failed: %s", err)
                errors[CONF_SCHEMA] = err.error_key

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={},
                    options={CONF_SCHEMA: schema},
                )

        suggested = (
            user_input if user_input is not None else {CONF_SCHEMA: DEFAULT_FSM_SCHEMA}
        )
        data_schema = self.add_suggested_values_to_schema(USER_SCHEMA, suggested)
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Handle options for State Machine."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            schema = user_input[CONF_SCHEMA]
            try:
                parse_fsm_schema(schema)
            except FsmValidationError as err:
                _LOGGER.debug("FSM schema validation failed: %s", err)
                errors[CONF_SCHEMA] = err.error_key
            else:
                return self.async_create_entry(
                    title="",
                    data={CONF_SCHEMA: schema},
                )

        suggested = (
            user_input
            if user_input is not None
            else {
                CONF_SCHEMA: self.config_entry.options.get(
                    CONF_SCHEMA, DEFAULT_FSM_SCHEMA
                )
            }
        )
        data_schema = self.add_suggested_values_to_schema(OPTIONS_SCHEMA, suggested)
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
