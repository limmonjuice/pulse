# Pulse — Launch Vision
### The full app: what Pulse becomes when it's grown

*This is the dream document — the complete picture of Pulse at public launch, not the MVP spec. The MVP (six screens, core loop, household profiles) remains the build target. Everything here is arranged in rings around that core, in the order it earns its way in. Nothing in this document changes the founding rule: Pulse guides urgency, it never diagnoses.*

---

## North Star

Baymax works as an inspiration for one specific reason: he is calm, personal, and present *before, during, and after* the moment of worry — not just a lookup tool you consult and close. Most health apps are either a search box wearing a nurse costume, or a data dashboard for people who are already healthy and organized. Pulse's identity at launch is different:

**Pulse is the health companion for the whole household — the calm first move when something feels wrong, the memory of what happened last time, and the gentle follow-through afterward.**

Three words carry the whole product: **calm, household, follow-through.** Every feature below serves at least one of them.

---

## The Launch Experience — a walkthrough

It's 9pm. Maya's 9-year-old son Leo feels hot and complains his head hurts. Maya opens Pulse, taps Leo's avatar, and says out loud — in Taglish, because that's how she actually talks — "May lagnat siya, sumasakit ulo niya since kanina." Pulse already knows Leo is 9, has no chronic conditions, and had a fever conversation eight months ago. It asks two questions, one at a time, with tappable chips because Maya is holding a thermometer in her other hand. Thirty seconds in, she has her answer: honey-amber card, *See a doctor soon* — with a plain-language explanation of why, what to watch for tonight, and one line she didn't expect: "Dengue cases are elevated in your area this month — if he develops stomach pain or any bleeding, that changes things. I'll check in with you at 7am."

At 7am, Pulse asks how Leo's night went. Worse — the fever's still high and now his stomach hurts. The card turns coral: *Seek care now.* One tap shows the three nearest open clinics and hospitals, with a prepared visit summary already generated: Leo's profile, the symptom timeline across both conversations, his medications, in a format a triage nurse can scan in ten seconds. Maya shows her phone at the desk instead of re-explaining everything from memory while worried.

Two days later, Leo's fine. Pulse logs the episode quietly into his health story, where it becomes context the next time anything happens. No streaks. No badges. No guilt for not opening the app when everyone's healthy.

That's the launch bar: every feature below exists to make that story work.

---

## Ring 0 — The Core (already designed; stays sacred)

The symptom conversation with urgency tagging, the deterministic red-flag safety net, household profiles, history, and the context-aware follow-up. Everything in this document is built *around* this loop. Any feature that competes with it, dilutes it, or gives the AI more diagnostic authority gets cut, no matter how impressive it demos.

---

## Ring 1 — Deepening the conversation

**Speak like home.** Full voice-first conversations in Tagalog, Ilocano, and Taglish — not just English with a mic button. This is the single most inclusive feature Pulse can ship in the Philippine context: the person most likely to need symptom guidance (an elderly parent, a grandparent in the province) is the least likely to type medical English into a chat box. Voice in, voice out, with the same calm tone. Elderly Mode makes this explicit: larger type, slower pacing, voice-by-default, and simplified chips.

**Show me where.** A soft, non-clinical body map — the same friendly blob language as the mascot, not an anatomy chart — for the moments words fail. "Point to where it hurts" is how humans already talk to children and how many people prefer to describe pain. A tap on the body seeds the conversation; it never replaces it.

**One photo is worth a paragraph.** Optional photo attachment for *visible* symptoms — rashes, swelling, a wound, a mosquito bite site. The model treats it as context for better questions ("is it raised or flat?"), never as a diagnostic scan. Guardrail: Pulse never rates a photo as "looks fine" — visible-symptom conversations bias one step more cautious, not less.

**The worry dial.** A quiet UX idea that fits the companion identity: at the start of a conversation, Pulse gently gauges how worried the person is ("scared," "just checking"), and calibrates tone — not conclusions — accordingly. A frightened user gets more reassurance-structure; a casual checker gets brevity. Same medicine, different bedside manner. This is the most Baymax feature in the app and costs almost nothing to build.

---

## Ring 2 — The household, fully realized

**The Family Pulse.** The Home screen grows into a gentle household dashboard: each family member's avatar with a subtle status ring — quiet gray-green for "nothing active," honey for "monitoring something," coral if an urgent flag is open. One glance answers "is everyone okay?" This is the screen that makes Pulse a *family* app rather than a personal one, and it's the natural heart of the launch UI.

**Caregiver sharing.** A profile can be shared across accounts — Maya and her sister both see Lola's profile, both get the follow-up check-ins, either can run a conversation on her behalf. OFW families are the sharpest version of the use case: a nurse in Dubai helping manage her mother's health in La Union through a shared profile. Permissions stay simple and explicit: view, converse, or manage.

**The health story.** Each profile's history matures from a chat log into a timeline: episodes, not messages. Fever episode in March, rash in June, the asthma flare last week — each with its urgency arc (did it escalate? resolve?). The AI reads this as context ("his third headache episode this month — worth mentioning that pattern to a doctor"), and it becomes the backbone of the doctor summary.

**Trusted contacts on the coral card.** When a conversation lands on *Seek care now*, one optional tap notifies a designated family member with the summary — because the moment someone actually needs the ER is the moment they shouldn't be composing a text message. Never automatic; always the user's tap.

---

## Ring 3 — From guidance to action

**The doctor visit kit.** The summary export, grown up: symptom timeline, profile context, medications, and — the underrated half — *questions worth asking the doctor*, generated from the conversation ("Ask whether the rash pattern suggests an allergy given the penicillin history"). Shareable as a clean PDF or shown on-screen at triage. This feature is where "companion" stops being a metaphor: Pulse walks you to the door of real care and hands you off well.

**Care finder.** The nearby-hospitals feature, scoped honestly: open-now clinics, health centers, and ERs, sorted by distance, filtered by what the urgency level actually calls for (a sage-green situation never pushes an ER). In the Philippine context, including barangay health stations and RHUs — not just private hospitals — is what makes this genuinely useful rather than a Google Maps embed.

**After the visit.** A tiny feature with outsized emotional weight: after a *See a doctor soon* or *Seek care now* episode, Pulse asks once — "were you able to get seen? how did it go?" — and logs the resolution into the health story. It closes the loop, teaches the system what its guidance led to, and it's exactly what a caring companion would ask.

**Pocket first-aid, offline.** A small, curated, DOH/Red Cross-aligned set of first-aid guides (burns, choking, wound care, fever in children, animal bites) bundled into the app and available with zero connectivity. Brownouts and weak signal are real; the moment you need "what do I do right now" guidance is precisely the moment the network fails you. This also makes the coral card useful even offline.

---

## Ring 4 — The companion between episodes

*The discipline here: Pulse never manufactures engagement. Every proactive touch is either clinically motivated or locally, genuinely informative.*

**Season sense.** A quiet, regional awareness layer: dengue season advisories, leptospirosis warnings after flooding, heat-index cautions in April, flu-season notes — sourced from DOH and local health advisories, localized to the user's province. Surfaced as one calm card on Home, never a push-notification barrage. This is also context the AI uses silently: "fever + rainy season + your area's advisory" legitimately changes what clarifying questions matter.

**Chronic companions.** Opt-in tracking spaces for the household's ongoing realities — Lola's blood pressure, Leo's asthma, a diabetic uncle's checkup rhythm. Simple logs, gentle trend views, and one genuinely valuable output: trends feed the doctor visit kit, so the cardiologist sees three months of BP readings instead of "mataas daw po minsan." No gamification; the reward is a better doctor visit.

**Medication rhythms.** The reminder engine, arriving in its proper place at last — per-profile schedules, caregiver visibility ("Lola hasn't confirmed her evening dose"), refill nudges. Built only at this ring because by now the medication *data* has been living in profiles since MVP, and real usage has shown whether people maintain it.

**The wellness check.** Once a season — not daily, not weekly — Pulse checks in on each profile like a family friend would: "It's been a while since Lola's last checkup — due for one?" Prompted by real intervals (annual checkups, dental, vaccinations for kids), sourced from the profile's age and history. This is the anti-streak: presence without pestering.

---

## Ring 5 — Trust infrastructure (invisible, non-negotiable)

**Grounded answers.** The RAG layer (the Pinecone idea, matured): Pulse's guidance grounded in a curated corpus — WHO fact sheets, DOH advisories, established triage protocols — with a subtle "sources" affordance on urgency cards. This upgrades trust from "the model says" to "here's where this comes from."

**A real triage engine under the hood.** If/when Infermedica (or equivalent) access lands, it replaces the LLM as the urgency *decider*, with the LLM staying in its lane: conversation, empathy, translation, explanation. The architecture was designed for exactly this swap from day one.

**Privacy as a feature, not a page.** Health data encrypted, exportable, deletable per-profile; a plain-language "what Pulse knows about you" screen written the way the app talks; explicit consent for anything shared across accounts. In a family app, "who can see what" isn't legal fine print — it's UI.

**The honesty line, everywhere.** Every surface keeps the founding sentence one glance away: *guidance on urgency, not a diagnosis.* At launch scale this stops being a disclaimer and becomes brand voice — the reason people trust the coral card when it matters.

---

## What stays out — even at launch

The vision needs walls as much as rooms. These are excluded on identity grounds, not resource grounds: **no diagnosis, ever** (no "top 3 conditions" lists, no confidence percentages); **no engagement mechanics** (streaks, badges, daily nags — a health companion that guilt-trips is a contradiction); **no social feed or community forum** (moderating strangers' medical advice is a different, dangerous product); **no ads, and no selling attention or data** (a companion that monetizes your worry isn't a companion); **no telehealth marketplace** at launch (partner-dependent, regulatory-heavy — a possible future chapter, not this one).

---

## The shape of the road

- **MVP (weeks 1–7):** Ring 0. Already planned, already scoped. Nothing above touches it.
- **v1.x (fast-follows):** Doctor visit kit v1 (summary export), Family Pulse home screen, worry dial, Elderly Mode basics.
- **v2:** Voice-first Tagalog/Ilocano, care finder, offline first-aid, caregiver sharing, season sense.
- **v3:** Chronic companions, medication rhythms, health story timeline, body map, photo context.
- **Launch-grade:** RAG grounding, triage-engine swap, privacy center, after-visit loop — the trust ring completes the picture.

The sequencing logic is the same funnel discipline the MVP came from: each ring must prove the previous one is actually used. The household ring only matters if the core loop retains people; the action ring only matters if urgency guidance is trusted; the between-episodes ring only matters if families are real, active units in the app.

---

*One paragraph to end on, because it's the whole point: Baymax was never compelling because he had features. He was compelling because he noticed, remembered, followed up, and never made it about himself. Every ring above is just that sentence, translated into software.*