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

# ports conformance + tests
python3 check_ports.py
python3 -m pytest -v
```

## Connection standard

`ports.json` declares the inputs `decide()` reads from `state` and the outputs
it writes under `output`, each typed against the vocabulary in
[`types.json`](types.json). The orchestrator's canonical `types.json`
(`Data-Flow-Advisory/orchestrator@feat/drift-gate`) was unreachable (HTTP 404)
at build time, so the JSON-primitive type names are **vendored** locally to keep
the conformance check self-contained; the names are pending reconciliation
upstream. This organ maps cleanly onto JSON primitives and **proposes no new
type**.
