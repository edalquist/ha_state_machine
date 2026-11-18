"""Tests for the State Machine sensor entity, actions, timeouts, and restore."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_OPTIONS, SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.state_machine.const import (
    ATTR_AVAILABLE_TRIGGERS,
    ATTR_PREVIOUS_STATE,
    ATTR_STATE,
    ATTR_TIMEOUT_AT,
    ATTR_TRIGGER,
    CONF_SCHEMA,
    DOMAIN,
    EVENT_TIMEOUT,
    SERVICE_SET_STATE,
    SERVICE_TRIGGER,
)

from .conftest import DRYER_SCHEMA, INITIAL_TIMEOUT_SCHEMA, TERMINAL_SCHEMA


async def _setup_fsm(
    hass: HomeAssistant,
    schema: dict[str, Any],
    *,
    title: str = "Dryer",
    entry_id: str = "entry-1",
) -> MockConfigEntry:
    """Create and set up a v2 State Machine config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        entry_id=entry_id,
        title=title,
        data={},
        options={CONF_SCHEMA: schema},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensor_metadata_and_device_info(hass: HomeAssistant) -> None:
    """Test ENUM device class, options, attributes, and Service DeviceInfo."""
    entry = await _setup_fsm(hass, DRYER_SCHEMA)

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "IDLE"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert state.attributes[ATTR_OPTIONS] == [
        "IDLE",
        "STARTING",
        "RUNNING",
        "STOPPING",
        "DONE",
    ]
    assert state.attributes[ATTR_AVAILABLE_TRIGGERS] == ["above"]
    assert state.attributes[ATTR_PREVIOUS_STATE] is None
    assert state.attributes[ATTR_TIMEOUT_AT] is None

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    assert device.entry_type is DeviceEntryType.SERVICE
    assert device.name == "Dryer"


async def test_trigger_transitions_and_validation_errors(hass: HomeAssistant) -> None:
    """Test trigger service transitions, ignored triggers, and validation errors."""
    await _setup_fsm(hass, DRYER_SCHEMA)

    # Trigger valid from another state, invalid from IDLE -> ignored cleanly
    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRIGGER,
        {ATTR_ENTITY_ID: "sensor.dryer", ATTR_TRIGGER: "below"},
        blocking=True,
    )
    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "IDLE"
    assert state.attributes[ATTR_PREVIOUS_STATE] is None

    # Valid transition IDLE -> STARTING
    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRIGGER,
        {ATTR_ENTITY_ID: "sensor.dryer", ATTR_TRIGGER: "above"},
        blocking=True,
    )
    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "STARTING"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "IDLE"
    assert state.attributes[ATTR_AVAILABLE_TRIGGERS] == ["below"]
    assert state.attributes[ATTR_TIMEOUT_AT] is not None

    # Unknown, "timeout", and "to_<STATE>" triggers must raise ServiceValidationError
    for bad_trigger in ("nonexistent", "timeout", "to_DONE"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_TRIGGER,
                {ATTR_ENTITY_ID: "sensor.dryer", ATTR_TRIGGER: bad_trigger},
                blocking=True,
            )


async def test_terminal_sink_state_transition(hass: HomeAssistant) -> None:
    """Test transitioning into a sink state omitted from transitions keys."""
    await _setup_fsm(hass, TERMINAL_SCHEMA, title="Job", entry_id="job-1")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRIGGER,
        {ATTR_ENTITY_ID: "sensor.job", ATTR_TRIGGER: "start"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRIGGER,
        {ATTR_ENTITY_ID: "sensor.job", ATTR_TRIGGER: "finish"},
        blocking=True,
    )
    state = hass.states.get("sensor.job")
    assert state is not None
    assert state.state == "COMPLETED"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "PROCESSING"
    assert state.attributes[ATTR_AVAILABLE_TRIGGERS] == []
    assert state.attributes[ATTR_TIMEOUT_AT] is None


async def test_set_state_override_and_validation(hass: HomeAssistant) -> None:
    """Test explicit state_machine.set_state action and invalid state handling."""
    await _setup_fsm(hass, DRYER_SCHEMA)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STATE,
        {ATTR_ENTITY_ID: "sensor.dryer", ATTR_STATE: "RUNNING"},
        blocking=True,
    )
    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "RUNNING"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "IDLE"
    assert state.attributes[ATTR_AVAILABLE_TRIGGERS] == ["below", "pulse"]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_STATE,
            {ATTR_ENTITY_ID: "sensor.dryer", ATTR_STATE: "BOGUS"},
            blocking=True,
        )


async def test_event_loop_timeouts_and_unload_cleanup(hass: HomeAssistant) -> None:
    """Test initial-state timeout, timeout event/context, and unload cleanup."""
    events: list[Event] = []
    hass.bus.async_listen(EVENT_TIMEOUT, events.append)

    entry = await _setup_fsm(
        hass, INITIAL_TIMEOUT_SCHEMA, title="Alarm", entry_id="alarm-1"
    )

    state = hass.states.get("sensor.alarm")
    assert state is not None
    assert state.state == "ARMED"
    assert state.attributes[ATTR_TIMEOUT_AT] is not None

    # Advance past the 10s initial-state timeout
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    state = hass.states.get("sensor.alarm")
    assert state is not None
    assert state.state == "EXPIRED"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "ARMED"
    assert state.attributes[ATTR_TIMEOUT_AT] is None
    assert len(events) == 1
    assert events[0].data == {
        "entity_id": "sensor.alarm",
        "from_state": "ARMED",
        "to_state": "EXPIRED",
    }
    assert state.context.id == events[0].context.id

    # Re-enter ARMED and verify unloading cancels active timer cleanly
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STATE,
        {ATTR_ENTITY_ID: "sensor.alarm", ATTR_STATE: "ARMED"},
        blocking=True,
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_reflexive_transition_resets_timeout(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test self-transitions reset active timeouts and update timeout_at."""
    schema = {
        "state": {"status": "WATCHING"},
        "transitions": {
            "WATCHING": {
                "heartbeat": "WATCHING",
                "timeout": {"after": 10, "to": "STALE"},
            },
            "STALE": {},
        },
    }
    await _setup_fsm(hass, schema, title="Watchdog", entry_id="wd-1")

    initial_state = hass.states.get("sensor.watchdog")
    assert initial_state is not None
    first_deadline = initial_state.attributes[ATTR_TIMEOUT_AT]

    # Advance 6s (before 10s timeout) and send reflexive heartbeat
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRIGGER,
        {ATTR_ENTITY_ID: "sensor.watchdog", ATTR_TRIGGER: "heartbeat"},
        blocking=True,
    )
    after_hb = hass.states.get("sensor.watchdog")
    assert after_hb is not None
    assert after_hb.state == "WATCHING"
    assert after_hb.attributes[ATTR_TIMEOUT_AT] != first_deadline

    # Advance another 6s (12s since start, only 6s since heartbeat): still WATCHING
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    still_watching = hass.states.get("sensor.watchdog")
    assert still_watching is not None
    assert still_watching.state == "WATCHING"

    # Advance another 5s (11s since heartbeat): now transitions to STALE
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    stale = hass.states.get("sensor.watchdog")
    assert stale is not None
    assert stale.state == "STALE"


async def test_restore_non_timeout_state(hass: HomeAssistant) -> None:
    """Test restoring a valid state without a timeout across restart."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.dryer", "RUNNING"),
                {"previous_state": "STARTING", "timeout_at": None},
            )
        ],
    )
    await _setup_fsm(hass, DRYER_SCHEMA)

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "RUNNING"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "STARTING"
    assert state.attributes[ATTR_TIMEOUT_AT] is None


async def test_restore_active_timeout_resumes_remaining_time(
    hass: HomeAssistant,
) -> None:
    """Test restoring a state with a future timeout deadline resumes remaining time."""
    deadline = dt_util.utcnow() + timedelta(seconds=4)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.dryer", "DONE"),
                {"previous_state": "STOPPING", "timeout_at": deadline.isoformat()},
            )
        ],
    )
    await _setup_fsm(hass, DRYER_SCHEMA)

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "DONE"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "STOPPING"

    # At +2s it should still be DONE; at +5s it should transition to IDLE
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    state_mid = hass.states.get("sensor.dryer")
    assert state_mid is not None
    assert state_mid.state == "DONE"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    state_after = hass.states.get("sensor.dryer")
    assert state_after is not None
    assert state_after.state == "IDLE"
    assert state_after.attributes[ATTR_PREVIOUS_STATE] == "DONE"


async def test_restore_expired_timeout_fires_immediately(hass: HomeAssistant) -> None:
    """Test restoring a state whose timeout deadline passed while HA was offline."""
    events: list[Event] = []
    hass.bus.async_listen(EVENT_TIMEOUT, events.append)

    expired_deadline = dt_util.utcnow() - timedelta(seconds=30)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.dryer", "STOPPING"),
                {
                    "previous_state": "RUNNING",
                    "timeout_at": expired_deadline.isoformat(),
                },
            )
        ],
    )
    await _setup_fsm(hass, DRYER_SCHEMA)

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "DONE"
    assert state.attributes[ATTR_PREVIOUS_STATE] == "STOPPING"
    assert state.attributes[ATTR_TIMEOUT_AT] is not None
    assert len(events) == 1
    assert events[0].data == {
        "entity_id": "sensor.dryer",
        "from_state": "STOPPING",
        "to_state": "DONE",
    }


async def test_restore_removed_state_falls_back_to_initial(
    hass: HomeAssistant,
) -> None:
    """Test restoring a state no longer in the schema falls back to initial."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.dryer", "REMOVED_STATE"),
                {"previous_state": "IDLE", "timeout_at": None},
            )
        ],
    )
    await _setup_fsm(hass, DRYER_SCHEMA)

    state = hass.states.get("sensor.dryer")
    assert state is not None
    assert state.state == "IDLE"
