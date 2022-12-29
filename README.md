

Example of triggering state change
```
service: state_machine.fsm_transition
entity_id: 'sensor.fsm_test'
data: {
transition: 'below'
}
```