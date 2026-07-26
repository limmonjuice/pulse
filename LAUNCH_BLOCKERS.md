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
      CORRECTION 2026-07-26: the earlier "Live-verified 2026-07-13
      via run_pipeline: both turns English, PASS" claim was INVALID
      — it passed only because those specific probe strings happened
      to contain detect_language marker words. THIRD WAVE found
      2026-07-26 in-app: an all-English dog-bite conversation ("hi" /
      "im having hydrophobia" / "i got bit by a dog") flipped to
      Tagalog because every terse turn returned "unknown" from
      detect_language (a function-word counter blind to terse,
      marker-free symptom vocabulary — symmetrically blind to terse
      Tagalog too), so _conversation_language yielded None and the
      directive was silently dropped. Fixed 2026-07-26: expanded the
      detect_language marker sets with terse symptom/reply vocabulary
      (both languages) and added conversation-level inheritance to
      _conversation_language (a terse turn inherits the established
      language, never re-decides). UNIT-VERIFIED ONLY (474 pytest
      green incl. new terse-vocabulary + inheritance + dog-bite
      regression tests); NOT verified on the real model. fasttext/
      langdetect was rejected for this path — its weakest regime is
      short + code-switched text, exactly this workload, and no
      unverifiable probabilistic component ships here while the live
      sweep is quota-blocked (backlogged in POLISH_BACKLOG.md with a
      revisit trigger). STILL OPEN: the full `python
      evals/run_evals.py --category language_mirroring` sweep (now 8
      cases incl. the two terse pins) has not run on the deployed
      model — quota; run it on fresh quota or the prod key, plus a
      Taglish-dengue register spot-check now that its example is
      English-only. Re-verify mirroring on the real model before
      calling this closed — do NOT treat the 2026-07-26 fix as
      verified on the strength of unit tests alone. QUOTA PRIORITY
      (owner, 2026-07-26): this `--category language_mirroring` sweep
      is the FIRST spend of any newly available quota — ahead of the
      visit-summary manual transcripts and ahead of the rest of the
      eval backlog. Three waves of this regression have each cost more
      time than the sweep ever would; it has earned priority. Running
      it green on every turn is the ONLY thing that closes this
      blocker.) A Tagalog-only Pulse silently excludes
      English-preferring users and vice versa. Verification =
      the language_mirroring category green on every turn, on the
      model that is actually deployed; the model-swap guard
      (gemini_client.py MODEL_CHANGELOG + the eval runner's banner)
      flags when this needs re-doing.
- [ ] Prompt 2.1.0 (conversation engine v2 + domain boundary gate) full
      eval sweep + re-baseline pending quota — THE deploy gate for both
      branches. The offline goldens (test_golden_conversations.py) gate
      merges; the live twins (evals categories intent_no_recard,
      deescalation_discipline, reset_flow, mixed_intent_escalation —
      authored 2026-07-14, never run — plus domain_boundary, authored
      2026-07-15, never run) plus a full re-run of every pre-existing
      category must be green on the deployed model before deploy. New
      prompt copy (three 2.0.0 few-shot examples + the TWO KINDS OF
      TURNS section, plus 2.1.0's hard rule 9 and two new few-shot
      examples — software-debugging redirect, health-education diabetes
      answer) is AGENT-DRAFTED, PENDING OWNER READ-ALOUD.
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
      one. Addendum from the domain-boundary-gate work (2026-07-15):
      hard rule 9 now explicitly states it never overrides crisis mode
      (rule 7), and safety_engine.py's crisis gate deterministically
      forces type/urgency regardless of what the model does — but a
      mid-crisis message the model mistakes for off-topic could still
      produce off-topic-flavored message TEXT inside that
      type-forced-to-crisis envelope (the deterministic gate only
      overrides type/urgency, never the model's own message content).
      Worth specifically probing crisis-adjacent + off-topic-adjacent
      inputs during this review, not just the crisis flow in isolation.
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
- [ ] `gemini_client._validate_payload` doesn't null-check
      `explanation`/`next_step` on `"crisis"`-type responses (found
      2026-07-15 during the domain-boundary-gate spec review —
      `"conversation"` type gets explicit checks on both, `"crisis"`
      never did). Checked severity: `crisis_card.dart` only ever reads
      `message` — a stray non-null `explanation`/`next_step` on a
      crisis payload isn't currently rendered anywhere client-side, so
      this is a latent schema gap, not a live user-facing bug. Still
      worth closing before launch — add the same explicit null checks
      `"conversation"` already has, so a future client change or model
      regression can't silently start relying on fields the schema was
      never meant to populate on crisis turns.
- [ ] The domain-boundary gate (safety_engine.py, added 2026-07-15) has
      no dedicated logging signal — found during Task 2's code quality
      review. `main.py`'s structured logs (`_log_request`) can't
      distinguish "the domain gate demoted an assessment turn" from "a
      crisis-forced override landed on an assessment-type turn": both
      produce `card_action="keep"`, `demoted=False`, and a
      `proposed_vs_final_urgency` of the form `"<tier>->None"`, and
      neither `type` nor `card_reason` is logged. This means there is
      currently no way to measure the gate's real-world false-positive
      rate (wrongly redirecting a genuine symptom as off-topic) from
      logs alone once this ships. Not a correctness defect — the gate
      itself behaves correctly regardless of logging — but worth closing
      before calling this feature launched: add a dedicated
      `domain_gate_fired: bool` field to `GateResult`/`_log_request`
      (deliberately distinct from `demoted`, which keeps its narrower
      pre-existing meaning per the domain-boundary-gate design doc §5).
