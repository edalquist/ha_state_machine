"""Sensor platform for State Machine integration."""

from __future__ import annotations

import logging

import transitions

try:
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StateMachineConfigEntry
from .const import DOMAIN, StateMachineEntityFeature
from .fsm import FsmConfig, StateMachine

_LOGGER = logging.getLogger(__name__)


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


class StateMachineSensorEntity(SensorEntity):
    """state_machine Sensor."""

    _attr_should_poll = False
    _attr_icon = "mdi:state-machine"
    _attr_supported_features: StateMachineEntityFeature = (
        StateMachineEntityFeature.TRANSITION
    )

    def __init__(self, unique_id: str, name: str, fsm_config: FsmConfig) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        self._machine = StateMachine(fsm_config)
        self._machine.after_state_change.append(self.schedule_update_ha_state)
        self._attr_name = name
        self._attr_unique_id = unique_id

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
            self._machine.trigger(trigger)
        except transitions.core.MachineError as exc:
            _LOGGER.error(
                "Trigger Error %s on %s[%s]: %s", trigger, self.name, self.state, exc
            )

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
