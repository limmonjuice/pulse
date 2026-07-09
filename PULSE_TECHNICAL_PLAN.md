# Pulse — Technical Plan for the Launch Vision
### Zero-cost edition: every ring, engineered without a peso spent

*Companion to the Launch Vision doc. This translates each ring into stack decisions, build priorities, design tasks, and research questions — under one hard constraint: no paid services. No Infermedica, no paid APIs, nothing that breaks the ₱0 infrastructure bill. Where the "obvious" tool is a paid trap, the free alternative is named explicitly.*

---

## 0. The constraint, stated honestly

"Free" has three different shapes in this plan, and it's worth knowing which one you're standing on at all times:

1. **Free forever** — open-source packages, on-device capabilities, bundled assets. No ceiling.
2. **Free tier with a generous quota** — Gemini API, Firestore, Cloud Functions, FCM. Fine at student/early-launch scale; the Auto Stop Services extension is the fence around all of it.
3. **Free-looking but paid** — the traps. Google Places API, cloud speech-to-text APIs, Pinecone at scale, SMS anything. These are called out per ring below with their free replacements.

The standing architecture rule doesn't change: Flutter client → Callable Cloud Function (Python) → Gemini, with the deterministic red-flag layer in front. Every ring below extends that spine; nothing replaces it.

---

## 1. Stack decisions, ring by ring

### Ring 1 — Deepening the conversation

**Voice in Tagalog/Ilocano/Taglish — use the phone, not the cloud.**
The paid trap here is cloud speech-to-text (Google Cloud STT bills per 15 seconds). The free answer is on-device recognition: the `speech_to_text` package uses each platform's built-in recognizer at zero cost, and Android's recognizer supports Filipino (`fil-PH`). For voice *out*, `flutter_tts` uses the platform's TTS engines, also free. Two honest caveats to design around: on-device recognition quality for Ilocano specifically is unverified (research item R1), and Taglish code-switching will produce imperfect transcripts — which is fine, because Gemini is genuinely good at reading messy Taglish text. Architecture: transcribe on-device → send text to the function like any typed message. Voice never touches the backend as audio.

**Body map — pure Flutter, zero dependencies.**
A custom widget: the soft blob-style body illustration as an SVG/CustomPainter with tappable regions mapped to body areas. A tap seeds the conversation with structured context ("pain location: lower right abdomen"). No package needed beyond possibly `flutter_svg`. This is a design task more than an engineering one.

**Photo context — multimodal Gemini, no storage bill.**
Gemini's free tier accepts images natively, so the AI side costs nothing. The trap is on the *storage* side: Firebase Storage now requires the Blaze plan for new projects (you're on Blaze anyway, and it has a free daily quota) — but the smarter zero-cost, zero-liability move is to **not persist symptom photos at all**. Send the image bytes with the callable request, let Gemini use it as context, keep only the text conversation. No storage cost, and a meaningfully better privacy story ("Pulse never keeps photos of your body") — the constraint produces the better product decision here.

**Worry dial — free by definition.**
It's a system prompt behavior plus one chip row in the chat UI. The calibration ("scared" vs "just checking") travels as a field in the function payload and modulates the persona's tone instructions. Highest value-per-line-of-code feature in the entire vision.

### Ring 2 — The household, fully realized

**Family Pulse dashboard — Firestore streams, already paid for (₱0).**
Status rings are derived state: each profile's most recent episode and its urgency level, streamed from Firestore. No new services. The engineering work is a clean `episode` data model (see §3) so "active/monitoring/urgent-open" is a query, not a computation.

**Caregiver sharing — the hard free problem.**
No new service needed — it's all Firestore — but this is the most security-rule-intensive feature in the app: profiles referenced by multiple accounts, permission tiers (view / converse / manage), invitations. Firestore security rules can express this, but they get genuinely tricky, and a mistake here leaks a family's health data. This is research item R2 and deserves its own design doc before a line of code. Invitation flow without SMS (paid trap): share-link deep links via Firebase Dynamic Links' successor — note Dynamic Links is deprecated, so use plain App Links/Universal Links with a Firestore-backed invite token (free, no service dependency).

**Health story timeline — a data model, not a feature.**
The move from "chat log" to "episodes" is a Firestore schema decision (conversations grouped into episodes with an urgency arc and resolution state). Costs nothing; pays everywhere — dashboard rings, doctor kit, AI context. Do this schema work *early* (it's in Phase A below) even though the timeline UI ships later, because retrofitting episode structure onto loose chat logs is miserable.

**Trusted contact alert — FCM, not SMS.**
The trap: SMS costs money everywhere. The free path: the trusted contact must also have Pulse installed, and the alert is a push notification (FCM, free) with the summary. Honest limitation to accept: no-app fallback is a share-sheet action (user taps to send the summary via their own Messenger/SMS — their choice, their cost).

### Ring 3 — From guidance to action

**Doctor visit kit — on-device PDF.**
The `pdf` + `printing` Flutter packages generate and share PDFs entirely on-device. Zero backend, zero cost. The "questions to ask your doctor" section is one extra instruction in the summary-generation prompt — Gemini free tier again.

**Care finder — the biggest paid trap in the vision, and the best free swap.**
Google Places/Maps is not free at real usage (per-SKU monthly caps now, and a billing account risk you don't want attached to a free app). The free stack: **OpenStreetMap data + `flutter_map`** (OSM tiles, no API key) with hospitals/clinics/health centers pulled from OSM via Overpass API — Philippine OSM coverage of health facilities is decent and includes barangay health stations, which Google often misses anyway. Ship it as a *bundled, periodically refreshed dataset* for your target provinces (La Union first) rather than live API calls: faster, works offline, and immune to Overpass rate limits. Research item R3 covers verifying data quality for your region. Distance sorting is local math (`geolocator` package, free).

**After-visit follow-up + all scheduled check-ins — on-device scheduling first.**
The trap-shaped decision: server-side scheduled notifications need Cloud Scheduler + FCM orchestration (free tier exists — 3 Scheduler jobs — but it's fiddly). The simpler free answer for v1 of every follow-up feature: `flutter_local_notifications` scheduled on-device when the conversation ends ("check in at 7am"). No backend, works offline, survives everything except the user uninstalling. Move to server-side FCM scheduling only when caregiver-sharing makes cross-device follow-ups necessary (Phase C).

**Offline first-aid — bundled assets.**
Curated guides as structured JSON + illustrations shipped inside the app bundle. Zero infrastructure. The real work is editorial (research item R4: sourcing DOH/Philippine Red Cross–aligned content and getting a clinical sanity-check on it) and design (making them beautiful and calm), not engineering.

### Ring 4 — The companion between episodes

**Season sense — a content pipeline problem, solved cheap.**
There is no clean DOH API (research item R5 confirms/denies). The free v1: a *seasonal baseline calendar* (dengue season, heat index months, flu season — static, editorially maintained JSON in Firestore) + a manually-updated advisories collection you edit when something real happens (post-typhoon lepto warning). A scheduled Cloud Function (within the free 3-job Scheduler quota) can later poll DOH/PAGASA pages if a scrape-able source proves stable. Regional context rides into the AI as one line of the function payload.

**Chronic companions — Firestore + `fl_chart`.**
Logs are documents; trends are `fl_chart` line charts (free, pure Flutter). No wearables, no integrations — manual entry with a fast, kind UX is the honest v1.

**Medication rhythms — local notifications again.**
Same scheduling engine as follow-ups (shared service, built once in Phase B). Caregiver visibility ("Lola hasn't confirmed her dose") is a Firestore write on confirmation + a dashboard read — no new services.

### Ring 5 — Trust infrastructure

**RAG grounding without Pinecone.**
The free path that actually works at your corpus size: your grounding corpus (WHO fact sheets, DOH advisories, triage-protocol summaries) is *small* — hundreds of chunks, not millions. Embed it once with Gemini's embedding model (free tier), store vectors directly in **Firestore, which now has native vector search** (K-nearest-neighbor queries) — no separate vector DB at all. If Firestore vector search proves awkward at your scale, the fallback is even simpler: load all embeddings into the Cloud Function's memory at cold start (a few MB) and brute-force cosine similarity in NumPy — at hundreds of chunks this is milliseconds. Pinecone solves a scale problem you will not have. Research item R6.

**Triage engine — the no-Infermedica answer.**
Without a certified engine, the urgency decider remains the layered system you already designed: deterministic red flags (hard floor) → LLM assessment biased toward the worst reasonable explanation → RAG grounding to keep the reasoning tethered to real protocols. The honest upgrade path that stays free: *grow the deterministic layer.* Expand `red_flags.py` from a red-flag list into a rules table covering the most common symptom clusters (fever+child+duration, chest pain variants, pregnancy flags), sourced from published triage protocols (research item R7), each rule unit-tested. This is genuinely strong engineering for a portfolio — "I built a tested, rules-first triage floor with LLM assessment above it" is a better story than "I called an API."

**Privacy center — engineering, not services.**
Per-profile export (JSON via the same on-device share path as PDFs), per-profile delete (a Cloud Function that cascades deletes — write it early, deleting data properly is harder than storing it), and the plain-language "what Pulse knows" screen (a Firestore read, rendered kindly).

---

## 2. The consolidated free stack (delta from MVP)

| Capability | Tool | Cost shape |
|---|---|---|
| Voice in/out | `speech_to_text`, `flutter_tts` (on-device) | Free forever |
| Photo context | Gemini multimodal, no persistence | Free tier |
| Maps & care finder | `flutter_map` + OSM/Overpass bundled dataset + `geolocator` | Free forever |
| PDF export | `pdf` + `printing` | Free forever |
| Charts | `fl_chart` | Free forever |
| Notifications (local) | `flutter_local_notifications` | Free forever |
| Notifications (push, cross-device) | FCM | Free tier |
| Scheduled jobs | Cloud Scheduler (≤3 jobs) | Free tier |
| Vector search / RAG | Gemini embeddings + Firestore vector search (or in-function NumPy) | Free tier |
| Body map, blob illustrations | `flutter_svg` / CustomPainter | Free forever |
| Deep-link invites | App Links + Firestore invite tokens | Free forever |

**Explicitly rejected paid traps:** Google Places/Maps SDK, cloud STT/TTS APIs, Pinecone, SMS gateways, Firebase Dynamic Links (deprecated anyway), any telehealth API.

---

## 3. What to design (the design workstream, in order)

1. **Episode data model** — the schema decision underneath everything: conversations → episodes → resolution states, per profile. One page of schema design now saves three refactors later.
2. **Family Pulse home screen** — the status-ring dashboard. This is the launch identity screen; design it before building any Ring 2 code so the data model serves the UI.
3. **Urgency card v2** — same card, new powers: regional-context line ("dengue advisory in your area"), trusted-contact action on coral, "sources" affordance for RAG later. Design the card once to hold all of it, ship the powers incrementally.
4. **Elderly Mode** — type scale, pacing, voice-default, simplified chips. Design as a *mode of the existing screens*, not new screens (surface-area discipline still applies).
5. **Body map illustration set** — blob-language body figure, tappable regions, child/adult variants.
6. **First-aid guide template** — one beautiful, calm layout that all guides pour into.
7. **Privacy center** — "what Pulse knows about you," written in the app's voice.

## 4. What to research (numbered, so they're trackable)

- **R1:** On-device speech recognition quality for `fil-PH` and Ilocano on real budget Android devices — test with actual elderly speakers, not just your own voice.
- **R2:** Firestore security-rules architecture for multi-account shared profiles — write and *test* the rules in the emulator before designing the UI around them.
- **R3:** OSM health-facility data quality for La Union / Ilocos region — count facilities, verify against reality, plan a manual-correction layer.
- **R4:** Sourcing + clinical review path for first-aid content (DOH/PRC-aligned; find one nurse/med student/doctor willing to review).
- **R5:** Whether any DOH/PAGASA advisory source is reliably machine-readable, or season sense stays editorially maintained.
- **R6:** Firestore vector search ergonomics at small corpus scale vs. in-function brute force — spike both in an afternoon.
- **R7:** Published triage protocols usable as the source for the expanded rules table (e.g., WHO IMCI for pediatric fever, standard chest-pain/stroke protocols) — the deterministic layer should cite its sources internally.
- **R8:** Play Store health-app policy requirements (privacy policy URL, data-safety form, health-apps declaration) — cheap to research now, painful to discover at submission.

## 5. Project plan — phases, not dates

*MVP weeks 1–7 stay exactly as planned; this picks up after. Phases are gated on evidence from the previous one, per the funnel discipline.*

**Phase A — Foundations for the vision (immediately post-MVP, ~3 wks)**
Episode data model migration · doctor visit kit v1 (PDF export) · worry dial · Family Pulse dashboard v1 · R1, R2, R7 research spikes.
*Gate to proceed: real testers complete real conversations; ≥1 tester exports a summary or asks for a feature Ring 2 covers.*

**Phase B — Voice & household (~4 wks)**
Voice in/out with Taglish · Elderly Mode · shared scheduling service + after-visit follow-up (local notifications) · expanded `red_flags.py` rules table with tests · offline first-aid v1 (5 guides).
*Gate: voice actually works for an elderly tester (R1 result), household profiles show multi-member usage.*

**Phase C — Action & reach (~4 wks)**
Care finder (OSM bundled dataset, La Union) · caregiver sharing (R2 design → build) · trusted-contact FCM alert · season sense v1 (editorial calendar).
*Gate: coral-card episodes occur in real usage (care finder demand is proven, not assumed).*

**Phase D — Companion & trust (~4–5 wks)**
Chronic companions · medication rhythms · body map · photo context · RAG grounding (R6 path) · privacy center · R8 store-readiness.
*Gate: retained households using the app across multiple episodes — the only evidence that "between-episodes" features have an audience.*

---

## 6. Priorities, if everything competes for the same week

1. Episode data model (everything sits on it)
2. Doctor visit kit v1 (highest value-per-effort, proven demand pattern)
3. Worry dial (near-free, identity-defining)
4. Family Pulse dashboard (the launch screen)
5. Expanded deterministic rules table (the portfolio's strongest engineering story)
6. Voice/Taglish (highest real-world impact, gated on R1)
7. Everything else in phase order

*The quiet theme of this whole plan: at your scale, the free constraint almost never costs you the product — twice (photos not persisted, rules-first triage) it actually forces the better decision. The only place "free" genuinely hurts is certified triage, and the mitigation — a tested, protocol-sourced rules layer — is itself the best engineering artifact in the project.*