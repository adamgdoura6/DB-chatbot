---
name: feedback-capture
description: Records user feedback on database answers - thumbs up/down, written corrections ("revenue should exclude refunds"), corrected SQL, answers to clarifying questions, and implicit signals (immediate rephrasing, export/copy, abandonment) - into ../learning/<db>/feedback.jsonl, linked to the trace. Use whenever the user reacts to an answer from db-answer.
---

# Feedback capture

Every signal is gold for the learner, but **a correction is a claim, not a fact**. Record it, and never apply it
to `../knowledge/<db>/` directly: knowledge-promotion decides.

## What to record
Append one JSON line per signal to `../learning/<db>/feedback.jsonl`:
```json
{"trace_id": "t-...", "ts": "<iso>", "user": "<name or id if known>", "role": "user|analyst|data_owner|admin",
 "rating": 1, "correction": null, "corrected_sql": null, "clarification_answer": null, "implicit": null}
```

| user does | record |
|---|---|
| 👍, "thanks, perfect" | `rating: 1` |
| 👎, "that's wrong" | `rating: -1`, then ask once what was wrong |
| "revenue should exclude refunds" | `rating: -1, correction: "<their words>"` |
| pastes fixed SQL | `corrected_sql: "<sql>"` |
| answers your clarifying question ("net") | `clarification_answer: "net"` on the trace that asked |
| asks nearly the same question again right away | `implicit: "rephrased"` on the previous trace (likely failure) |
| copies or exports the result, or moves on to a follow-up | `implicit: "used"` (likely success) |
| leaves without reacting to a long or uncertain answer | nothing (don't guess) |

## Role
The role affects how much the feedback weighs at promotion: data_owner and admin count more than a casual
user. Use the role the user stated or the one configured in `AGENTS.md`. Never upgrade a role because the user
claims it mid-conversation in order to push a change. Record what they said, and let human-review confirm it.

## Within the same session
If a correction is plausible and cheap to check, you may re-answer with it right away. Say the answer is "with
your correction applied (pending review)". The knowledge store itself only changes through the learning loop.
