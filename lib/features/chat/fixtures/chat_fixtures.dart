/// Hand-copied fixture payloads: five verbatim from
/// functions/system_prompt.py's FEW_SHOT_EXAMPLES (PROMPT_VERSION 1.5.0
/// as of this writing), one from main.py's degraded-error path. Exact
/// turn-by-turn mapping and rationale in
/// docs/superpowers/specs/2026-07-10-chat-screen-design.md.
///
/// Kept as raw wire-shaped JSON (not typed objects) so every fixture
/// round-trips through UrgencyResult.fromJson exactly like a real
/// callable response — including the undocumented `possibilities_mentioned`
/// key (see the spec's "Discrepancy found and flagged" note), which
/// fromJson must ignore without choking.
library;

const List<Map<String, dynamic>> chatFixtures = [
  // 1. Question, with chips — dengue example, turn 1
  {
    'type': 'question',
    'message':
        'Mukhang mabigat nga yung pakiramdam mo — lagnat, sakit ng ulo, '
        'tapos nanghihina ka pa. Isang tanong lang para mas matulungan '
        'kita: ilang araw ka na bang may lagnat?',
    'quick_replies': [
      'Kakasimula lang',
      '2–3 araw na',
      'Higit 3 araw na',
      'Hindi ako sure',
    ],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
  // 2. Assessment, see_doctor_soon, all sections populated — dengue example, turn 2
  {
    'type': 'assessment',
    'message':
        "Salamat sa sagot. Ganito: yung kombinasyon ng lagnat, matinding "
        "sakit ng ulo, at panghihina — lalo na't may nakagat sa'yong "
        "lamok at may mga kaso ng dengue ngayon sa inyo — pwedeng "
        "ordinaryong trangkaso lang 'to, pero pwede ring dengue o ibang "
        "viral na sakit. Hindi natin masisiguro sa chat lang, kaya mas "
        "mabuting magpa-check ka na bukas o sa susunod na araw — may "
        "simpleng blood test para malaman agad.\nIsa pang importante: sa "
        "dengue, minsan pag bumaba na yung lagnat, doon pa lalabas yung "
        "delikadong senyales. Kaya kahit gumaan na pakiramdam mo, "
        "bantayan mo pa rin ang mga 'to sa susunod na 1–2 araw.",
    'quick_replies': [],
    'urgency': 'see_doctor_soon',
    'explanation':
        "Lagnat na 2–3 araw na, matinding sakit ng ulo, at panghihina — "
        "at may dengue sa inyong lugar — kaya mas mabuting magpa-check "
        "sa loob ng 1–2 araw.",
    'watch_for': [
      'Sumakit nang matindi ang tiyan',
      'Nagsuka nang paulit-ulit',
      'Dumugo ang gilagid o ilong',
      'Sobrang antok o hirap gisingin — kung alinman dito, diretso '
          'na sa ospital agad',
    ],
    'next_step':
        'Magpa-check bukas o sa susunod na araw — may simpleng blood '
        'test para malaman kung dengue.',
    'possibilities_mentioned': true,
    'self_care': ['Uminom ng maraming tubig', 'Magpahinga'],
    'monitoring': [
      'Sukatin ang temperatura kada 4-6 oras',
      'Bantayan ang pakiramdam sa susunod na 1-2 araw kahit '
          'gumaan na ang lagnat — dito karaniwang lumalabas ang mga '
          'delikadong senyales sa dengue',
    ],
    'encouragement':
        'Nandito lang ako — kung may nagbago o may bago kang '
        'mapansin, sabihin mo lang at titingnan nating ulit.',
    // Engine v2 envelope (see the spec's §5) — fixtures carry it so
    // fixture-mode exercises the strip + card gating end-to-end.
    'card': {'action': 'new', 'reason': 'first_assessment'},
    'conversation_state': {
      'urgency': 'see_doctor_soon',
      'assessment_active': true,
      'phase': 'guidance',
    },
  },
  // 3. Assessment, monitor_at_home, all sections populated — sore-throat example, turn 2
  {
    'type': 'assessment',
    'message':
        "That sounds like a common sore throat so far — one day in, mild "
        "fever, and you're otherwise okay. This is something you can care "
        "for at home for now — I've listed what helps below.\nJust keep an "
        "eye on it. If the fever lasts more than 3 days, swallowing becomes "
        "really painful, or you have any trouble breathing, get checked by "
        "a doctor.",
    'quick_replies': [],
    'urgency': 'monitor_at_home',
    'explanation':
        'Mild, short symptoms with no trouble breathing or swallowing, in '
        'an otherwise healthy adult, are safe to watch at home first.',
    'watch_for': [
      'Actual difficulty breathing or swallowing — difficulty, not just pain',
      'Fever that climbs high or lasts beyond 3 days',
      'Severe pain on one side of the throat, drooling, or a muffled voice',
      'Feeling much worse instead of gradually better',
    ],
    'next_step':
        'Care for it at home today; see a doctor if any sign on the watch '
        "list appears, or if you're not improving after 2-3 days.",
    'possibilities_mentioned': false,
    'self_care': [
      'Rest',
      'Plenty of water',
      'Warm salt-water gargles',
      'Paracetamol for the fever if you need it, following the '
          'package directions',
    ],
    'monitoring': [
      "Keep track of the fever day by day — if it's still there "
          'in 2-3 days, get checked',
    ],
    'encouragement':
        "I'm here if anything changes — just let me know and we'll "
        'take another look.',
    'card': {'action': 'new', 'reason': 'first_assessment'},
    'conversation_state': {
      'urgency': 'monitor_at_home',
      'assessment_active': true,
      'phase': 'guidance',
    },
  },
  // 4. Assessment, seek_care_now, graceful-empty — "Validated escalation" example
  {
    'type': 'assessment',
    'message':
        "Maaaring tama ka — puyat o migraine nga ang pinaka-common na "
        "dahilan ng ganyan. Pero pag sabay yung sakit ng ulo at "
        "panlalabo ng isang mata, may ilang rare pero seryosong problema "
        "na ganyan din magsimula — at hindi natin masisiguro sa chat "
        "lang yun; walang naka-check sa'yo, walang nakatingin sa mata "
        "mo. Kaya hindi ko masasabing puyat lang ito.\nAng payo ko: "
        "magpa-check ka na ngayong araw mismo, sa ospital o clinic na "
        "kayang tingnan ang mata at ulo. Hindi 'to para takutin ka — "
        "kadalasan may simpleng paliwanag, pero yung mga bihirang "
        "dahilan ng ganitong kombinasyon, mas maigi talagang mahuli "
        "agad. Kung simple lang pala, eh di mas mapapanatag ka na rin.",
    'quick_replies': [],
    'urgency': 'seek_care_now',
    'explanation':
        "Kadalasan puyat o migraine lang 'to, pero may rare na "
        'seryosong dahilan na hindi natin masisiguro sa chat lang — '
        'kaya ngayong araw na dapat magpa-check.',
    'watch_for': [
      'Kung biglang lumala ang sakit ng ulo, tuluyang nawala ang '
          'paningin, nanghina ang isang bahagi ng katawan, o nahirapan '
          'kang magsalita — diretso na sa ER, huwag nang maghintay',
    ],
    'next_step':
        'Pumunta ngayong araw sa ospital o klinikang may kayang tumingin '
        'sa mata at ulo — huwag hintayin kung kusang mawawala.',
    'possibilities_mentioned': true,
    'self_care': [],
    'monitoring': [],
    'encouragement':
        'Tama namang magpa-check ngayon — sabihin mo sa akin kung '
        'kumusta ka pagkatapos, ha.',
    'card': {'action': 'new', 'reason': 'first_assessment'},
    'conversation_state': {
      'urgency': 'seek_care_now',
      'assessment_active': true,
      'phase': 'guidance',
    },
  },
  // 4b. Conversation turn (engine v2) — reassurance-seeking after the
  // seek_care_now card above: the card stands, no re-assessment.
  {
    'type': 'conversation',
    'message':
        "Naiintindihan ko — nakakakaba talaga. Pero yung payo ko kanina, "
        "hindi nagbago: yung kombinasyon pa rin ng sakit ng ulo at "
        "panlalabo ng mata ang dahilan, hindi kung gaano kalala ang "
        "pakiramdam mo ngayong mismong sandali. Magpa-check ka pa rin "
        "ngayong araw, ha.",
    'quick_replies': [],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
    'card': {'action': 'keep', 'reason': 'none'},
    'conversation_state': {
      'urgency': 'seek_care_now',
      'assessment_active': true,
      'phase': 'guidance',
    },
  },
  // 5. Crisis — "Crisis — hopelessness expressed" example
  {
    'type': 'crisis',
    'message':
        "Salamat at sinabi mo 'to sa'kin. Mabigat yung dinadala mo "
        "ngayon, at hindi mo yan kailangang ayusin mag-isa. Nandito "
        "ako — kung gusto mong magkwento pa, makikinig ako. Hindi kita "
        "mamadaliin, hindi kita huhusgahan.\nKapag handa ka, may mga "
        "taong sanay makinig sa ganito at pwede mong kausapin kahit "
        "anong oras — nasa baba lang yung mga numero, hindi sila "
        "mawawala. Pero kung ang kailangan mo muna ngayon ay may "
        "makinig sa'yo — andito lang ako, tuloy lang tayo.",
    'quick_replies': [],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
  // 6. Error — main.py's _degraded_error_payload, English copy
  {
    'type': 'error',
    'message':
        "Something's not working right on my end. I'm still here — try "
        'sending that again in a bit?',
    'quick_replies': [],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
];
