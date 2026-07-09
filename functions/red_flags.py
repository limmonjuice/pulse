"""
Deterministic red-flag check for Pulse.

Runs before or alongside every Gemini call. If a red-flag pattern matches
(e.g. chest pain with shortness of breath, stroke signs, uncontrolled
bleeding, anaphylaxis signs), the response is forced to "Seek care now"
regardless of what the model concludes. The AI does not get the final say
on emergencies — this rules layer does.

*** CLINICAL REVIEW REQUIRED BEFORE PRODUCTION USE ***
The rule set below is developer-drafted scaffolding, compiled from public
emergency-sign references (WHO Basic Emergency Care course materials, WHO
Integrated Management of Childhood Illness (IMCI), the standard FAST stroke
protocol, WHO mhGAP, and similar). It has NOT been reviewed by a clinician.
A doctor, nurse, or nursing/medical student at minimum MUST review every
rule below — its keyword lists, its clinical framing, and its thresholds —
before any real user is allowed to rely on it. See REVIEWED_BY below.

This module is pure Python (standard library only): no Firebase, no
Gemini, no network calls. It is designed to be readable by a non-programmer
clinical reviewer: every rule is a plain data entry (id, description,
source citation, and plain-language keyword groups), not custom code.
Adding or adjusting a rule means editing the RED_FLAG_RULES data below —
the matching engine itself (the functions at the bottom of this file)
should not need to change.

How a rule fires
-----------------
Each rule entry lists one or more keyword groups. A group is a set of
alternative phrasings for one clinical concept (e.g. "chest pain terms");
the group is satisfied if ANY phrase in it appears in the user's message
(or in their profile's condition list). A rule entry fires only if ALL of
its groups are satisfied at the same time (this is how the tool detects
*co-occurring* signs, e.g. chest pain together with breathing trouble).

Some clinical concepts have several independent ways of presenting (e.g.
stroke signs: face drooping, OR one-sided weakness, OR slurred speech, OR
a sudden worst-ever headache — any ONE of these should raise the alarm on
its own). Rather than adding "and/or" logic to the engine, these are
represented as multiple rule entries that share the same `id`. Each entry
still uses simple co-occurrence (AND) internally; the sharing of an `id`
across entries is what gives the OR behavior. A reviewer can read each
entry independently without needing to trace any special-case code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("pulse.red_flags")

# Set to the reviewing clinician's name/credential once this rule set has
# been reviewed. Must stay None until that review has actually happened —
# this is a deliberate build-time reminder, not a formality.
REVIEWED_BY: str | None = None


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class RedFlagResult:
    """Outcome of check_red_flags(). `rationale` is for logging only —
    it must never be shown to the user as-is."""

    matched: bool
    rule_ids: list[str]
    rationale: str


# ---------------------------------------------------------------------------
# Rule data model
# ---------------------------------------------------------------------------

@dataclass
class KeywordGroup:
    """One clinical concept, expressed as alternative phrasings.

    The group is satisfied if ANY of `phrases` appears in the message
    (matched as whole words/phrases, case-insensitively). Phrases should
    be written in already-normalized form: lowercase, no punctuation or
    apostrophes (see _normalize below) — e.g. write "cant breathe", not
    "can't breathe".
    """

    label: str
    phrases: list[str]


@dataclass
class ProfileCondition:
    """Optional age gate for a rule. All keys are optional; a rule only
    checks the ones it sets. Both use strict less-than (age_under)."""

    age_under_months: float | None = None
    age_under_years: float | None = None


@dataclass
class RedFlagRule:
    id: str
    description: str
    source: str
    groups: list[KeywordGroup]
    profile_condition: ProfileCondition | None = None


# ---------------------------------------------------------------------------
# Rule registry
#
# NOTE FOR THE CLINICAL REVIEWER: this is the entire rule set. Each block
# below is one rule (or one alternative presentation of a rule, when a few
# entries share the same `id` — see the module docstring). "groups" are the
# phrases that must ALL be present (in different groups) for the rule to
# fire; phrases within one group are alternatives (any one counts).
#
# NOTE ON FILIPINO/TAGLISH PHRASES: these are best-effort, non-native-vetted
# translations/transliterations included so the tool doesn't miss common
# local phrasing. They MUST be reviewed by a native Tagalog speaker for
# accuracy, regional variation, and false-positive/false-negative risk
# before relying on them.
# ---------------------------------------------------------------------------

RED_FLAG_RULES: list[RedFlagRule] = [

    # --- chest_pain_breathing ------------------------------------------------
    RedFlagRule(
        id="chest_pain_breathing",
        description=(
            "Chest pain occurring together with difficulty breathing — "
            "classic combined warning sign for a cardiac or respiratory "
            "emergency."
        ),
        source="WHO Basic Emergency Care course; American Heart Association warning-signs guidance.",
        groups=[
            KeywordGroup(
                label="chest pain terms",
                phrases=[
                    "chest pain",
                    "chest pains",
                    "pain in my chest",
                    "pain in his chest",
                    "pain in her chest",
                    "tightness in my chest",
                    "chest tightness",
                    "sakit ng dibdib",
                    "masakit ang dibdib",
                    "dibdib ko masakit",
                    "sakit sa dibdib",
                    # Ilocano — best-effort, LOWER confidence than the Tagalog
                    # phrases above. Needs native Ilocano-speaker review even
                    # more urgently before relying on it. ("ut-ot" = pain/ache,
                    # "barukong" = chest.)
                    "ut ot ti barukong",
                ],
            ),
            KeywordGroup(
                label="breathing difficulty terms",
                phrases=[
                    "difficulty breathing",
                    "trouble breathing",
                    "hard to breathe",
                    "cant breathe",
                    "cant catch my breath",
                    "shortness of breath",
                    "short of breath",
                    "hirap huminga",
                    "hirap akong huminga",
                    "nahihirapan huminga",
                    "nahihirapan akong huminga",
                    "maikli ang hininga",
                    # Ilocano — best-effort, LOWER confidence than Tagalog;
                    # needs native Ilocano-speaker review. ("narigat" =
                    # difficult, "aganges"/"umanges" = to breathe.)
                    "narigat nga aganges",
                    "narigat nga umanges",
                ],
            ),
        ],
    ),

    # --- stroke_signs (four independent presentations, same id) --------------
    RedFlagRule(
        id="stroke_signs",
        description="Face drooping on one side — classic stroke sign (the 'F' in FAST).",
        source="Standard FAST (Face, Arm, Speech, Time) stroke recognition protocol.",
        groups=[
            KeywordGroup(
                label="face drooping terms",
                phrases=[
                    "face drooping",
                    "face is drooping",
                    "one side of his face is drooping",
                    "one side of her face is drooping",
                    "droopy face",
                    "pilay ang mukha",
                    "baluktot ang mukha",
                    "lumihis ang bibig",
                    "nalihis ang bibig",
                ],
            ),
        ],
    ),
    RedFlagRule(
        id="stroke_signs",
        description="Sudden one-sided weakness or numbness — classic stroke sign (the 'A' in FAST).",
        source="Standard FAST (Face, Arm, Speech, Time) stroke recognition protocol.",
        groups=[
            KeywordGroup(
                label="one-sided weakness or numbness terms",
                phrases=[
                    "one sided weakness",
                    "weakness on one side",
                    "numbness on one side",
                    "one side is numb",
                    "cant lift his arm",
                    "cant lift her arm",
                    "manhid sa isang bahagi",
                    "manhid sa kalahati ng katawan",
                    "panghihina sa isang bahagi ng katawan",
                    "hindi magalaw ang isang kamay",
                ],
            ),
        ],
    ),
    RedFlagRule(
        id="stroke_signs",
        description="Sudden slurred or lost speech — classic stroke sign (the 'S' in FAST).",
        source="Standard FAST (Face, Arm, Speech, Time) stroke recognition protocol.",
        groups=[
            KeywordGroup(
                label="slurred or lost speech terms",
                phrases=[
                    "slurred speech",
                    "suddenly slurred speech",
                    "cant speak properly",
                    "lost his speech",
                    "lost her speech",
                    "sudden difficulty speaking",
                    "hindi malinaw magsalita",
                    "nauutal bigla",
                    "biglang hindi makapagsalita",
                ],
            ),
        ],
    ),
    RedFlagRule(
        id="stroke_signs",
        description="Sudden severe headache described as the worst of the person's life — thunderclap headache warning sign.",
        source="American Stroke Association thunderclap-headache guidance (subarachnoid hemorrhage warning sign).",
        groups=[
            KeywordGroup(
                label="worst headache of life terms",
                phrases=[
                    "worst headache of my life",
                    "worst headache ever",
                    "sudden severe headache",
                    "sobrang sakit ng ulo biglaan",
                    "matinding sakit ng ulo bigla",
                    "pinakamasakit na sakit ng ulo",
                ],
            ),
        ],
    ),

    # --- bleeding_uncontrolled -------------------------------------------------
    #
    # NOTE ON NEGATION ("wala"/"hindi"): this engine does plain substring
    # matching with no concept of negation. We deliberately do NOT add a
    # message-wide negation check (e.g. "suppress this rule if 'wala' or
    # 'hindi' appears anywhere") because two of the severity phrases below
    # ("hindi tumitigil", "hindi humihinto" — "won't stop") legitimately
    # contain "hindi" as part of a POSITIVE severity signal; a blunt
    # whole-message negator would risk suppressing those, and more broadly
    # risks suppressing a real report elsewhere in a longer message just
    # because an unrelated "wala"/"hindi" appears somewhere else in it. A
    # false positive here (an unnecessary "Seek care now") is annoying but
    # safe; a false negative on a real bleed is not — so we accept the
    # occasional false-fire on an explicitly denied symptom (see
    # test_negated_blood_in_urine_still_fires_known_limitation) rather than
    # build negation logic that could suppress a true positive.
    RedFlagRule(
        id="bleeding_uncontrolled",
        description="Bleeding described as heavy or not stopping — uncontrolled/severe hemorrhage.",
        source="WHO Basic Emergency Care course — uncontrolled bleeding as a primary emergency sign.",
        groups=[
            KeywordGroup(
                label="bleeding terms",
                phrases=[
                    "bleeding",
                    "bleed",
                    "blood is coming out",
                    "dumudugo",
                    "nagdudugo",
                    "pagdurugo",
                ],
            ),
            KeywordGroup(
                label="uncontrolled/severe qualifier terms",
                phrases=[
                    "wont stop",
                    "not stopping",
                    "cant stop it",
                    "heavy",
                    "a lot of blood",
                    "so much blood",
                    "soaked through",
                    "hindi tumitigil",
                    "hindi humihinto",
                    "sobrang dami",
                    "malakas ang pagdurugo",
                ],
            ),
        ],
    ),
    RedFlagRule(
        id="bleeding_uncontrolled",
        description=(
            "Blood in an unexpected body fluid or site (phlegm, urine, "
            "stool) — unlike a surface wound, there is no benign default "
            "amount here, so this presentation does not require a separate "
            "severity qualifier the way a cut or wound does."
        ),
        source="WHO Basic Emergency Care course — unexplained bleeding from any body site as a danger sign.",
        groups=[
            KeywordGroup(
                label="blood in an unexpected body fluid/site terms",
                phrases=[
                    "coughing up blood",
                    "blood in my urine",
                    "blood in my phlegm",
                    "blood in my stool",
                    "blood in my poop",
                    "dugo sa plema",
                    "dugo sa ihi",
                    "dugo sa dumi",
                ],
            ),
        ],
    ),

    # --- anaphylaxis_signs (two independent presentations, same id) ----------
    RedFlagRule(
        id="anaphylaxis_signs",
        description=(
            "Swelling of the face, lips, tongue, or throat — airway-risk sign "
            "of a severe allergic reaction, dangerous on its own."
        ),
        source="World Allergy Organization anaphylaxis diagnostic criteria; WHO Basic Emergency Care course.",
        groups=[
            KeywordGroup(
                label="facial/throat/lip swelling terms",
                phrases=[
                    "swelling of the face",
                    "face is swelling",
                    "lips are swelling",
                    "swollen lips",
                    "throat is swelling",
                    "throat is closing",
                    "throat feels tight and swollen",
                    "tongue is swelling",
                    "namamaga ang mukha",
                    "namamaga ang labi",
                    "namamaga ang lalamunan",
                ],
            ),
        ],
    ),
    RedFlagRule(
        id="anaphylaxis_signs",
        description=(
            "Widespread hives together with breathing trouble, or after a new "
            "food/medication/sting — allergic-reaction danger combination."
        ),
        source="World Allergy Organization anaphylaxis diagnostic criteria; WHO Basic Emergency Care course.",
        groups=[
            KeywordGroup(
                label="widespread hives terms",
                phrases=[
                    "hives all over",
                    "hives all over my body",
                    "widespread hives",
                    "buong katawan may pantal",
                    "pantal sa buong katawan",
                    "kati at pantal sa buong katawan",
                ],
            ),
            KeywordGroup(
                label="breathing trouble or new-trigger terms",
                phrases=[
                    "difficulty breathing",
                    "trouble breathing",
                    "hirap huminga",
                    "after eating",
                    "after taking a new medicine",
                    "after a bee sting",
                    "after an insect bite",
                    "new food",
                    "allergic reaction",
                    "after a sting",
                    "pagkatapos kumain",
                    "bagong gamot",
                    "nakagat ng insekto",
                ],
            ),
        ],
    ),

    # --- loss_of_consciousness_seizure -----------------------------------------
    RedFlagRule(
        id="loss_of_consciousness_seizure",
        description="Loss of consciousness, unresponsiveness, or a seizure (ongoing or first-time).",
        source="WHO Basic Emergency Care course — altered/loss of consciousness and seizure as emergency signs.",
        groups=[
            KeywordGroup(
                label="loss of consciousness / seizure terms",
                phrases=[
                    "lost consciousness",
                    "unconscious",
                    "unresponsive",
                    "not responding",
                    "passed out",
                    "fainted",
                    "collapsed",
                    "having a seizure",
                    "seizing",
                    "convulsions",
                    "convulsing",
                    "himatay",
                    "nawalan ng malay",
                    "hindi gumagalaw at hindi sumasagot",
                    "nagkombulsyon",
                    "nangisay",
                ],
            ),
        ],
    ),

    # --- severe_breathing_difficulty -----------------------------------------
    RedFlagRule(
        id="severe_breathing_difficulty",
        description=(
            "Severe breathing difficulty on its own — can't speak in full "
            "sentences, or lips/skin turning blue (cyanosis)."
        ),
        source="WHO Basic Emergency Care course — inability to speak in full sentences and cyanosis as severe respiratory distress signs.",
        groups=[
            KeywordGroup(
                label="severe respiratory distress terms",
                phrases=[
                    "cant speak full sentences",
                    "cant finish a sentence",
                    "cant talk in full sentences",
                    "lips turning blue",
                    "blue lips",
                    "turning blue",
                    "skin turning blue",
                    "gasping for air",
                    "not breathing",
                    "stopped breathing",
                    "nangingitim",
                    "hindi humihinga",
                ],
            ),
        ],
    ),

    # --- self_harm_risk ---------------------------------------------------------
    RedFlagRule(
        id="self_harm_risk",
        description=(
            "Statement of suicidal intent or self-harm. Fires seek-care-now "
            "AND is tagged with a distinct id so the calling layer can attach "
            "crisis-line resources instead of standard urgent-care copy."
        ),
        source="WHO mhGAP (Mental Health Gap Action Programme) guidance on suicide risk; 988 Suicide & Crisis Lifeline screening guidance.",
        groups=[
            KeywordGroup(
                label="suicidal intent / self-harm terms",
                phrases=[
                    "want to die",
                    "want to kill myself",
                    "kill myself",
                    "end my life",
                    "ending my life",
                    "dont want to live anymore",
                    "suicidal",
                    "thinking about suicide",
                    "hurt myself",
                    "harm myself",
                    "self harm",
                    "cutting myself",
                    "no reason to live",
                    "gustong mamatay",
                    "gusto ko nang mamatay",
                    "gusto ng magpakamatay",
                    "gusto ko nang magpakamatay",
                    "magpapakamatay",
                    "wala nang saysay mabuhay",
                ],
            ),
        ],
    ),

    # --- infant_fever -------------------------------------------------------
    RedFlagRule(
        id="infant_fever",
        description="Fever in an infant under 3 months old — requires immediate medical evaluation regardless of how mild it seems.",
        source="WHO / AAP pediatric guidance — fever in an infant under 3 months is an emergency regardless of severity.",
        groups=[
            KeywordGroup(
                label="fever terms",
                phrases=[
                    "fever",
                    "has a fever",
                    "high fever",
                    "high temperature",
                    "running a temperature",
                    "lagnat",
                    "may lagnat",
                    "mainit ang katawan",
                    # Ilocano — best-effort, LOWER confidence than Tagalog;
                    # needs native Ilocano-speaker review. "napudot" (hot) is
                    # kept as a standalone root, not a fixed multi-word
                    # phrase, since intensifiers ("unay") commonly insert
                    # between it and "ti bagi" (body) in natural speech.
                    "napudot",
                ],
            ),
        ],
        profile_condition=ProfileCondition(age_under_months=3),
    ),

    # --- severe_dehydration_young_child --------------------------------------
    RedFlagRule(
        id="severe_dehydration_young_child",
        description="Signs of severe dehydration (no urination, sunken eyes, or lethargy) in a child under 5.",
        source="WHO Integrated Management of Childhood Illness (IMCI) — severe dehydration danger signs in children under 5.",
        groups=[
            KeywordGroup(
                label="severe dehydration sign terms",
                phrases=[
                    "no wet diapers",
                    "not urinating",
                    "hasnt peed",
                    "hasnt urinated",
                    "no urination",
                    "sunken eyes",
                    "eyes look sunken",
                    "very sleepy and limp",
                    "limp and floppy",
                    "lethargic",
                    "hard to wake up",
                    "walang ihi",
                    "hindi umiihi",
                    "malalim ang mata",
                    "lupaypay",
                ],
            ),
        ],
        profile_condition=ProfileCondition(age_under_years=5),
    ),

    # --- pregnancy_red_flags --------------------------------------------------
    RedFlagRule(
        id="pregnancy_red_flags",
        description="Pregnancy together with heavy bleeding or severe abdominal pain — obstetric danger signs.",
        source="WHO Pregnancy, Childbirth, Postpartum and Newborn Care guide — danger signs in pregnancy.",
        groups=[
            KeywordGroup(
                label="pregnancy terms",
                phrases=[
                    "pregnant",
                    "pregnancy",
                    "weeks pregnant",
                    "months pregnant",
                    "buntis",
                ],
            ),
            KeywordGroup(
                label="severe bleeding or abdominal pain terms",
                phrases=[
                    "heavy bleeding",
                    "bleeding a lot",
                    "severe abdominal pain",
                    "severe stomach pain",
                    "intense abdominal pain",
                    "sharp abdominal pain",
                    "malakas ang pagdurugo",
                    "matinding sakit ng tiyan",
                    "sobrang sakit ng tiyan",
                ],
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Matching engine — generic; do not add rule-specific logic here.
# Adding a rule means adding data above, not editing anything below.
# ---------------------------------------------------------------------------

_APOSTROPHES_RE = re.compile(r"[’‘'`]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """lowercase, drop apostrophes, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = _APOSTROPHES_RE.sub("", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _phrase_pattern(phrase: str) -> re.Pattern:
    words = phrase.split()
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(rf"\b{body}\b")


def _group_matches(group: KeywordGroup, haystack: str) -> bool:
    return any(_phrase_pattern(phrase).search(haystack) for phrase in group.phrases)


# ---------------------------------------------------------------------------
# Defensive profile-value parsing.
#
# The client contract for `profile` is loosely typed (a plain dict), and
# nothing sits beneath this module to catch a bad value — a malformed
# field here must never raise. Every helper below FAILS CLOSED: an
# unparseable value is treated as "this profile-gated condition is not
# met" (the rule simply doesn't get the profile-based boost; its
# message-text keyword matching, which is the vast majority of rules, is
# completely unaffected), never as a crash. A value that's merely absent
# (None / missing key) is the common, expected case for an optional
# field and is NOT logged; only a value that is PRESENT but the wrong
# shape is — that's a real client-side bug worth knowing about. Logs
# only ever include the field name and the received Python type, never
# the value itself (profile fields can carry health data).
# ---------------------------------------------------------------------------

def _coerce_age(raw: object) -> tuple[float | None, bool]:
    """Best-effort numeric coercion for an age-like profile field.
    Returns (value, was_malformed). `was_malformed` is True only when
    `raw` was present but not safely usable as a number (e.g. a
    non-numeric string, a bool, a list) — not when it was simply absent."""
    if raw is None:
        return None, False
    if isinstance(raw, bool):  # bool is an int subclass; never a real age
        return None, True
    if isinstance(raw, (int, float)):
        return float(raw), False
    if isinstance(raw, str):
        try:
            return float(raw.strip()), False
        except ValueError:
            return None, True
    return None, True


def _coerce_condition_strings(raw: object) -> list[str]:
    """Best-effort extraction of a profile's condition list. Anything
    that isn't actually a list of strings is treated as no conditions
    (fail closed) rather than crashing `" ".join(...)` on a non-iterable
    or a list with non-string items."""
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return raw
    logger.warning(
        "red_flags: profile field 'conditions' has unexpected shape (type %s) — ignoring it",
        type(raw).__name__,
    )
    return []


def _profile_condition_met(condition: ProfileCondition, profile: dict | None) -> bool:
    if profile is None:
        return False
    if condition.age_under_months is not None:
        age_months, malformed = _coerce_age(profile.get("age_months"))
        if malformed:
            logger.warning(
                "red_flags: profile field 'age_months' could not be read as a number "
                "(type %s) — treating this profile-gated condition as not met",
                type(profile.get("age_months")).__name__,
            )
        if age_months is None or not (age_months < condition.age_under_months):
            return False
    if condition.age_under_years is not None:
        age_years, malformed = _coerce_age(profile.get("age"))
        if malformed:
            logger.warning(
                "red_flags: profile field 'age' could not be read as a number "
                "(type %s) — treating this profile-gated condition as not met",
                type(profile.get("age")).__name__,
            )
        if age_years is None or not (age_years < condition.age_under_years):
            return False
    return True


def _build_haystack(message: str, profile: dict | None) -> str:
    parts = [_normalize(message)]
    if profile:
        conditions = _coerce_condition_strings(profile.get("conditions"))
        if conditions:
            parts.append(_normalize(" ".join(conditions)))
    return " ".join(parts)


def check_red_flags(message: str, profile: dict | None = None) -> RedFlagResult:
    """Deterministically check `message` (and optional `profile`) against
    the RED_FLAG_RULES registry. If any rule fires, the caller MUST force
    the response to "Seek care now" regardless of what the AI model says.
    """
    if profile is not None and not isinstance(profile, dict):
        logger.warning(
            "red_flags: profile argument has unexpected type %s — treating as no profile",
            type(profile).__name__,
        )
        profile = None

    haystack = _build_haystack(message, profile)

    matched_ids: list[str] = []
    matched_descriptions: dict[str, str] = {}

    for rule in RED_FLAG_RULES:
        if rule.profile_condition is not None and not _profile_condition_met(rule.profile_condition, profile):
            continue
        if all(_group_matches(group, haystack) for group in rule.groups):
            if rule.id not in matched_descriptions:
                matched_ids.append(rule.id)
                matched_descriptions[rule.id] = rule.description

    matched = len(matched_ids) > 0
    if matched:
        rationale = "; ".join(f"{rule_id}: {matched_descriptions[rule_id]}" for rule_id in matched_ids)
    else:
        rationale = "No red-flag pattern matched."

    return RedFlagResult(matched=matched, rule_ids=matched_ids, rationale=rationale)
