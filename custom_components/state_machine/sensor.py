"""Sensor platform for State Machine integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import transitions

try:
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    HomeAssistant,
    ServiceCall,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from . import StateMachineConfigEntry
from .const import DOMAIN, EVENT_TIMEOUT, StateMachineEntityFeature
from .fsm import FsmConfig, StateMachine

_LOGGER = logging.getLogger(__name__)


@dataclass
class StateMachineExtraStoredData(ExtraStoredData):
    """Extra state data persisted across Home Assistant restarts."""

    previous_state: str | None
    timeout_at: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of extra stored data."""
        return {
            "previous_state": self.previous_state,
            "timeout_at": self.timeout_at,
        }

    @classmethod
    def from_dict(cls, restored: Mapping[str, Any]) -> Self:
        """Deserialize restored extra state data."""
        prev = restored.get("previous_state")
        timeout_at = restored.get("timeout_at")
        return cls(
            previous_state=prev if isinstance(prev, str) else None,
            timeout_at=timeout_at if isinstance(timeout_at, str) else None,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StateMachineConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    name = config_entry.title
    unique_id = config_entry.entry_id
    fsm_config = config_entry.runtime_data

    sme = StateMachineSensorEntity(unique_id, name, fsm_config)
    async_add_entities([sme])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "trigger",
        {vol.Required("trigger"): cv.string},
        async_trigger,
        [StateMachineEntityFeature.TRANSITION],
    )


async def async_trigger(entity: StateMachineSensorEntity, call: ServiceCall) -> None:
    """Handle Trigger Events."""
    entity.trigger(call.data["trigger"])


class StateMachineSensorEntity(RestoreEntity, SensorEntity):
    """Finite State Machine sensor entity."""

    _attr_should_poll = False
    _attr_icon = "mdi:state-machine"
    _attr_supported_features: StateMachineEntityFeature = (
        StateMachineEntityFeature.TRANSITION
    )

    def __init__(self, unique_id: str, name: str, fsm_config: FsmConfig) -> None:
        """Initialize the State Machine sensor."""
        super().__init__()
        self._machine = StateMachine(fsm_config)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._previous_state: str | None = None
        self._cancel_timeout: CALLBACK_TYPE | None = None
        self._timeout_at: datetime | None = None

    @property
    def extra_restore_state_data(self) -> StateMachineExtraStoredData:
        """Return extra state data to preserve across restarts."""
        return StateMachineExtraStoredData(
            previous_state=self._previous_state,
            timeout_at=self._timeout_at.isoformat() if self._timeout_at else None,
        )

    async def async_added_to_hass(self) -> None:
        """Restore state and resume or fire any pending state timeout."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        last_extra = await self.async_get_last_extra_data()
        extra = (
            StateMachineExtraStoredData.from_dict(last_extra.as_dict())
            if last_extra is not None
            else None
        )

        if (
            last_state is not None
            and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            and last_state.state in self._machine.states
        ):
            self._machine.set_state(last_state.state)
            if extra is not None:
                self._previous_state = extra.previous_state

            if (spec := self._machine.get_timeout()) is not None:
                restored_deadline = (
                    dt_util.parse_datetime(extra.timeout_at)
                    if extra is not None and extra.timeout_at
                    else None
                )
                if restored_deadline is not None:
                    if restored_deadline.tzinfo is None:
                        restored_deadline = restored_deadline.replace(tzinfo=UTC)
                    else:
                        restored_deadline = dt_util.as_utc(restored_deadline)
                    remaining = (restored_deadline - dt_util.utcnow()).total_seconds()
                    if remaining <= 0:
                        self._async_fire_timeout_transition(spec.dest)
                    else:
                        self._async_schedule_timeout(
                            delay=remaining, deadline=restored_deadline
                        )
                else:
                    self._async_schedule_timeout()
        else:
            self._async_schedule_timeout()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any active timeout before removing entity."""
        self._async_cancel_timeout()
        await super().async_will_remove_from_hass()

    @callback
    def _async_cancel_timeout(self) -> None:
        """Cancel the pending timeout callback if one is scheduled."""
        if self._cancel_timeout is not None:
            self._cancel_timeout()
            self._cancel_timeout = None

    @callback
    def _async_schedule_timeout(
        self,
        delay: float | None = None,
        deadline: datetime | None = None,
    ) -> None:
        """Schedule a timeout transition for the current state if configured."""
        self._async_cancel_timeout()
        spec = self._machine.get_timeout()
        if spec is None:
            self._timeout_at = None
            return

        effective_delay = spec.after if delay is None else max(0.0, delay)
        self._timeout_at = deadline or (
            dt_util.utcnow() + timedelta(seconds=effective_delay)
        )
        self._cancel_timeout = async_call_later(
            self.hass, effective_delay, self._async_handle_timeout
        )

    @callback
    def _async_fire_timeout_transition(self, dest: str) -> None:
        """Apply a timeout transition with fresh Logbook context and bus event."""
        prev_state = self._machine.state
        ctx = Context()
        self.hass.bus.async_fire(
            EVENT_TIMEOUT,
            {
                "entity_id": self.entity_id,
                "from_state": prev_state,
                "to_state": dest,
            },
            context=ctx,
        )
        self.async_set_context(ctx)
        self._machine.set_state(dest)
        self._previous_state = prev_state
        self._async_schedule_timeout()

    @callback
    def _async_handle_timeout(self, _now: datetime) -> None:
        """Handle scheduled timeout expiration on the Home Assistant event loop."""
        self._cancel_timeout = None
        spec = self._machine.get_timeout()
        if spec is None:
            self._timeout_at = None
            return

        self._async_fire_timeout_transition(spec.dest)
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._attr_unique_id))},
            name=self.name,
            sw_version="1.0.2",
        )

    def trigger(self, trigger: str) -> None:
        """Execute the trigger."""
        pre_state = self._machine.state

        if not self._machine.has_trigger(trigger):
            raise transitions.core.MachineError(
                f"'{trigger}' is not a possible trigger on '{self.name}'"
            )

        if not self._machine.may_trigger(trigger):
            _LOGGER.debug("Cannot trigger %s from %s", trigger, self._machine.state)
            return

        try:
            transitioned = self._machine.trigger(trigger)
        except transitions.core.MachineError as exc:
            _LOGGER.error(
                "Trigger Error %s on %s[%s]: %s", trigger, self.name, self.state, exc
            )
            return

        if transitioned:
            self._previous_state = pre_state
            self._async_schedule_timeout()
            self.async_write_ha_state()

        _LOGGER.info(
            "Trigger '%s' on '%s' [%s -> %s]",
            trigger,
            self.name,
            pre_state,
            self._machine.state,
        )

    @property
    def native_value(self) -> str:
        """Return the current FSM state."""
        return self._machine.state
