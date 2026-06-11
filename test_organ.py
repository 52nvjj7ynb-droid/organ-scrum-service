"""Tests for the scrum-service organ — the pure standup state machine.

Covers the three transition paths (advance, end, chair-no-advance), the
next-speaker read, the fail-safe contract, and the committed samples.
"""
import json
import os

import pytest

from organ import decide

HERE = os.path.dirname(os.path.abspath(__file__))


def _base_state(**over):
    state = {
        "phase": "standup",
        "turn_order": [
            {"type": "persona", "project_id": 3},
            {"type": "persona", "project_id": 5},
        ],
        "turn_index": 0,
        "contributions": [],
        "contribution_text": "DONE x. NEXT y. BLOCKERS none.",
        "speaker_name": "Tim",
        "speaker_role": "Head of Sales",
        "speaker_project_id": 3,
        "is_chair": False,
        "persona_names": {"3": "Tim", "5": "Matt"},
        "persona_roles": {"3": "Head of Sales", "5": "CTO"},
        "persona_avatars": {"3": "🧑‍💼", "5": "🧑‍💻"},
        "persona_voice_ids": {"3": "voice_tim", "5": "voice_matt"},
    }
    state.update(over)
    return state


# --- transition: advance to the next persona --------------------------------

def test_advance_to_next_turn():
    out = decide(_base_state(), {"now": "2026-06-11T09:00:00"})["output"]
    assert out["phase"] == "standup"
    assert out["scrum_ended"] is False
    assert out["turn_index"] == 1
    assert out["contribution_count"] == 1
    # next speaker is the second persona
    assert out["next_speaker"]["project_id"] == 5
    assert out["next_speaker"]["name"] == "Matt"
    assert out["next_speaker"]["turn_index"] == 1
    assert out["next_speaker"]["total_turns"] == 2


def test_recorded_contribution_carries_record_phase_and_clock():
    out = decide(_base_state(), {"now": "2026-06-11T09:00:00"})["output"]
    c = out["contribution"]
    assert c["speaker_name"] == "Tim"
    assert c["phase"] == "standup"  # phase at record time, before transition
    assert c["timestamp"] == "2026-06-11T09:00:00"
    assert c["is_chair"] is False
    # appended to the running list
    assert out["contributions"][-1] == c


def test_missing_clock_stamps_null_not_wallclock():
    out = decide(_base_state(), None)["output"]
    assert out["contribution"]["timestamp"] is None


# --- transition: last turn ends the scrum -----------------------------------

def test_last_turn_ends_scrum():
    out = decide(_base_state(turn_index=1, speaker_project_id=5, speaker_name="Matt"), {})["output"]
    assert out["phase"] == "ended"
    assert out["scrum_ended"] is True
    # turn_index does not advance past the end
    assert out["turn_index"] == 1
    # no next speaker once ended
    assert out["next_speaker"] is None


# --- transition: chair interjection does not advance ------------------------

def test_chair_interjection_does_not_advance():
    out = decide(
        _base_state(is_chair=True, speaker_name="Jules", speaker_role="Chair", speaker_project_id=None),
        {},
    )["output"]
    assert out["scrum_ended"] is False
    assert out["turn_index"] == 0  # unchanged
    assert out["contribution_count"] == 1
    assert out["contribution"]["is_chair"] is True
    # still Tim's turn (the chair spoke out of band)
    assert out["next_speaker"]["project_id"] == 3


def test_non_standup_phase_does_not_advance():
    out = decide(_base_state(phase="opening"), {})["output"]
    assert out["phase"] == "opening"
    assert out["scrum_ended"] is False
    assert out["turn_index"] == 0


# --- next-speaker lookups defensive fallbacks -------------------------------

def test_next_speaker_unknown_pid_uses_fallbacks():
    state = _base_state(
        turn_order=[{"type": "persona", "project_id": 99}],
        persona_names={},
        persona_roles={},
        persona_avatars={},
        persona_voice_ids={},
        turn_index=0,
    )
    # single persona -> ends after this contribution, so next_speaker is None
    out = decide(state, {})["output"]
    assert out["next_speaker"] is None


def test_next_speaker_fallback_glyphs_when_not_ended():
    # two-persona order, unknown second pid -> next_speaker uses default glyphs
    state = _base_state(
        turn_order=[{"type": "persona", "project_id": 3}, {"type": "persona", "project_id": 99}],
        persona_names={"3": "Tim"},
        persona_avatars={"3": "🧑‍💼"},
    )
    out = decide(state, {})["output"]
    ns = out["next_speaker"]
    assert ns["project_id"] == 99
    assert ns["name"] == "?"
    assert ns["avatar"] == "🤖"
    assert ns["voice_id"] == ""


# --- fail-safe contract ------------------------------------------------------

def test_failsafe_on_bad_turn_order():
    # turn_order is not a list -> len() inside raises -> fail-safe empty output
    res = decide({"turn_order": 123, "contribution_text": "x"}, {})
    assert res["output"] == {}
    assert res["self_metric"]["confidence"] == 0.0
    assert res["self_metric"]["decision_path"] == "error_fallback"


# --- committed samples are well-formed --------------------------------------

@pytest.mark.parametrize(
    "fname",
    sorted(f for f in os.listdir(os.path.join(HERE, "samples")) if f.endswith(".json")),
)
def test_samples_run_clean(fname):
    with open(os.path.join(HERE, "samples", fname)) as fh:
        payload = json.load(fh)
    res = decide(payload["state"], payload.get("context"))
    assert res["self_metric"]["confidence"] == 1.0
    assert set(res["output"].keys()) == {
        "phase", "turn_index", "contribution", "contributions",
        "contribution_count", "scrum_ended", "next_speaker",
    }
