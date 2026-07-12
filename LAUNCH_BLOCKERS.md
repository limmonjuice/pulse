# Launch Blockers

Things that must be resolved before Pulse is used by anyone besides
the developer, in order of severity.

- [x] Verified PH crisis hotlines in crisis_resources.dart
      (resolved 2026-07-12 — NCMH cross-checked against
      ncmh.gov.ph; In Touch/Hopeline/DSWD from owner research)
- [ ] Clinician review of functions/red_flags.py (REVIEWED_BY still
      None) — rule set needs sign-off from a nurse/med student
      minimum before real symptom data relies on it
- [ ] Mental-health-trained review of the crisis conversation flow
      (system_prompt.py crisis mode + this crisis card) — distinct
      from the clinical review above, flagged separately since day
      one
- [ ] Live end-to-end test of CallableChatRepository against the
      deployed function (blocked on Gemini free-tier quota /
      pending paid credits)
