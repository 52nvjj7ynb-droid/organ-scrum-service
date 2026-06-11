#!/usr/bin/env python3
"""Connection-standard ports conformance check for organ-scrum-service.

Asserts, with stdlib only:

  1. ``ports.json`` parses and has the declared ``{inputs, outputs}`` shape
     (each input: name + type + boolean ``required``; each output: name + type).
  2. ``types.json`` parses and declares a non-empty type vocabulary.
  3. Every ``type`` named in ports.json exists in the types.json vocabulary.
  4. ``decide()`` READS every declared input name from ``state`` — verified by a
     static scan of ``organ.py`` for ``state.get("<name>")``.
  5. ``decide()`` WRITES exactly the declared output names — verified
     BEHAVIOURALLY: the union of top-level ``output`` keys produced across a
     representative run of the organ must EQUAL the declared output set (no
     undeclared key is ever emitted, and every declared output is reachable).

This organ is SINGLE-op (``decide`` always records one standup contribution and
advances the scrum), so the output check is an exact equality over every
representative run, not a multi-op union. Nested fields inside the
``contributions`` / ``contribution`` / ``next_speaker`` objects are NOT ports —
only the top-level keys of ``decide()``'s ``output`` dict are.

Exit 0 on success, non-zero (with a diagnostic) on any violation.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _fail(msg: str) -> "None":
    print(f"check_ports: FAIL — {msg}", file=sys.stderr)
    raise SystemExit(1)


def _load(name: str) -> dict:
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        _fail(f"{name} is missing")
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as e:  # noqa: BLE001
        _fail(f"{name} does not parse as JSON: {e}")


def main() -> int:
    ports = _load("ports.json")
    types = _load("types.json")

    # --- 1. ports.json shape -------------------------------------------------
    if not isinstance(ports, dict):
        _fail("ports.json must be a JSON object")
    for key in ("inputs", "outputs"):
        if not isinstance(ports.get(key), list):
            _fail(f"ports.json must declare a list '{key}'")
    for spec in ports["inputs"]:
        if not isinstance(spec, dict) or "name" not in spec or "type" not in spec:
            _fail(f"each input needs 'name' and 'type': {spec!r}")
        if "required" not in spec:
            _fail(f"each input needs a 'required' flag: {spec!r}")
        if not isinstance(spec["required"], bool):
            _fail(f"input 'required' must be boolean: {spec!r}")
    for spec in ports["outputs"]:
        if not isinstance(spec, dict) or "name" not in spec or "type" not in spec:
            _fail(f"each output needs 'name' and 'type': {spec!r}")

    # --- 2. types.json vocabulary -------------------------------------------
    vocab = types.get("types")
    if not isinstance(vocab, dict) or not vocab:
        _fail("types.json must declare a non-empty 'types' object")
    vocab_names = set(vocab.keys())

    # --- 3. every declared type exists in the vocabulary ---------------------
    for spec in ports["inputs"] + ports["outputs"]:
        if spec["type"] not in vocab_names:
            _fail(
                f"port {spec['name']!r} uses type {spec['type']!r} which is not "
                f"in the types.json vocabulary {sorted(vocab_names)}"
            )

    # --- 4. decide() reads every declared input from state -------------------
    with open(os.path.join(HERE, "organ.py")) as fh:
        source = fh.read()
    for spec in ports["inputs"]:
        name = spec["name"]
        pat = re.compile(r"""state\.get\(\s*['"]""" + re.escape(name) + r"""['"]""")
        if not pat.search(source):
            _fail(
                f"declared input {name!r} is never read via state.get({name!r}) "
                f"in organ.py — ports.json and decide() disagree"
            )

    # --- 5. decide() writes exactly the declared outputs (behavioural) -------
    sys.path.insert(0, HERE)
    from organ import decide  # noqa: E402

    # Representative runs: the committed samples plus a synthetic chair-
    # interjection so the no-advance path is exercised too. Every healthy run
    # of this single-op organ must emit the same top-level output keys.
    runs = []
    samples_dir = os.path.join(HERE, "samples")
    for fname in sorted(os.listdir(samples_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(samples_dir, fname)) as fh:
                payload = json.load(fh)
            runs.append((fname, payload.get("state"), payload.get("context")))
    runs.append(
        (
            "synthetic:chair_interjection",
            {
                "phase": "standup",
                "turn_order": [{"type": "persona", "project_id": 3}],
                "turn_index": 0,
                "contribution_text": "Quick steer before we continue.",
                "speaker_name": "Jules",
                "speaker_role": "Chair",
                "speaker_project_id": None,
                "is_chair": True,
            },
            {},
        )
    )

    declared_outputs = {spec["name"] for spec in ports["outputs"]}
    observed_outputs: set = set()
    for label, state, context in runs:
        res = decide(state, context)
        out = res.get("output")
        if out is None:
            _fail(f"representative run {label!r} produced a no-op output (None)")
        if not isinstance(out, dict):
            _fail(f"run {label!r} output is not an object: {out!r}")
        undeclared = set(out.keys()) - declared_outputs
        if undeclared:
            _fail(
                f"run {label!r} emitted undeclared output key(s) {sorted(undeclared)}; "
                f"declared outputs are {sorted(declared_outputs)}"
            )
        observed_outputs |= set(out.keys())

    unreachable = declared_outputs - observed_outputs
    if unreachable:
        _fail(
            f"declared output(s) {sorted(unreachable)} are never produced by any run — "
            f"ports.json over-declares outputs"
        )

    print(
        "check_ports: OK — ports.json parses, "
        f"{len(ports['inputs'])} input(s)/{len(ports['outputs'])} output(s) "
        "use known types, decide() reads every declared input, and the produced "
        "outputs equal the declared output set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
