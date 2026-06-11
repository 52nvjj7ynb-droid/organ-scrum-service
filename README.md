# organ-scrum-service

A pure, side-effect-free decider for the **virtual daily scrum** standup state
machine, extracted from `app/services/scrum_service.py` in discovery-engine.

```
decide(state, context) -> {"output", "rationale", "self_metric"}
```

Given the current scrum state and a freshly-spoken standup contribution, it
records the contribution, advances the running order one turn (or ends the
scrum after the last non-chair report; chair interjections never advance), and
computes the next speaker. No DB, no Claude pass, no wall-clock read.

See [`CONTRACT.md`](CONTRACT.md) for the full input/output ports and
[`ports.json`](ports.json) for the connection-standard declaration.

## Run

```bash
# shadow-run on a committed sample
ORGAN_INPUT=samples/advance_to_next_persona.json python3 organ.py

# tests
python3 -m pytest -v
```
