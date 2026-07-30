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
      revisit trigger). SWEEP RAN 2026-07-26 ON FRESH QUOTA — AND DID
      NOT CONFIRM THE FIX. `python evals/run_evals.py --category
      language_mirroring` (8 cases) reported 9/9 checks passed (100%)
      on prompt 2.1.0 / gemini-3.1-flash-lite, but that green is
      largely vacuous and MUST NOT be read as verification. Report:
      evals/results/2.1.0_gemini-3.1-flash-lite_20260726T060440Z.json.
      Three reasons it proves less than it looks:
      (1) ZERO LIVE COVERAGE OF CONVERSATION-LEVEL INHERITANCE — the
      actual heart of the 2026-07-26 fix. 4 of 9 turns failed schema
      validation on the first attempt and went through the corrective
      retry, which (pre-fix, see the apology-leak entry below) returned
      `type="conversation"` payloads. The harness loop only continues
      while `type == "question"`, so the three multi-turn terse cases
      broke after ONE turn and never consumed a single scripted reply.
      Only single-turn detection was exercised; a terse turn inheriting
      an established language was never tested against the real model.
      (2) ONE MANUFACTURED PASS — `check_language` scored a
      `type="error"` turn, i.e. Pulse's own hardcoded
      FRIENDLY_DEGRADED_ERROR_MESSAGE_EN, as an English mirroring pass.
      That check tested Pulse's own string, not model output. Fixed in
      the harness 2026-07-26 (non-evaluable on Pulse-constructed turns).
      (3) The checker judges replies with `mirror_probes.detect_language`
      — the same detector the fix modified. Safe direction (an "unknown"
      fails), but not an independent oracle.
      WHAT THE RUN DOES LEGITIMATELY SUPPORT: single-turn mirroring on
      terse input held on the deployed model — "i got bit by a dog" →
      English reply + English quick_replies; "nilalagnat ako" → Tagalog
      reply + Tagalog quick_replies; all four full-sentence cases clean.
      That is the easy half.
      SECOND RUN 2026-07-26, after the apology-leak fix — THE MECHANISM
      NOW HAS LIVE COVERAGE AND HELD. Report:
      evals/results/2.1.0_gemini-3.1-flash-lite_20260726T122643Z.json.
      Targeted at the two cases that had zero multi-turn coverage
      (`--case terse_dog_bite,tagalog_terse`), since running the full
      category in CASES order would have spent the remaining quota
      re-measuring the four single-turn cases and died before reaching
      these. Result: 5 passed / 0 failed / 0 non-evaluable, no degraded
      turns, no manufactured greens.
      - `english_terse_dog_bite` reached turn 2: "i got bit by a dog" →
        English question; terse reply "im dizzy" → English assessment.
      - `tagalog_terse` reached turn 3: "nilalagnat ako" → Tagalog
        question; "inuubo ako" → Tagalog question; a BARE "oo" →
        Tagalog assessment. That last turn is the strongest single
        piece of evidence in the whole saga: a one-word turn that the
        pre-fix newest-confident fallback would have let re-decide the
        conversation language, inheriting correctly instead.
      Conversation-level inheritance — the part with zero coverage in
      the morning run — is now live-verified in BOTH directions.
      The retry fix is also confirmed by the same run: 3 first-attempt
      schema rejections occurred and every one retried into a proper
      question/assessment turn with no apology copy and no derailed
      `type="conversation"` turn — the exact failure that collapsed the
      multi-turn loop hours earlier.
      *** THIRD RUN 2026-07-27: FULL CATEGORY PASS IN ONE SWEEP ***
      Report: evals/results/2.1.0_gemini-3.1-flash-lite_20260726T170608Z.json.
      All 8 cases, one pass, on current code (apology-leak fix + findings
      coercion): 13 passed / 0 failed / 0 NON-EVALUABLE / 0 crashes /
      0 API errors / 0 first-attempt schema rejections. Every turn of
      every case green, including all three multi-turn terse cases,
      which this time genuinely ran multi-turn:
        - english_terse_chip_taps (WAVE 2, uncovered until now): 3 turns
          — opener, chip tap "Stomach pain or nausea", "Just started
          today" — all English, ending in an English assessment. This is
          the exact input that flipped to Tagalog in the 2026-07-13
          in-app screenshots.
        - english_terse_dog_bite (WAVE 3): 2 turns, terse "im dizzy"
          stayed English.
        - tagalog_terse: 3 turns, a bare "oo" stayed Tagalog.
      Zero non-evaluable means no turn was Pulse-constructed — every
      check scored real model output, so the 100% is not the vacuous
      kind the first sweep produced.
      THE AUTOMATED VERIFICATION CRITERION STATED BELOW IS NOW MET.
      Box left unticked pending ONE remaining human item: the
      Taglish-dengue register spot-check (does the Taglish read as
      everyday register, not formal Tagalog?) — an owner read-aloud,
      not something the harness or an agent can sign off. The
      taglish_stays_taglish case passed and its reply is in the report
      for that read. Tick this box after it.
      NOTE for whoever reads this next: one case
      (english_no_regional_context) ended on question-budget exhaustion
      — the model asked a clarifying question and that case carries no
      scripted_replies. Its turn-1 mirroring check passed; the budget
      fact is reported separately and is NOT a mirroring failure. Worth
      adding scripted replies to that case so it exercises more than one
      turn (POLISH_BACKLOG, not a blocker).
      QUOTA NOTE (updated 2026-07-27): the 20/day figure does NOT bind
      on 3.1-flash-lite. Measured: 21 calls on 2026-07-26 (13 + 8) with
      no 429, plus 13 more on 2026-07-27. Free-tier RPD for this model
      is therefore >=21/day; the 20/day ceiling was measured on
      2.5-flash-lite and never applied here. The model swap was
      2026-07-13, so the larger allowance was in effect the whole time
      and the 2026-07-26 rationing was against a figure that did not
      apply. Owner decision 2026-07-27: treat quota as a non-constraint
      for now. The exact ceiling remains unmeasured — record what runs
      observe rather than asserting a number.) A Tagalog-only Pulse silently excludes
      English-preferring users and vice versa. Verification =
      the language_mirroring category green on every turn, on the
      model that is actually deployed; the model-swap guard
      (gemini_client.py MODEL_CHANGELOG + the eval runner's banner)
      flags when this needs re-doing.
- [x] Schema-repair apology leak reaching user-facing copy (found
      2026-07-26 in the language_mirroring sweep, fixed same day).
      `_call_gemini_with_retry` appended the malformed reply plus a
      corrective USER turn to `contents`, so the model read it as the
      user complaining about a broken response and apologised in the
      `message` field: "I apologize for that error. I am ready to
      continue helping you with your health questions." and "Pasensya na
      kung nagkaroon ng error sa format." — both shipped verbatim in the
      sweep's report. Fixed by moving the repair directive to the
      system-instruction position (the retry re-sends the SAME
      `contents`, so the conversational surface never learns anything
      went wrong) plus an enforcement blocklist on error/format/apology
      language in user-visible fields, modelled on the existing
      tier-language blocklist and covering `message` and the visit
      summary alike. This class was structurally invisible to the mocked
      suite, which never made a first attempt fail — the new tests
      script first-attempt-fails/retry-succeeds explicitly.
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
- [x] 2.1.0 first-attempt schema-validation failure rate (~44% observed
      2026-07-26) — characterised, fixed and re-measured 2026-07-27.
      RESOLVED: the coercion fix took the rate from ~44% to ZERO. The
      2026-07-27 full sweep logged 0 first-attempt schema rejections
      across 13 turns, with `FIELDS COERCED (retries avoided):
      {'findings': 5}` — i.e. 5 turns that would each have burned a
      second API call now cost one, and no turn reached the user as a
      degraded fallback. Quota cost of the category dropped from a
      projected ~18 calls to 13. The rate stays measurable via the
      coerced_field structured log, so a future regression is visible
      rather than silent. Original characterisation kept below.
      At least 4 of 9 live
      turns in the language_mirroring sweep failed `_validate_payload`
      on the first attempt and needed the corrective retry; one
      (`english_terse_chip_taps` turn 2, the chip tap "Stomach pain or
      nausea") failed TWICE and reached the user as a degraded-mode
      error. Costs: 2x quota and 2x latency per affected turn against a
      20/day free tier, and exhausted retries are user-visible.
      ~44% is a LOWER BOUND — a retry that succeeded without leaving
      apology copy behind leaves no trace in the report at all.
      CHARACTERISATION IS BLOCKED ON INSTRUMENTATION, NOT ON QUOTA: the
      report preserves NO evidence of what failed. `_retry_used` is
      popped by main.py for logging before the response is built, and
      the rejected payload and its ValueError reason are discarded
      inside `_call_gemini_with_retry`. The 2026-07-26 retry fix now
      captures that reason (it feeds the system-instruction repair
      directive) but still does not persist it. PREREQUISITE for the
      next sweep: log the rejection reason in main.py's structured logs
      and carry `retry_used` + `rejection_reason` into the eval report,
      so the quota-priority mirroring re-run characterises this for
      free instead of needing a second spend.
      *** HYPOTHESIS CONFIRMED ON THE LIVE MODEL 2026-07-26 *** — the
      instrumentation paid for itself on its first run. The second
      sweep logged 3 first-attempt rejections and ALL THREE carry the
      identical reason: `question responses require empty findings`
      (`english_terse_dog_bite` t1, `tagalog_terse` t1 and t2). So this
      is NOT general instruction-following drift — it is ONE rule,
      violated exactly where predicted: a turn that must ask a question
      while carrying an extractable symptom. The model records the
      finding it just heard; `_validate_payload` rejects any non-empty
      `findings` outside an assessment. Note the prompt is already
      explicit about this ("[] on every other turn type"), so
      prompt-side clarification is now the WEAKER option — the rule is
      stated and still lost. RECOMMENDED FIX (revised, still not
      implemented): schema tolerance — coerce `findings` to [] on
      non-assessment turns instead of rejecting, since safety_engine
      already owns findings state and the model's proposal is discarded
      there anyway. That would eliminate 3 of 3 observed rejections,
      halve the quota/latency cost of those turns, and remove a
      user-visible degraded-fallback path, at near-zero risk. Confirm
      against a larger sample before committing.
      ORIGINAL HYPOTHESIS (recorded 2026-07-26 before the evidence
      existed, kept for the record): failures cluster on turns that
      must ask a QUESTION while carrying an extractable symptom. All 4
      first-run failures
      ("sore throat since yesterday and a mild fever", "Stomach pain or
      nausea", "i got bit by a dog", "nilalagnat ako") are that shape;
      the one question turn that SUCCEEDED first time ("Ive been
      feeling sick lately") had nothing extractable. In that state the
      model has obvious `findings` but the schema requires `findings:
      []` on every non-assessment turn (`_validate_payload`'s
      `response_type != "assessment" and findings` rule, new in v2), and
      also requires 2-4 `quick_replies` plus null urgency/encouragement
      and empty self_care/monitoring. Secondary candidate: vocabulary
      drift across the 24-value `VALID_INTENTS` / `VALID_CHANGE_TYPES` /
      `VALID_CARD_ACTIONS` closed sets. Note one real prompt
      inconsistency found while checking this: the field spec says
      `quick_replies` is "[] otherwise" (i.e. outside question turns)
      while the conversation paragraph allows up to 4 — harmless today
      because the validator is the permissive one, but it should be
      reconciled. Ranked fixes proposed 2026-07-26, NOT implemented:
      (1) instrument, then re-measure; (2) prompt-side — make the
      question-turn empties explicit at the point of decision rather
      than only in the field list; (3) schema tolerance — coerce a
      non-empty `findings` on a non-assessment turn to [] instead of
      rejecting, since safety_engine already owns findings state;
      (4) model-tier decision, last resort and a cost change.
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
