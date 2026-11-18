"""Tests for config entry migration from v1 to v2."""

from __future__ import annotations

import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.state_machine.const import CONF_SCHEMA, CONF_SCHEMA_JSON, DOMAIN

from .conftest import DRYER_SCHEMA


async def test_migrate_v1_to_v2_success(hass: HomeAssistant) -> None:
    """Test migrating a v1 JSON string config entry to v2 mapping."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title="Dryer",
        data={},
        options={CONF_SCHEMA_JSON: json.dumps(DRYER_SCHEMA)},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.minor_version == 1
    assert entry.options == {CONF_SCHEMA: DRYER_SCHEMA}

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "IDLE"


async def test_migrate_v1_corrupt_json_fails_cleanly(hass: HomeAssistant) -> None:
    """Test invalid v1 JSON fails migration cleanly without crashing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title="Broken",
        data={},
        options={CONF_SCHEMA_JSON: "{not valid json"},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is False
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_v1_missing_schema_fails_cleanly(hass: HomeAssistant) -> None:
    """Test missing v1 schema_json fails migration cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title="Missing",
        data={},
        options={},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is False
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_future_version_rejected(hass: HomeAssistant) -> None:
    """Test downgrading from a newer unknown entry version is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Future",
        data={},
        options={CONF_SCHEMA: DRYER_SCHEMA},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is False
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
