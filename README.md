# Finite State Machine Sensor

Creates helper sensors whose state is backed by a Finite State Machine (FSM), along with Home Assistant actions to trigger transitions, override states, and run automatic state timeouts.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=edalquist&repository=ha_state_machine&category=integration)

## Features

- **YAML or JSON Configuration UI**: Uses Home Assistant's syntax-highlighted `ObjectSelector` editor (with automatic migration from v1 `schema_json` entries).
- **Enum Sensor & State Attributes**: Exposes all configured states as `SensorDeviceClass.ENUM` options for dropdowns in the Automation UI, plus `available_triggers`, `previous_state`, and `timeout_at` attributes.
- **Event-Loop Timeouts & Logbook Events**: Supports per-state `timeout` rules scheduled directly on Home Assistant's event loop, emitting `state_machine_timeout` events with context attribution.
- **State & Deadline Persistence**: Preserves the current state, `previous_state`, and active `timeout_at` deadline across Home Assistant restarts (resuming remaining time or transitioning immediately if a timeout expired while offline).
- **Actions**:
  - `state_machine.trigger`: Executes a named trigger if valid from the current state (raises a validation error for undefined triggers; safely ignores triggers valid only from other states).
  - `state_machine.set_state`: Explicitly overrides the current state to any valid state in the schema.

## Configuration

Configured via a schema close to Node-RED's [Finite State Machine](https://flows.nodered.org/node/node-red-contrib-finite-statemachine) using either YAML or JSON in the integration config/options flow.

A special `timeout` rule is supported on any state for time-based automatic transitions (`after` in seconds, `to` destination state). Terminal states with no outgoing transitions can be specified as `{}` or implicitly referenced as a destination state.

### Example Config

Tracks the state of a dryer starting up, running, and stopping. The automation sends `above`, `below`, and `middle` triggers based on the dryer's power consumption. Automatic transitions happen from `STARTING` to `RUNNING` after 1 second, from `STOPPING` to `DONE` after 2 minutes, and from `DONE` to `IDLE` after 15 seconds.

```yaml
state:
  status: IDLE
transitions:
  IDLE:
    above: STARTING
  STARTING:
    timeout:
      after: 1
      to: RUNNING
    below: IDLE
  RUNNING:
    below: STOPPING
  STOPPING:
    timeout:
      after: 120
      to: DONE
    above: RUNNING
    middle: RUNNING
  DONE:
    timeout:
      after: 15
      to: IDLE
```

Equivalent JSON (also accepted by the editor and matching [`example.json`](example.json)):

```json
{
  "state": {
    "status": "IDLE"
  },
  "transitions": {
    "IDLE": {
      "above": "STARTING"
    },
    "STARTING": {
      "timeout": { "after": 1, "to": "RUNNING" },
      "below": "IDLE"
    },
    "RUNNING": {
      "below": "STOPPING"
    },
    "STOPPING": {
      "timeout": { "after": 120, "to": "DONE" },
      "above": "RUNNING",
      "middle": "RUNNING"
    },
    "DONE": {
      "timeout": { "after": 15, "to": "IDLE" }
    }
  }
}
```

### Example Automation

Uses the FSM above, configured as `sensor.dryer`. Triggers monitor a dryer power sensor (`sensor.dryer_power`) and react when the FSM transitions to `DONE`.

The automation uses `state_machine.trigger` to send triggers to `sensor.dryer` based on current power consumption, and sends a notification when the cycle reaches `DONE`.

```yaml
alias: "!Laundry: Dryer Notifier"
description: ""
triggers:
  - trigger: state
    entity_id:
      - sensor.dryer
    to: DONE
    id: DRYER_DONE
  - trigger: numeric_state
    entity_id: sensor.dryer_power
    above: 200
    id: FSM:above
  - trigger: numeric_state
    entity_id: sensor.dryer_power
    below: 20
    id: FSM:below
  - trigger: numeric_state
    entity_id: sensor.dryer_power
    above: 20
    below: 200
    id: FSM:middle
conditions: []
actions:
  - choose:
      - conditions:
          - condition: template
            alias: FSM Event
            value_template: "{{ trigger.id.startswith('FSM:') }}"
        sequence:
          - action: state_machine.trigger
            data:
              trigger: "{{ trigger.id[4:] }}"
            target:
              entity_id: sensor.dryer
      - conditions:
          - condition: trigger
            id: DRYER_DONE
        sequence:
          - action: notify.iq_notify_parents
            data:
              message: >-
                Dryer is Done{{ '<br>Washer Is Still Running' if
                states('sensor.washer') not in ['DONE', 'IDLE'] else '' }}
              title: Laundry
              data:
                mode: only_home_then_away
mode: queued
max: 10
```

## Related Software

### hasmtools

[Hasmtools](https://github.com/mutax/hasmtools) is a small python utility to visualize the state machine and convert the JSON configuration to/from YAML, started as a simple proof of concept. Code and examples are available on [GitHub](https://github.com/mutax/hasmtools) and the package can be found on [PyPI](https://pypi.org/project/hasmtools/).
