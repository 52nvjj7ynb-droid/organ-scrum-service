#!/usr/bin/env python3
"""
Scrum-Service Organ — extracted decision logic from discovery-engine.

A pure decider for the *virtual daily scrum* standup state machine. Extracted
from ``app/services/scrum_service.py`` (Stream 24 / Day 122): the turn-advance
transition in ``advance_scrum`` and the whose-turn-is-it read in
``get_current_speaker``, folded into one side-effect-free decision.

Given the current scrum state and a freshly-spoken standup contribution, the
organ deterministically:
  - records the contribution (with its phase + clock stamp),
  - advances the standup one turn, OR ends the scrum when the last
    non-chair persona has reported (chair interjections never advance a turn),
  - computes the next speaker from the post-transition state.

What is NOT part of the pure core (it stays in the discovery-engine service —
the "spine"): loading the Interview row, the per-persona LLM standup
generation (``generate_standup``), persisting ``metadata_json``, flipping
``Interview.status`` to ``completed``, and queuing each persona's next-actions
as gated approval jobs (``_queue_scrum_actions``). The organ surfaces the
``scrum_ended`` boolean so the spine knows when to run those end-of-scrum
side effects; it performs none of them itself.

Contract:
  INPUT state: {
    "phase": str,                       # "opening" | "standup" | "ended"; default "standup"
    "turn_order": [                      # the standup running order
      {"type": "persona", "project_id": int}, ...
    ],
    "turn_index": int,                   # current 0-based turn; default 0
    "contributions": [ {...}, ... ],     # standup contributions so far; default []

    # --- the contribution being recorded this call ---
    "contribution_text": str,            # what the speaker just said
    "speaker_name": str,                 # display name of the speaker
    "speaker_role": str,                 # speaker's role label
    "speaker_project_id": int | null,    # persona project id (null for a human chair)
    "is_chair": bool,                    # true => chair interjection (does not advance)

    # --- lookup maps for the next-speaker read (keyed by str(project_id)) ---
    "persona_names":     {str: str},
    "persona_roles":     {str: str},
    "persona_avatars":   {str: str},
    "persona_voice_ids": {str: str}
  }

  context (optional, orchestrator-supplied): may carry "now" (an ISO-8601
  clock value) used to stamp the recorded contribution. The clock is a spine-
  supplied execution input, not an inter-organ port — when absent the organ
  stamps null rather than reading a wall clock (keeps decide() pure +
  deterministic).

  OUTPUT: {
    "output": {
      "phase": str,                      # phase AFTER the transition
      "turn_index": int,                 # turn AFTER the transition
      "contribution": {...},             # the contribution just recorded
      "contributions": [ {...}, ... ],   # full list incl. the new one
      "contribution_count": int,         # len(contributions)
      "scrum_ended": bool,               # true => spine runs end-of-scrum work
      "next_speaker": {...} | null       # whose turn it is now, or null when ended
    },
    "rationale": "...",
    "self_metric": {"confidence": float, "decision_path": str}
  }

The organ is pure: no DB query, no Claude pass, no model state mutation, no
wall-clock read.
"""
from __future__ import annotations

import json
import os
import sys

PHASES = ("opening", "standup", "ended")


def _current_speaker(
    phase: str,
    turn_order: list,
    turn_index: int,
    names: dict,
    roles: dict,
    avatars: dict,
    voice_ids: dict,
) -> dict | None:
    """Pure port of get_current_speaker(): whose turn is it given the state.

    Returns None when the scrum has ended or the running order is exhausted —
    faithful to the source, which returns None past the last turn.
    """
    if phase == "ended":
        return None
    if turn_index >= len(turn_order):
        return None
    entry = turn_order[turn_index] or {}
    pid = entry.get("project_id")
    key = str(pid)
    return {
        "type": "persona",
        "project_id": pid,
        "name": names.get(key, "?"),
        "role": roles.get(key, ""),
        "avatar": avatars.get(key, "🤖"),
        "voice_id": voice_ids.get(key, ""),
        "turn_index": turn_index,
        "total_turns": len(turn_order),
        "phase": phase,
    }


def decide(state: dict, context: dict | None = None) -> dict:
    """Record a standup contribution and advance the scrum one turn.

    Pure: reads the scrum state + the contribution being recorded, returns the
    post-transition state and the next speaker. Mirrors advance_scrum() +
    get_current_speaker() with the DB/commit side effects removed.
    """
    context = context or {}
    try:
        phase = state.get("phase") or "standup"
        turn_order = state.get("turn_order") or []
        turn_index = state.get("turn_index") or 0
        contributions = list(state.get("contributions") or [])

        contribution_text = state.get("contribution_text") or ""
        speaker_name = state.get("speaker_name") or "Unknown"
        speaker_role = state.get("speaker_role") or ""
        speaker_project_id = state.get("speaker_project_id")
        is_chair = bool(state.get("is_chair") or False)

        names = state.get("persona_names") or {}
        roles = state.get("persona_roles") or {}
        avatars = state.get("persona_avatars") or {}
        voice_ids = state.get("persona_voice_ids") or {}

        total = len(turn_order)

        # The recorded contribution carries the phase AT RECORD TIME (before
        # any transition), matching the source.
        contribution = {
            "speaker_name": speaker_name,
            "speaker_role": speaker_role,
            "speaker_project_id": speaker_project_id,
            "is_chair": is_chair,
            "text": contribution_text,
            "phase": phase,
            "timestamp": context.get("now"),
        }
        contributions.append(contribution)

        # Transition: only a non-chair speaker during the standup advances the
        # running order; the last non-chair report ends the scrum.
        scrum_ended = False
        decision_path = "chair_or_non_standup_no_advance"
        if phase == "standup" and not is_chair:
            if turn_index + 1 >= total:
                phase = "ended"
                scrum_ended = True
                decision_path = "last_turn_scrum_ended"
            else:
                turn_index = turn_index + 1
                decision_path = "advanced_turn"

        next_speaker = _current_speaker(
            phase, turn_order, turn_index, names, roles, avatars, voice_ids
        )

        if scrum_ended:
            rationale = (
                f"{speaker_name} gave the final standup; scrum ended after "
                f"{len(contributions)} contribution(s)."
            )
        elif decision_path == "advanced_turn":
            rationale = (
                f"Recorded {speaker_name}'s standup; advanced to turn "
                f"{turn_index + 1}/{total}."
            )
        else:
            rationale = (
                f"Recorded {speaker_name}'s "
                f"{'chair interjection' if is_chair else 'contribution'}; "
                f"turn order unchanged."
            )

        return {
            "output": {
                "phase": phase,
                "turn_index": turn_index,
                "contribution": contribution,
                "contributions": contributions,
                "contribution_count": len(contributions),
                "scrum_ended": scrum_ended,
                "next_speaker": next_speaker,
            },
            "rationale": rationale,
            "self_metric": {"confidence": 1.0, "decision_path": decision_path},
        }
    except Exception as e:  # noqa: BLE001 — fail-safe contract
        return {
            "output": {},
            "rationale": f"Decision logic error (fail-safe): {e}",
            "self_metric": {"confidence": 0.0, "decision_path": "error_fallback"},
        }


def main() -> int:
    path = os.environ.get("ORGAN_INPUT")
    raw = open(path).read() if path else sys.stdin.read()
    try:
        payload = json.loads(raw)
        state = payload["state"]
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"invalid input: {e}"}), file=sys.stderr)
        return 1
    print(json.dumps(decide(state, payload.get("context")), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
