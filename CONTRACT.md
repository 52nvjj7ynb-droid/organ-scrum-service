# organ-scrum-service — contract

A pure decider for the **virtual daily scrum** standup state machine, extracted
from `app/services/scrum_service.py` (Stream 24 / Day 122) in discovery-engine.

`decide(state, context)` records one freshly-spoken standup contribution and
advances the scrum exactly one step. It is the side-effect-free fusion of two
functions from the source service:

- `advance_scrum()` — record the contribution, advance the turn, or end the
  scrum when the last non-chair persona has reported.
- `get_current_speaker()` — compute whose turn it is from the (post-transition)
  state.

## Single op

This organ has a single decision. There is no `state.op` dispatch.

## Inputs (read from `state`)

| name | type | required | meaning |
|------|------|----------|---------|
| `phase` | string | no (default `"standup"`) | `opening` \| `standup` \| `ended` |
| `turn_order` | array | **yes** | running order: `[{type, project_id}, …]` |
| `turn_index` | integer | no (default `0`) | current 0-based turn |
| `contributions` | array | no (default `[]`) | standup contributions so far |
| `contribution_text` | string | **yes** | what the speaker just said |
| `speaker_name` | string | no | display name of the speaker |
| `speaker_role` | string | no | speaker's role label |
| `speaker_project_id` | integer | no | persona project id (null for a human chair) |
| `is_chair` | boolean | no (default `false`) | chair interjection — does **not** advance |
| `persona_names` | object | no | `{str(project_id): name}` |
| `persona_roles` | object | no | `{str(project_id): role}` |
| `persona_avatars` | object | no | `{str(project_id): emoji}` |
| `persona_voice_ids` | object | no | `{str(project_id): voice_id}` |

`context.now` (an ISO-8601 clock value) stamps the recorded contribution. It is
spine-supplied execution context, **not** a port — when absent the organ stamps
`null` rather than reading a wall clock, keeping `decide()` pure.

## Outputs (written under `output`)

| name | type | meaning |
|------|------|---------|
| `phase` | string | phase **after** the transition |
| `turn_index` | integer | turn **after** the transition |
| `contribution` | object | the contribution just recorded |
| `contributions` | array | full list including the new one |
| `contribution_count` | integer | `len(contributions)` |
| `scrum_ended` | boolean | true ⇒ the spine runs end-of-scrum work |
| `next_speaker` | object \| null | whose turn it is now, or null when ended |

## What stays in the spine (NOT in this organ)

Loading the Interview row, the per-persona LLM standup generation
(`generate_standup`), persisting `metadata_json`, flipping `Interview.status`
to `completed`, and queuing each persona's next-actions as gated approval jobs
(`_queue_scrum_actions`). The organ surfaces `scrum_ended` so the spine knows
when to run those side effects; it performs none of them.
