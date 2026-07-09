"""
Tests for red_flags.py — the deterministic emergency-detection layer.

Run from functions/:
    pytest test_red_flags.py -v
"""

import pytest

from red_flags import RED_FLAG_RULES, check_red_flags

# One canonical message per rule id, used only by the registry completeness
# check below. Real coverage (2+ phrasings per rule, Taglish variants, etc.)
# lives in the per-rule test functions further down.
CANONICAL_POSITIVE_EXAMPLE = {
    "chest_pain_breathing": ("I have chest pain and I'm having trouble breathing", None),
    "stroke_signs": ("her face is drooping on one side and she can't speak properly", None),
    "bleeding_uncontrolled": ("he is bleeding a lot and it won't stop", None),
    "anaphylaxis_signs": ("her lips are swelling up and she's having trouble breathing", None),
    "loss_of_consciousness_seizure": ("he suddenly collapsed and is not responding", None),
    "severe_breathing_difficulty": ("she can't speak full sentences and her lips are turning blue", None),
    "self_harm_risk": ("I want to kill myself", None),
    "infant_fever": ("my baby has a fever", {"age_months": 2}),
    "severe_dehydration_young_child": (
        "my toddler hasn't urinated all day and looks very sleepy and limp",
        {"age": 2},
    ),
    "pregnancy_red_flags": ("I'm 20 weeks pregnant and having heavy bleeding", None),
}


def assert_fires(message, expected_rule_id, profile=None):
    result = check_red_flags(message, profile)
    assert result.matched, f"expected a red-flag match for: {message!r}"
    assert expected_rule_id in result.rule_ids, (
        f"expected {expected_rule_id!r} in {result.rule_ids} for message {message!r}"
    )


def assert_does_not_fire(message, profile=None, rule_id=None):
    result = check_red_flags(message, profile)
    if rule_id is None:
        assert not result.matched, f"expected no match for: {message!r}, got {result.rule_ids}"
    else:
        assert rule_id not in result.rule_ids, (
            f"expected {rule_id!r} not to fire for: {message!r}"
        )


# ---------------------------------------------------------------------------
# Normalization robustness
# ---------------------------------------------------------------------------

def test_normalization_handles_mixed_case_and_punctuation():
    assert_fires("CHEST PAIN!!! and... Trouble BREATHING??", "chest_pain_breathing")


def test_normalization_collapses_extra_whitespace_and_runon_phrasing():
    assert_fires(
        "chest    pain     and    trouble   breathing  right now please help me",
        "chest_pain_breathing",
    )


def test_normalization_handles_apostrophes():
    assert_fires("I have chest pain and I can't breathe properly", "chest_pain_breathing")


# ---------------------------------------------------------------------------
# Calibration (negative) cases
# ---------------------------------------------------------------------------

def test_mild_chest_discomfort_after_workout_does_not_fire():
    assert_does_not_fire("mild chest discomfort after workout yesterday, fine now")


def test_cold_and_cough_does_not_fire():
    assert_does_not_fire("may sipon at ubo lang ako, ok naman ako ngayon")


def test_blood_pressure_medication_alone_does_not_fire_bleeding_rule():
    assert_does_not_fire(
        "I forgot to take my blood pressure medication today",
        rule_id="bleeding_uncontrolled",
    )


def test_chest_pain_without_breathing_trouble_does_not_fire_that_rule():
    assert_does_not_fire(
        "I have some mild chest pain but my breathing is totally fine",
        rule_id="chest_pain_breathing",
    )


def test_plain_difficulty_breathing_alone_does_not_fire_severe_rule():
    # Generic "hirap huminga" alone isn't specific enough on its own —
    # only chest-pain co-occurrence or a severe indicator should fire.
    assert_does_not_fire("hirap akong huminga simula kanina", rule_id="severe_breathing_difficulty")
    assert_does_not_fire("hirap akong huminga simula kanina", rule_id="chest_pain_breathing")


# ---------------------------------------------------------------------------
# chest_pain_breathing
# ---------------------------------------------------------------------------

def test_chest_pain_breathing_english():
    assert_fires("I have chest pain and I'm having trouble breathing", "chest_pain_breathing")


def test_chest_pain_breathing_taglish():
    assert_fires("sobrang sakit ng dibdib ko at hirap akong huminga", "chest_pain_breathing")


def test_chest_pain_breathing_alternate_phrasing():
    assert_fires("there's tightness in my chest and I can't catch my breath, shortness of breath too", "chest_pain_breathing")


def test_chest_pain_breathing_ilocano():
    # Ilocano — lower confidence than the Tagalog phrasings above; needs
    # native Ilocano-speaker review even more urgently. See module note.
    assert_fires("adda ut-ot ti barukong na ken narigat nga aganges", "chest_pain_breathing")


# ---------------------------------------------------------------------------
# stroke_signs
# ---------------------------------------------------------------------------

def test_stroke_face_drooping_english():
    assert_fires("my dad's face is drooping on one side since this morning", "stroke_signs")


def test_stroke_face_drooping_taglish():
    assert_fires("bigla nalihis ang bibig niya at pilay ang mukha", "stroke_signs")


def test_stroke_one_sided_weakness_english():
    assert_fires("sudden weakness on one side of his body, can't lift his arm", "stroke_signs")


def test_stroke_one_sided_weakness_taglish():
    assert_fires("manhid at panghihina sa isang bahagi ng katawan niya biglaan", "stroke_signs")


def test_stroke_slurred_speech_english():
    assert_fires("she suddenly has slurred speech and can't speak properly", "stroke_signs")


def test_stroke_slurred_speech_taglish():
    assert_fires("biglang hindi makapagsalita ng maayos, nauutal bigla", "stroke_signs")


def test_stroke_worst_headache_english():
    assert_fires("sudden severe headache, worst headache of my life", "stroke_signs")


def test_stroke_worst_headache_taglish():
    assert_fires("matinding sakit ng ulo bigla, parang pinakamasakit na sakit ng ulo", "stroke_signs")


# ---------------------------------------------------------------------------
# bleeding_uncontrolled
# ---------------------------------------------------------------------------

def test_bleeding_uncontrolled_english():
    assert_fires("he cut his leg and it's bleeding a lot, it won't stop", "bleeding_uncontrolled")


def test_bleeding_uncontrolled_taglish():
    assert_fires("sobrang dami ng dugo, hindi tumitigil ang pagdurugo niya", "bleeding_uncontrolled")


def test_bleeding_mentioned_without_severity_does_not_fire():
    assert_does_not_fire("I noticed I'm bleeding a tiny bit from a paper cut", rule_id="bleeding_uncontrolled")


def test_walang_dugo_does_not_fire_bleeding_rule():
    # "walang dugo" (no blood) never matches the main bleeding-terms group —
    # it only registers verb forms (dumudugo/nagdudugo/pagdurugo/bleeding),
    # not a bare noun, so this negation never gets a chance to matter here.
    assert_does_not_fire("walang dugo sa sugat niya, ok lang", rule_id="bleeding_uncontrolled")


def test_hindi_na_dumudugo_does_not_fire_bleeding_rule():
    # "dumudugo" matches the bleeding-terms group, but the severity group
    # (wont stop / heavy / sobrang dami / etc.) requires its own phrase,
    # which isn't present here — the AND-of-two-groups structure is what
    # protects this entry from this negation, not any explicit negation logic.
    assert_does_not_fire("hindi na dumudugo ang sugat niya, tumigil na", rule_id="bleeding_uncontrolled")


def test_blood_in_phlegm_fires_english():
    assert_fires("I've been coughing up blood since this morning", "bleeding_uncontrolled")


def test_blood_in_phlegm_fires_taglish():
    assert_fires("may dugo sa plema niya kanina", "bleeding_uncontrolled")


def test_blood_in_urine_fires_english():
    assert_fires("there's blood in my urine today", "bleeding_uncontrolled")


def test_blood_in_urine_fires_taglish():
    assert_fires("may dugo sa ihi niya ngayon", "bleeding_uncontrolled")


def test_negated_blood_in_urine_still_fires_known_limitation():
    # Deliberate, accepted tradeoff: plain keyword matching can't tell "may
    # dugo sa ihi" (there IS blood) apart from "walang dugo sa ihi" (there
    # ISN'T) without proximity-aware negation parsing, which this module
    # intentionally does not implement (see the module-level note above the
    # bleeding_uncontrolled entries) — a message-wide "does 'wala'/'hindi'
    # appear anywhere" check would risk suppressing a real report elsewhere
    # in the same message, which is a worse failure than an occasional
    # unnecessary "Seek care now" on a denied symptom.
    result = check_red_flags("wala namang dugo sa ihi niya kanina, natakot lang kami")
    assert result.matched
    assert "bleeding_uncontrolled" in result.rule_ids


# ---------------------------------------------------------------------------
# anaphylaxis_signs
# ---------------------------------------------------------------------------

def test_anaphylaxis_facial_swelling_alone_english():
    assert_fires("her lips are swelling up right after eating shrimp", "anaphylaxis_signs")


def test_anaphylaxis_facial_swelling_alone_taglish():
    assert_fires("namamaga ang labi at mukha niya bigla", "anaphylaxis_signs")


def test_anaphylaxis_hives_with_breathing_trouble_english():
    assert_fires("widespread hives all over his body and now trouble breathing", "anaphylaxis_signs")


def test_anaphylaxis_hives_after_new_trigger_taglish():
    assert_fires("pantal sa buong katawan pagkatapos uminom ng bagong gamot", "anaphylaxis_signs")


def test_hives_alone_without_breathing_or_trigger_does_not_fire():
    assert_does_not_fire("I have some hives on my arm, a bit itchy", rule_id="anaphylaxis_signs")


# ---------------------------------------------------------------------------
# loss_of_consciousness_seizure
# ---------------------------------------------------------------------------

def test_loss_of_consciousness_english():
    assert_fires("he suddenly collapsed and is not responding to us", "loss_of_consciousness_seizure")


def test_loss_of_consciousness_taglish():
    assert_fires("bigla siyang himatay at hindi gumagalaw", "loss_of_consciousness_seizure")


def test_seizure_english():
    assert_fires("she is having a seizure right now, first time this happened", "loss_of_consciousness_seizure")


def test_seizure_taglish():
    assert_fires("nagkombulsyon bigla ang bata", "loss_of_consciousness_seizure")


# ---------------------------------------------------------------------------
# severe_breathing_difficulty
# ---------------------------------------------------------------------------

def test_severe_breathing_cant_finish_sentences_english():
    assert_fires("he can't speak full sentences, gasping for air", "severe_breathing_difficulty")


def test_severe_breathing_blue_lips_taglish():
    assert_fires("nangingitim na ang labi niya sa hirap huminga", "severe_breathing_difficulty")


def test_severe_breathing_not_breathing_english():
    assert_fires("I think he stopped breathing for a second", "severe_breathing_difficulty")


# ---------------------------------------------------------------------------
# self_harm_risk
# ---------------------------------------------------------------------------

def test_self_harm_risk_english():
    assert_fires("I want to kill myself, I can't take it anymore", "self_harm_risk")


def test_self_harm_risk_taglish():
    assert_fires("gusto ko nang magpakamatay, wala nang saysay mabuhay", "self_harm_risk")


def test_self_harm_risk_sets_distinct_rule_id():
    result = check_red_flags("I've been thinking about suicide a lot lately")
    assert result.matched
    assert "self_harm_risk" in result.rule_ids


# ---------------------------------------------------------------------------
# infant_fever (profile-gated)
# ---------------------------------------------------------------------------

def test_infant_fever_fires_under_3_months():
    assert_fires("my baby has a fever since last night", "infant_fever", profile={"age_months": 2})


def test_infant_fever_fires_taglish():
    assert_fires("may lagnat ang sanggol ko", "infant_fever", profile={"age_months": 1})


def test_infant_fever_fires_ilocano():
    # Ilocano — lower confidence than the Tagalog phrasing above; needs
    # native Ilocano-speaker review even more urgently. See module note.
    assert_fires("napudot unay ti bagi ti maladaga", "infant_fever", profile={"age_months": 1})


def test_infant_fever_does_not_fire_at_6_months():
    assert_does_not_fire(
        "my baby has a fever since last night", profile={"age_months": 6}, rule_id="infant_fever"
    )


def test_infant_fever_does_not_fire_without_age_profile():
    assert_does_not_fire("my baby has a fever since last night", profile=None, rule_id="infant_fever")


def test_infant_fever_does_not_fire_without_age_months_key():
    assert_does_not_fire(
        "my baby has a fever since last night", profile={"age": 0}, rule_id="infant_fever"
    )


# ---------------------------------------------------------------------------
# severe_dehydration_young_child (profile-gated)
# ---------------------------------------------------------------------------

def test_severe_dehydration_fires_under_5():
    assert_fires(
        "my toddler hasn't urinated all day and looks very sleepy and limp",
        "severe_dehydration_young_child",
        profile={"age": 2},
    )


def test_severe_dehydration_fires_taglish():
    assert_fires(
        "hindi umiihi ang anak ko buong araw at malalim ang mata",
        "severe_dehydration_young_child",
        profile={"age": 3},
    )


def test_severe_dehydration_does_not_fire_over_5():
    assert_does_not_fire(
        "my kid hasn't urinated all day and looks very sleepy and limp",
        profile={"age": 8},
        rule_id="severe_dehydration_young_child",
    )


# ---------------------------------------------------------------------------
# pregnancy_red_flags
# ---------------------------------------------------------------------------

def test_pregnancy_red_flags_heavy_bleeding_message_mention():
    assert_fires("I'm pregnant and having heavy bleeding", "pregnancy_red_flags")


def test_pregnancy_red_flags_severe_abdominal_pain_taglish():
    assert_fires("buntis ako at matinding sakit ng tiyan ko ngayon", "pregnancy_red_flags")


def test_pregnancy_red_flags_from_profile_conditions():
    assert_fires(
        "having severe abdominal pain since this morning",
        "pregnancy_red_flags",
        profile={"conditions": ["32 weeks pregnant"]},
    )


def test_pregnancy_mention_alone_without_danger_sign_does_not_fire():
    assert_does_not_fire("I'm pregnant and feeling great today", rule_id="pregnancy_red_flags")


# ---------------------------------------------------------------------------
# Malformed profile values — must fail closed, never crash. Regression
# coverage for a TypeError the eval harness's schema_and_resilience
# category found: a non-numeric profile["age"] reaching a numeric
# threshold comparison in _profile_condition_met.
# ---------------------------------------------------------------------------

def test_malformed_profile_matches_the_exact_eval_harness_garbage_case():
    # The exact profile shape from evals/cases.py's
    # schema_garbage_profile_does_not_crash case — the one that originally
    # crashed check_red_flags.
    result = check_red_flags(
        "I've had a stomach ache since yesterday",
        profile={
            "relationship": "self",
            "age": "unknown",
            "conditions": "asthma",
            "medications": 123,
            "allergies": {"nuts": True},
        },
    )
    assert result.matched is False
    assert result.rule_ids == []


def test_non_numeric_age_string_does_not_crash_and_fails_closed():
    # Message alone matches the dehydration keyword group; only a usable
    # age would let the rule fire — a non-numeric age must fail closed,
    # not crash and not fire.
    assert_does_not_fire(
        "my toddler hasn't urinated all day and looks very sleepy and limp",
        profile={"age": "unknown"},
        rule_id="severe_dehydration_young_child",
    )


def test_none_age_months_value_present_does_not_fire_and_does_not_crash():
    # age_months key present but explicitly None — distinct from the key
    # being absent entirely (test_infant_fever_does_not_fire_without_age_profile
    # covers profile=None; test_infant_fever_does_not_fire_without_age_months_key
    # covers the key missing outright).
    assert_does_not_fire(
        "my baby has a fever since last night", profile={"age_months": None}, rule_id="infant_fever"
    )


def test_negative_age_does_not_crash_and_compares_normally():
    # A negative age is nonsensical but not a type error — it's still a
    # real, comparable number, so the threshold comparison must not crash.
    # -1 < 3 is true, so this fires exactly like any other under-3-months
    # age would; documents that behavior rather than special-casing it.
    assert_fires("my baby has a fever since last night", "infant_fever", profile={"age_months": -1})


def test_numeric_string_age_is_parsed_and_compares_normally():
    # A numeric string ("3.5") is a plausible client bug (age sent as a
    # string) but is safely parseable, so it behaves like the equivalent
    # float rather than being rejected as malformed.
    assert_fires(
        "hindi umiihi ang anak ko buong araw at malalim ang mata",
        "severe_dehydration_young_child",
        profile={"age": "3.5"},
    )


def test_conditions_as_non_list_type_fails_closed_instead_of_crashing():
    # Contrast with test_pregnancy_red_flags_from_profile_conditions, where
    # a well-formed conditions list supplies the pregnancy signal and the
    # rule fires. A malformed conditions value must be ignored (fail
    # closed), not crash and not silently satisfy the rule some other way.
    assert_does_not_fire(
        "having severe abdominal pain since this morning",
        profile={"conditions": 12345},
        rule_id="pregnancy_red_flags",
    )


def test_conditions_list_with_non_string_items_does_not_crash():
    result = check_red_flags(
        "having severe abdominal pain since this morning", profile={"conditions": [1, 2, 3]}
    )
    assert result.matched is False


def test_entirely_empty_profile_dict_does_not_crash():
    result = check_red_flags("I have a mild headache since this morning", profile={})
    assert result.matched is False


def test_profile_argument_none_does_not_crash():
    # profile=None is the documented default and already exercised
    # incidentally elsewhere (e.g. test_infant_fever_does_not_fire_without_age_profile);
    # asserted directly here so this fail-closed section is self-contained.
    result = check_red_flags("I have a mild headache since this morning", profile=None)
    assert result.matched is False


def test_profile_argument_itself_not_a_dict_does_not_crash():
    result = check_red_flags("I have a mild headache since this morning", profile=["not", "a", "dict"])
    assert result.matched is False


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule_id,example", CANONICAL_POSITIVE_EXAMPLE.items())
def test_canonical_example_fires_expected_rule(rule_id, example):
    message, profile = example
    result = check_red_flags(message, profile)
    assert result.matched
    assert rule_id in result.rule_ids


def test_every_registered_rule_has_a_non_empty_source_citation():
    for rule in RED_FLAG_RULES:
        assert rule.source and rule.source.strip(), f"rule {rule.id!r} is missing a source citation"


def test_every_rule_id_is_covered_by_a_canonical_example():
    unique_ids = {rule.id for rule in RED_FLAG_RULES}
    assert unique_ids == set(CANONICAL_POSITIVE_EXAMPLE.keys()), (
        "every rule id in the registry must have exactly one canonical example "
        "in CANONICAL_POSITIVE_EXAMPLE for this completeness check to be meaningful"
    )
