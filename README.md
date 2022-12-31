# Finite State Machine Sensors.

Creates sensors whos state is backed by a Finite State Machine and a corresponding service that is
used to trigger state changes.

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

The automation uses the `state_machine.trigger` service to send triggers to the `sensor.dryer_state`
state machine entity based on the dryer's current power.

When the state machine eventually cycles to `DONE` that trigger results in a notification being sent.

```yaml
alias: Drier Notifier
description: ""
trigger:
  - platform: state
    entity_id:
      - input_number.dryer_power
  - platform: state
    entity_id:
      - sensor.dryer_state
    to: DONE
    id: DRYER_DONE
condition: []
action:
  - choose:
      - conditions:
          - condition: trigger
            id: DRYER_DONE
        sequence:
          - service: notify.notify
            data:
              message: Drier Is Done
    default:
      - choose:
          - conditions:
              - condition: numeric_state
                entity_id: input_number.dryer_power
                above: 50
            sequence:
              - service: state_machine.trigger
                data:
                  trigger: above
                target:
                  entity_id: sensor.dryer_state
          - conditions:
              - condition: numeric_state
                entity_id: input_number.dryer_power
                below: 15
            sequence:
              - service: state_machine.trigger
                data:
                  trigger: below
                target:
                  entity_id: sensor.dryer_state
        default:
          - service: state_machine.trigger
            data:
              trigger: middle
            target:
              entity_id: sensor.dryer_state
mode: queued
max: 10
```