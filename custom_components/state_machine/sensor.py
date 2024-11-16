"""Sensor platform for State Machine integration."""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
import json
import logging

import transitions
from transitions import Machine, State
from transitions.extensions.states import Tags, Timeout, add_state_features
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, StateMachineEntityFeature

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class FsmConfig:
    """FSM Config Data Model."""

    initial: str
    states: list[State]
    transitions: list[dict[str, str]]


@add_state_features(Tags, Timeout)
class StateMachine(Machine):
    """State Machine used in sensor."""

    def __init__(
        self,
        fsm_config: FsmConfig,
        after_state_change: Callable,
        set_timeout_context: Callable,
    ) -> None:
        """Init the state machine."""

        Machine.__init__(
            self,
            states=fsm_config.states,
            transitions=fsm_config.transitions,
            initial=fsm_config.initial,
            ignore_invalid_triggers=True,  # TODO make this configurable, what to do on error?
            after_state_change=after_state_change,
        )

        self._stc = set_timeout_context

        # Cache set of all possible triggers
        self._all_triggers = set(self.get_triggers(*self.states.keys()))

    def has_trigger(self, trigger: str) -> bool:
        """Check if the trigger exists in the Machine."""
        return trigger in self._all_triggers

    def set_timeout_context(self) -> None:
        """Call the set_timeout_context callback."""
        if self._stc:
            self._stc()


def to_transitions_config(entry_id: str, config_json: dict) -> FsmConfig:
    """Convert JSON fsm config to Transitions config."""
    initial = config_json["state"]["status"]
    states: dict[str, State] = {}
    transition_lst: list[dict] = []

    for name, triggers in config_json["transitions"].items():
        if "timeout" in triggers:
            timeout = triggers["timeout"]
            timeout_trigger = entry_id + "__" + timeout["to"]
            states[name] = Timeout(
                name, timeout=timeout["after"], on_timeout=timeout_trigger
            )
            # Add a synthetic trigger for timeout execution
            transition_lst.append(
                {
                    "trigger": timeout_trigger,
                    "source": name,
                    "dest": timeout["to"],
                    "before": ["set_timeout_context"],
                }
            )
        else:
            states[name] = State(name)

        for trigger, dest in triggers.items():
            transition_lst.append({"trigger": trigger, "source": name, "dest": dest})

    return FsmConfig(initial, list(states.values()), transition_lst)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize State Machine config entry."""
    name = config_entry.title
    unique_id = config_entry.entry_id
    config_json = config_entry.options.get("schema_json", "{}")
    try:
        config_json = json.loads(config_json)
    except ValueError as exc:
        _LOGGER.error("Failed to parse FSM Config: %s\n%s", exc, config_json)
        config_json = {}

    fsm_config = to_transitions_config(config_entry.entry_id, config_json)

    sme = StateMachineSensorEntity(unique_id, name, fsm_config)
    # TODO add button for each transition?
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

    # Our class is PUSH, so we tell HA that it should not be polled
    _attr_should_poll = False

    _attr_icon = "mdi:state-machine"

    # Declare supported features
    _attr_supported_features: StateMachineEntityFeature = (
        StateMachineEntityFeature.TRANSITION
    )

    def __init__(self, unique_id: str, name: str, fsm_config: FsmConfig) -> None:
        """Initialize state_machine Sensor."""
        super().__init__()
        self._machine = StateMachine(
            fsm_config,
            after_state_change=self.schedule_update_ha_state,
            set_timeout_context=self._set_timeout_context,
        )
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_value = self._machine.state

    def _set_timeout_context(self) -> None:
        # TODO this gets called but async_set_context doesn't impact the "triggered by" info in LogBook
        # self.async_set_context(
        #     Context(parent_id="state_machine", id=self._attr_unique_id)
        # )
        pass

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._attr_unique_id))},
            name=self.name,
            sw_version="0.0.1",
        )

    def trigger(self, trigger: str) -> None:
        """Execute the trigger."""

        pre_state = self._machine.state

        if not self._machine.has_trigger(trigger):
            # TODO is there a better way to communicate service errors?
            raise transitions.core.MachineError(
                f"'{trigger}' is not a possible trigger on '{self.name}'"
            )

        if not self._machine.may_trigger(trigger):
            _LOGGER.debug("Cannot trigger %s from %s", trigger, self._machine.state)
            return

        try:
            self._machine.trigger(trigger)
        except transitions.core.MachineError as exc:
            # TODO fire transition error event
            # event_data = {
            #     "device_id": "my-device-id",
            #     "type": "motion_detected",
            # }
            # hass.bus.async_fire("mydomain_event", event_data)
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
        return self._machine.state

    def update(self) -> None:
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        return self._machine.state
