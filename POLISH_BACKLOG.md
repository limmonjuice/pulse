# Polish Backlog

Non-blocking gaps and rough edges worth fixing eventually. Nothing here
blocks launch — see LAUNCH_BLOCKERS.md for those.

- [ ] detect_language (mirror_probes.py) is a whole-word function-word +
      symptom-vocabulary counter. It was expanded 2026-07-26 to cover
      terse symptom/reply vocabulary in both languages after the third
      mirroring regression, but it stays a hand-maintained marker list:
      inflected forms are matched only via pronoun/particle markers (e.g.
      "nilalagnat" classifies via "ako", not "lagnat"), and genuinely
      novel terse phrasings can still return "unknown". A real
      language-detection library (fasttext-lid / cld3 / langid) was
      DELIBERATELY NOT adopted here: its weakest regime is short +
      code-switched text — precisely this workload — and an unverifiable
      probabilistic component must not enter this safety-adjacent path
      while the live eval sweep is quota-blocked. REVISIT TRIGGER: only
      if a real post-quota `evals/run_evals.py --category
      language_mirroring` sweep on the deployed model STILL shows
      language misses after the marker expansion. If it does, re-evaluate
      a library against the terse + code-switched eval cases specifically,
      not in the abstract.

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
