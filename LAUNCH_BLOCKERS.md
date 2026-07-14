# Launch Blockers

Things that must be resolved before Pulse is used by anyone besides
the developer, in order of severity.

- [x] Verified PH crisis hotlines in crisis_resources.dart
      (resolved 2026-07-12 — NCMH cross-checked against
      ncmh.gov.ph; In Touch/Hopeline/DSWD from owner research)
- [ ] Language mirroring verified on the CURRENT production model —
      re-verify after ANY model swap (regressed 2026-07-12 on the
      3.1-flash-lite swap; root-caused 2026-07-13 and fixed through
      prompt v1.5.4: conditional register rule, deck fixes, and —
      owner decision 2026-07-13 — removal of the Taglish dengue
      few-shot, whose presence probe-provenly made English
      dengue-shaped openers mirror Tagalog. SECOND WAVE found
      2026-07-13 in-app, post-1.5.4: tapped quick-reply chips
      ("Stomach pain or nausea") still flipped English conversations
      to Tagalog — bare symptom nouns read as code-switched Taglish
      register, and live probes showed no prompt-side rule or
      few-shot twin beat that prior. Fixed in v1.5.5 (deployed
      2026-07-13) by taking the decision away from the model:
      main._conversation_language derives the language
      deterministically from the user's own turns (chip taps are
      below the word threshold and can never flip it) and section 9
      states it as an explicit CONVERSATION LANGUAGE directive.
      Live-verified 2026-07-13 on the exact regressed sequence via
      run_pipeline: both turns English, PASS. STILL OPEN: the full
      `python evals/run_evals.py --category language_mirroring`
      sweep (now 6 cases incl. the terse-chip pin) has not run on
      v1.5.5 — quota; run it on fresh quota or the prod key, plus a
      Taglish-dengue register spot-check now that its example is
      English-only). A Tagalog-only Pulse silently excludes
      English-preferring users and vice versa. Verification =
      the language_mirroring category green on every turn, on the
      model that is actually deployed; the model-swap guard
      (gemini_client.py MODEL_CHANGELOG + the eval runner's banner)
      flags when this needs re-doing.
- [ ] Prompt 2.0.0 (conversation engine v2) full eval sweep +
      re-baseline pending quota — THE deploy gate for the engine v2
      branch. The offline goldens (test_golden_conversations.py) gate
      merges; the live twins (evals categories intent_no_recard,
      deescalation_discipline, reset_flow, mixed_intent_escalation —
      authored 2026-07-14, never run) plus a full re-run of every
      pre-existing category must be green on the deployed model
      before deploy. New prompt copy (three 2.0.0 few-shot examples +
      the TWO KINDS OF TURNS section) is AGENT-DRAFTED, PENDING OWNER
      READ-ALOUD.
- [ ] red_flags.py has NO rule matching blood in vomit (hematemesis) —
      "vomiting blood", "throwing up blood", "blood in my vomit",
      "nagsusuka ng dugo" all miss (found 2026-07-14 authoring the
      golden conversations; the bleeding_uncontrolled "unexpected
      body fluid" entry covers phlegm/urine/stool only). This is the
      owner's own canonical emergency example. Clinical change —
      fold into the clinician review below rather than self-adding.
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
- [ ] Swap GEMINI_API_KEY in functions/.env for the real production
      key and redeploy before launch — the key deployed 2026-07-13
      is the free-tier testing key only (owner decision 2026-07-13)
- [ ] Firebase App Check API not yet enabled for pulse-3a13c
      (found 2026-07-12 — first live-mode test failed with
      "Firebase App Check API has not been used in project
      59929382829"). Enable it in Cloud Console, then register the
      AndroidDebugProvider's debug token in Firebase Console > App
      Check > Apps before debug-build calls to assess_symptoms will
      succeed (enforce_app_check defaults to True in main.py). Blocks
      the item above, too — can't live-test the callable until this
      is done.
