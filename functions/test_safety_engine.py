"""Row-by-row tests for the Safety Engine (spec §6)."""
import fallbacks
from episode_state import EpisodeState
from safety_engine import apply_gates


def model(type_="conversation", urgency=None, intents=("reporting_new_symptom",),
          requires=False, change="none", reason=None, card="keep", **over):
    p = {
        "type": type_, "message": "hi", "quick_replies": [], "urgency": urgency,
        "explanation": "x" if type_ == "assessment" else None,
        "watch_for": [], "next_step": None, "possibilities_mentioned": False,
        "self_care": [], "monitoring": [],
        "encouragement": "here" if type_ == "assessment" else None,
        "intents": list(intents), "requires_clinical_reassessment": requires,
        "change_type": change, "reassessment_reason": reason,
        "proposed_card_action": card,
        "findings": ["fever"] if type_ == "assessment" else [],
    }
    p.update(over)
    return p


def guidance(urgency="seek_care_now", latched=()):
    return EpisodeState(
        phase="guidance", current_urgency=urgency,
        min_safe_urgency="seek_care_now" if latched else None,
        latched_rule_ids=list(latched),
    )


IDLE = EpisodeState()


def gates(state, payload, message="hello", rule_ids=(), force_crisis=False):
    return apply_gates(state=state, message=message,
                       current_match_rule_ids=list(rule_ids),
                       force_crisis=force_crisis, model_result=payload)


# --- matrix rows ---

def test_first_assessment_gets_new_card():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("reporting_new_symptom",), requires=True,
                          change="new_symptom", card="new"))
    assert (r.card_action, r.card_reason) == ("new", "first_assessment")


def test_conversation_turn_keeps_card():
    r = gates(guidance(), model())
    assert r.card_action == "keep"
    assert r.payload["type"] == "conversation"
    assert not r.demoted


def test_same_tier_no_change_demotes():
    r = gates(guidance("see_doctor_soon"),
              model("assessment", "see_doctor_soon"))
    assert r.demoted and r.card_action == "keep"
    assert r.payload["type"] == "conversation"
    assert r.payload["urgency"] is None and r.payload["watch_for"] == []
    assert r.payload["message"] == "hi"  # text survives demotion


def test_same_tier_with_clinical_change_updates():
    r = gates(guidance("see_doctor_soon"),
              model("assessment", "see_doctor_soon", requires=True,
                    change="new_symptom"))
    assert (r.card_action, r.card_reason) == ("update", "clinical_change")


def test_urgency_raise_updates():
    r = gates(guidance("monitor_at_home"),
              model("assessment", "seek_care_now", requires=True,
                    change="worsening"))
    assert (r.card_action, r.card_reason) == ("update", "urgency_raised")


def test_new_red_flag_at_same_tier_updates():
    r = gates(guidance("seek_care_now", latched=("rule_a",)),
              model("assessment", "seek_care_now"),
              rule_ids=("rule_b",))
    assert (r.card_action, r.card_reason) == ("update", "new_red_flag")


# --- clamp ---

def test_deescalation_accepted_only_for_resolved_symptom_with_reason():
    ok = gates(guidance("see_doctor_soon"),
               model("assessment", "monitor_at_home", requires=True,
                     change="resolved_symptom", reason="fever gone 2 days"))
    assert ok.deescalation_accepted and ok.final_urgency == "monitor_at_home"
    assert ok.card_reason == "urgency_lowered"

    for bad in [
        model("assessment", "monitor_at_home", requires=True,
              change="treatment_update", reason="saw doctor"),   # wrong type
        model("assessment", "monitor_at_home", requires=True,
              change="resolved_symptom", reason=None),            # no reason
        model("assessment", "monitor_at_home", requires=False,
              change="resolved_symptom", reason="better"),        # no reassess
    ]:
        r = gates(guidance("see_doctor_soon"), bad)
        assert not r.deescalation_accepted
        assert r.final_urgency == "see_doctor_soon"


def test_latch_floor_beats_everything():
    r = gates(guidance("seek_care_now", latched=("rule_a",)),
              model("assessment", "monitor_at_home", requires=True,
                    change="resolved_symptom", reason="all better"))
    assert r.final_urgency == "seek_care_now"
    assert not r.deescalation_accepted


# --- floor-newly-raised guard ---

def test_new_floor_substitutes_static_fallback_over_conversation():
    r = gates(guidance("monitor_at_home"), model(), rule_ids=("rule_a",))
    assert r.payload["urgency"] == "seek_care_now"
    assert r.payload["message"] == fallbacks.STATIC_SEEK_CARE_FALLBACK_EN
    # First-match-wins: the urgency-differs row sits ABOVE new_red_flag
    # (spec §6 matrix), so a floor raise reports urgency_raised.
    assert (r.card_action, r.card_reason) == ("update", "urgency_raised")


def test_new_floor_with_compliant_assessment_passes_through():
    r = gates(guidance("monitor_at_home"),
              model("assessment", "seek_care_now", requires=True,
                    change="worsening"),
              rule_ids=("rule_a",))
    assert r.payload["message"] == "hi"  # model's own words kept
    assert r.card_action == "update"


# --- reset gate ---

def test_reset_accepted():
    r = gates(guidance(), model(intents=("testing_system",), card="clear"))
    assert r.reset_accepted and r.card_action == "clear"
    assert r.assessment_cleared


def test_reset_refused_on_red_flag_message():
    r = gates(guidance(), model(intents=("testing_system",), card="clear"),
              rule_ids=("rule_a",))
    assert not r.reset_accepted


def test_reset_refused_without_reset_intent():
    r = gates(guidance(), model(intents=("casual_chat",), card="clear"))
    assert not r.reset_accepted


def test_reset_refused_when_crisis_locked():
    state = guidance()
    state.phase = "crisis"
    r = gates(state, model(intents=("testing_system",), card="clear"),
              force_crisis=True)
    assert not r.reset_accepted
    assert r.payload["type"] == "crisis"


# --- crisis ---

def test_force_crisis_outranks_everything():
    r = gates(guidance(), model("assessment", "monitor_at_home"),
              force_crisis=True)
    assert r.payload["type"] == "crisis" and r.payload["urgency"] is None
    assert r.card_action == "keep"


# --- domain gate (2026-07-15 design) ---

def test_domain_gate_demotes_assessment_without_eligible_intent():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("off_topic",), requires=True,
                          change="new_symptom", card="new"))
    assert r.payload["type"] == "conversation"
    assert r.card_action == "keep"
    assert r.payload["urgency"] is None
    # This is a distinct event from gate 6's redundant-collapse — demoted
    # deliberately keeps its original narrow meaning (see plan Task 2
    # preamble), so it stays False here.
    assert r.demoted is False


def test_domain_gate_union_lets_mixed_intents_through():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("reporting_new_symptom", "off_topic"),
                          requires=True, change="new_symptom", card="new"))
    assert r.payload["type"] == "assessment"
    assert r.card_action == "new"


def test_domain_gate_leaves_question_type_alone():
    # Scoped to "assessment" only — a "question" turn already can't
    # open/update a card regardless of intents (gate 6 routes every
    # non-assessment type to keep/none), so gating it would add no
    # safety value while risking wrongful demotion of a genuine
    # health_education/medical-conversation clarifying follow-up.
    r = gates(IDLE, model("question", intents=("off_topic",),
                          quick_replies=["A", "B"]))
    assert r.payload["type"] == "question"
    assert r.card_action == "keep"


def test_domain_gate_demotion_clears_stale_quick_replies():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("off_topic",), quick_replies=["A", "B"]))
    assert r.payload["quick_replies"] == []
