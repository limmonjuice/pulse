# Polish Backlog

Non-blocking gaps and rough edges worth fixing eventually. Nothing here
blocks launch — see LAUNCH_BLOCKERS.md for those.

- [ ] `gemini_client._validate_payload` never checks `watch_for` for
      emptiness on `"question"`/`"crisis"`/`"conversation"` types (only
      `self_care`/`monitoring`/`encouragement`/`findings` are checked) —
      found 2026-07-15 during the domain-boundary-gate spec review.
      Every few-shot example and the prompt text both say `watch_for`
      should be `[]` on those types, but nothing in the validator
      enforces it. Cosmetic: no known path currently produces a
      non-empty `watch_for` on a non-assessment type. Worth closing so
      a future prompt regression can't silently attach a watch-for list
      to a turn the client has no card to render it on.
