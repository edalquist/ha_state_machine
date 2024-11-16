# Finite State Machine Sensor

Creates sensors who's state is backed by a Finite State Machine and a corresponding action that is
used to trigger state changes.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=edalquist&repository=ha_state_machine&category=integration)

## Configuration

Currently configured using a JSON schema that is very close to Node Red's
[Finite State Machine](https://flows.nodered.org/node/node-red-contrib-finite-statemachine)

A special `timeout` trigger is supported for time-based automatic transitions.

### Example Config

Tracks the state of a dryer starting up, running, and stopping. The automation sends `above`,
`below`, and `middle` triggers based on the dryer's power consumption. Automatic transitions
happen from `STARTING` to `RUNNING` after 1 second, from `STOPPING` to `DONE` after 2 minutes, and
from `DONE` to `IDLE` after 15 seconds.

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

Uses the FSM above, configured as `sensor.dryer_state`. Triggers are a faux drier power meter
`input_number.dryer_power` and the FSM sensor when it transitions to the `DONE` state where
we want to take an action.

The automation uses the `state_machine.trigger` action to send triggers to the `sensor.dryer_state`
state machine entity based on the dryer's current power.

When the state machine eventually cycles to `DONE` that trigger results in a notification being sent.

```yaml
alias: "!Laundry: Dryer Notifier"
description: ""
trigger:
  - platform: state
    entity_id:
      - sensor.dryer_state
    to: DONE
    id: DRYER_DONE
  - platform: numeric_state
    entity_id: switch.dryer_plug_switch
    above: 200
    id: FSM:above
  - platform: numeric_state
    entity_id: switch.dryer_plug_switch
    id: FSM:below
    below: 20
  - platform: numeric_state
    entity_id: switch.dryer_plug_switch
    id: FSM:middle
    below: 200
    above: 20
condition: []
action:
  - choose:
      - conditions:
          - condition: template
            alias: FSM Event
            value_template: |
              {{trigger.id.startswith('FSM:')}}
        sequence:
          - service: state_machine.trigger
            data:
              trigger: "{{trigger.id[4:]}}"
            target:
              entity_id: sensor.dryer_state
      - conditions:
          - condition: trigger
            id: DRYER_DONE
        sequence:
          - service: notify.iq_notify_parents
            data:
              message: >-
                Dryer is Done{{'<br>Washer Is Still Running' if
                states('sensor.washer_state') not in ['DONE', 'IDLE'] else ''}}
              title: Laundry
              data:
                mode: only_home_then_away
mode: queued
max: 10
```
