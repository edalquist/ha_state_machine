"""Tests for the State Machine config and options flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.state_machine.const import CONF_NAME, CONF_SCHEMA, DOMAIN

from .conftest import DRYER_SCHEMA, TERMINAL_SCHEMA


async def test_user_flow_create_entry(hass: HomeAssistant) -> None:
    """Test creating a v2 config entry via the user config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(
        "custom_components.state_machine.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Dryer", CONF_SCHEMA: DRYER_SCHEMA},
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Dryer"
    assert result2["data"] == {}
    assert result2["options"] == {CONF_SCHEMA: DRYER_SCHEMA}
    assert result2["version"] == 2
    assert result2["minor_version"] == 1
    assert len(mock_setup.mock_calls) == 1


async def test_user_flow_validation_errors_and_recovery(hass: HomeAssistant) -> None:
    """Test user config flow surfaces validation errors and recovers cleanly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Empty name + invalid schema
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "   ", CONF_SCHEMA: {"state": {"status": "IDLE"}}},
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {
        CONF_NAME: "invalid_name",
        CONF_SCHEMA: "no_transitions",
    }

    with patch(
        "custom_components.state_machine.async_setup_entry",
        return_value=True,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_NAME: "Washer", CONF_SCHEMA: TERMINAL_SCHEMA},
        )

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == "Washer"
    assert result3["options"] == {CONF_SCHEMA: TERMINAL_SCHEMA}


async def test_options_flow_update_and_error_recovery(hass: HomeAssistant) -> None:
    """Test options flow stays on step_id='init' on error and saves on recovery."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        title="Dryer",
        data={},
        options={CONF_SCHEMA: DRYER_SCHEMA},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    # Regression test: invalid schema must return step_id="init", NOT "user"
    result_err = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCHEMA: {
                "state": {"status": "IDLE"},
                "transitions": {"IDLE": {"timeout": {"after": -1, "to": "DONE"}}},
            }
        },
    )
    assert result_err["type"] is FlowResultType.FORM
    assert result_err["step_id"] == "init"
    assert result_err["errors"] == {CONF_SCHEMA: "invalid_timeout"}

    # Submitting valid schema after error must succeed cleanly
    result_ok = await hass.config_entries.options.async_configure(
        result_err["flow_id"],
        user_input={CONF_SCHEMA: TERMINAL_SCHEMA},
    )
    assert result_ok["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCHEMA: TERMINAL_SCHEMA}

    await hass.async_block_till_done()
    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "READY"
