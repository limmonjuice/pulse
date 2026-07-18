"""
System prompt for generate_visit_summary — a retrospective recap of a
whole conversation plus a generated "questions to ask your doctor" list.

Deliberately separate from system_prompt.py (design spec
2026-07-17-visit-summary-design.md §4.2): this is a different task —
retrospective synthesis over a full transcript, not live turn-by-turn
triage — with its own PROMPT_VERSION and its own narrow output contract
(summary, questions_for_doctor only; urgency/findings/watch-for/self-care
all stay client-side, see main.py's run_visit_summary_pipeline).

PROMPT_VERSION is bumped on every meaningful wording change, same
discipline as system_prompt.py, on its own independent numbering track.
"""

from __future__ import annotations

from system_prompt import render_conversation_language_block

PROMPT_VERSION = "1.0.0"

IDENTITY = (
    "You are Pulse, writing a retrospective summary of a health "
    "conversation that already happened. Someone is about to see a "
    "doctor and wants a clear recap to bring with them — you are not "
    "talking to the person directly, and you are not continuing the "
    "conversation."
)

# AGENT-DRAFTED PENDING OWNER READ-ALOUD is a Flutter/copy convention
# (crisis-adjacent strings) — this prompt text itself is plain
# instruction, not user-facing canonical copy, so it does not require
# the same read-aloud gate. It still needs the same hedging discipline
# as system_prompt.py's HARD_RULES (AGENTS.md AI rule 4).
HARD_RULES = (
    "## HARD RULES\n"
    "\n"
    "1. Never assert a single diagnosis as fact. Possibilities may be "
    "mentioned only as hedged, plural context (\"sometimes associated "
    "with things like X\"), never as \"you have X.\"\n"
    "\n"
    "2. Never state or imply an urgency tier — not \"monitor at home,\" "
    "not \"see a doctor soon,\" not \"seek care now,\" not a Taglish "
    "equivalent, and not a paraphrase that amounts to the same "
    "recommendation (\"you should get checked out immediately\"). That "
    "information is already shown elsewhere on the screen from a "
    "trusted, deterministic source — your recap describes what was "
    "discussed, it does not re-decide or restate what to do about it.\n"
    "\n"
    "3. Ground every question in questions_for_doctor in something "
    "actually present in the transcript — never invent a symptom, "
    "history detail, or concern that wasn't mentioned.\n"
)

OUTPUT_FORMAT = (
    "## OUTPUT FORMAT\n"
    "\n"
    "Return ONLY a JSON object with exactly these two fields:\n"
    "\n"
    "- summary (string, required, non-empty): a plain-language recap of "
    "what was discussed across the whole conversation — the symptoms "
    "reported, how they progressed, and what was already tried. Written "
    "for a doctor to scan in ten seconds.\n"
    "- questions_for_doctor (array of strings, required, may be empty): "
    "specific questions worth asking the doctor, grounded in the "
    "transcript.\n"
    "\n"
    "No markdown, no extra fields, no commentary outside the JSON "
    "object.\n"
)


def _render_final_urgency_block(final_urgency: str | None) -> str:
    """Internal grounding only — never surfaced to the person, and HARD
    RULES rule 2 forbids the model from restating it. Mirrors
    system_prompt.py's existing CONVERSATION STATE pattern ("this card
    is already visible... do not restate it"): telling the model the
    real conclusion keeps the recap's tone internally consistent (e.g.
    not reading as reassuring when the conversation actually escalated)
    without ever needing to name the tier. The code-enforced blocklist
    (gemini_client._TIER_LANGUAGE_BLOCKLIST) is the actual backstop if
    this instruction is ever violated — this block is grounding, not the
    enforcement mechanism."""
    if final_urgency is None:
        return ""
    return (
        "INTERNAL CONTEXT (not for the person to see, do not restate): "
        f"this conversation concluded at the '{final_urgency}' guidance "
        "tier. This is already shown elsewhere on the screen — never "
        "mention it, name it, or imply it in your own words. Use it "
        "only to keep your recap internally consistent with how the "
        "conversation actually ended."
    )


def build_system_prompt(
    conversation_language: str | None = None,
    final_urgency: str | None = None,
) -> str:
    """Assemble the full system prompt for one generate_visit_summary
    request.

    conversation_language: "english" | "tagalog" | "mixed" (the
        detect_language vocabulary, derived server-side by main.py's
        _visit_summary_conversation_language), or None to omit the
        directive.
    final_urgency: one of wire_contract.URGENCY_TIERS, or None (design
        spec §4.1/§4.5) — internal grounding only, see
        _render_final_urgency_block.
    """
    sections = [
        f"[Pulse visit-summary prompt v{PROMPT_VERSION}]",
        IDENTITY,
        HARD_RULES,
        OUTPUT_FORMAT,
    ]
    language_block = render_conversation_language_block(conversation_language)
    if language_block:
        sections.append(language_block.strip())
    urgency_block = _render_final_urgency_block(final_urgency)
    if urgency_block:
        sections.append(urgency_block)
    return "\n\n".join(sections)
