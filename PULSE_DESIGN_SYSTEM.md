# Pulse — Design System

*AI health companion. Warm, calming, reassuring — a gentle companion checking in, not a clinical medical app. The interface should feel soft even when the user is worried or unwell.*

---

## 1. Design Principles

- **Comforting over clinical.** Rounded shapes, soft shadows, warm off-white surfaces. Never sterile white, red crosses, or hospital iconography.
- **Guidance, not diagnosis.** The product tells users *how seriously to take* something, never *what they have*. Copy and semantic colors are calibrated, never alarmist.
- **Easy when unwell.** Big touch targets, generous whitespace, high legibility — some users are elderly or reading while sick.
- **One consistent kit.** Buttons, cards, chat bubbles, and badges reuse the same styles across every screen.

---

## 2. Color

### Core palette
| Token | Hex | Use |
|---|---|---|
| `--bg-cream` | `#FBF7F0` | App background (warm off-white, never stark white) |
| `--surface` | `#FFFFFF` | Cards, bubbles, sheets |
| `--primary` | `#6FA8B5` | Brand teal — user bubbles, active accents, mic |
| `--primary-deep` | `#4E8A97` | Primary CTA buttons, send button |
| `--primary-ink` | `#3F7A86` | Teal text (labels, wordmark, active nav) |
| `--tint-teal` | `#EAF3F4` | Soft teal fill (invitation card, chips) |

### Text
| Token | Hex | Use |
|---|---|---|
| `--text` | `#33403F` | Primary headings & labels (warm near-black) |
| `--text-body` | `#5C6866` | Body copy |
| `--text-muted` | `#7C8887` / `#8B9694` | Secondary / meta text |
| `--text-faint` | `#A9B0AE` / `#A0AAA9` | Placeholders, timestamps, captions |
| `--nav-inactive` | `#ADB4B1` | Inactive nav icons/labels |
| `--label-eyebrow` | `#A69C82` | Uppercase section eyebrows (warm taupe) |

### Lines & borders
| Token | Hex | Use |
|---|---|---|
| `--divider` | `#F0E9DD` / `#F5EFE4` | Hairline dividers, card row separators |
| `--dashed` | `#CBBFA0` | "Add" placeholder borders |
| `--chip-border` | `#BBD7DD` | Quick-reply chip outline |

### Semantic urgency (muted, distinct, never siren-red)
| Level | Solid | Tint bg | Text | Meaning |
|---|---|---|---|---|
| **Monitor at home** | `#8FB89A` (sage) | `#EBF3ED` | `#4F7A5E` | Mild — care for at home |
| **See a doctor soon** | `#E8B04B` (honey) | `#FBF1DC` | `#B07E17` | Worth a visit in 24–48h, not urgent |
| **Seek care now** | `#E07856` (coral) | `#FBEAE3` | `#C85A38` | Best checked without delay |

> Rule: use the **solid** color for icon chips, dots, and buttons; the **tint** as a soft background; the **text** shade for the level's label/word. Never pair urgency solids with harsh reds.

### Avatar accents (low-chroma, one per person)
Teal `#6FA8B5` · Lavender `#B9A6D6` · Sage `#8FB89A` · Honey `#E8B04B` — white initial, `50%` radius.

---

## 3. Typography

Two families only.

- **Headings — Nunito** (friendly rounded sans): weights 600 / 700 / 800.
- **Body — Inter** (clean, legible): weights 400 / 500 / 600.

| Role | Font / weight | Size | Notes |
|---|---|---|---|
| Wordmark | Nunito 800 | 42px | Letter-spacing −0.5px |
| Screen title | Nunito 800 | 25px | e.g. "History", greeting |
| Card / section heading | Nunito 700–800 | 16–20px | |
| Bubble label ("Pulse") | Nunito 800 | 16px | |
| Section eyebrow | Nunito 700 | 12–13px | UPPERCASE, letter-spacing 0.5–0.6px, `--label-eyebrow` |
| Body copy | Inter 400 | 14–15.5px | line-height 1.5–1.65 |
| Chat bubble | Inter 400 | 14.5px | line-height 1.5 |
| Meta / timestamp | Inter 500–600 | 11.5–13px | `--text-muted` / `--text-faint` |
| Nav label | Nunito 600 (700 active) | 10px | |
| Button label | Nunito 700 | 15–17px | |

Minimum body size on mobile: **12px**. Prefer 14px+ for anything a user reads while unwell.

---

## 4. Shape, Elevation & Spacing

### Radii
| Element | Radius |
|---|---|
| Phone frame | 46px |
| CTA button | 20px (in-card buttons 15–16px) |
| Cards / sheets | 20–28px |
| Chat bubble | 22px, with the "tail" corner tightened to 8px (bottom-right for user, bottom-left for Pulse) |
| Pills / chips / badges | 999px |
| Icon chips | 14–16px |
| Nav bar top | 26px |

### Shadows (soft, cool-gray, never harsh black)
| Token | Value |
|---|---|
| Card (resting) | `0 8px 22px rgba(80,100,100,.08)` |
| Card (raised) | `0 10px 26px rgba(111,168,181,.16)` |
| Urgency card (elevated) | `0 16px 36px rgba(80,100,100,.18)` |
| CTA button | `0 12px 26px rgba(78,138,151,.38)` |
| Phone frame | `0 24px 60px rgba(60,80,80,.22)` |
| Nav bar (top edge) | `0 -6px 20px rgba(80,100,100,.06)` |

### Spacing & layout
- Screen padding: **24px** horizontal.
- Card padding: **16–22px**.
- Section rhythm: ~20–26px between blocks; 8–14px gaps within groups.
- **Use flex/grid with `gap`** for any row/group of elements.
- Touch targets: **minimum 44px** (nav items, buttons, avatars all ≥44px).
- Reference frame: **390 × 844** (iOS), 46px corners, 46px status bar.

---

## 5. Components

**Primary button** — full-width, height 58px (48–50px inside cards), radius 20px, `--primary-deep` fill, white Nunito 700, CTA shadow. Urgency-card CTA uses that level's **solid** color.

**Card** — white, radius 20–28px, resting shadow, 16–22px padding.

**List row** — inside a white card; icon chip (34–44px, tinted) + title (Nunito 700, 15px) + meta (Inter, 12px) + chevron (`#C3CBC9`, 2.4 stroke). Rows in a group share a `--divider` hairline.

**Chat bubbles**
- *Pulse (assistant):* white surface, radius `22 22 22 8`, resting shadow, `--text` body.
- *User:* `--primary` fill, white text, radius `22 22 8 22`, teal shadow, right-aligned, max-width ~78%.

**Quick-reply chips** — pill, Nunito 700 13px. Unselected: white fill, `--chip-border` outline, `--primary-ink` text. Selected: `--primary` fill, white text. Kept on a single non-wrapping row above the input.

**Input bar** — white pill, radius 22px, placeholder in `--text-faint`; mic icon (`--primary` stroke) + circular send button (42px, `--primary-deep`, white up-arrow).

**Invitation input (Home)** — large soft-teal gradient card (`#EAF3F4 → #DCEBED`), companion blob + Nunito 800 prompt, nested white pill with mic. Feels like an invitation, not a form.

**Urgency Tag Card** (flagship) — elevated white card. Row: solid-color icon chip (44px, level glyph in white) + level label in level **text** color (Nunito 800, 18px) + "PULSE GUIDANCE" eyebrow. Then plain-language explanation → `--divider` → "What to do next" line → full-width CTA in level solid color. Icons: check (monitor) · clock (soon) · exclamation (now).

**Urgency badge (History)** — 10px colored dot (level solid) + level word in level text color.

**Bottom nav** — white, top radius 26px, top-edge shadow, 84px tall, 5 items (Home · Chat · History · Family · Settings). Active = `--primary-ink`, Nunito 700; inactive = `--nav-inactive`, Nunito 600. Line icons, 24px, 2px round stroke.

**Toggle** — pill 46×27px; ON = `--primary` with knob right, OFF = `#E4DDD0` with knob left; white 21px knob.

**Avatar** — circle, level/accent fill, white Nunito 800 initial. Active state adds a teal ring (`box-shadow: 0 0 0 3px #FBF7F0, 0 0 0 6px #6FA8B5`).

---

## 6. Iconography & Illustration

- **Line icons:** 24px, `stroke-width 2`, round caps/joins, `currentColor`. Friendly, minimal.
- **No clinical imagery** — no stethoscopes, red crosses, pill bottles, hospital marks.
- **Companion motif:** soft organic blob(s) with an off-center `border-radius` (e.g. `46% 54% 58% 42% / 52% 46% 54% 48%`), teal gradient (`#8FC3CD → #6FA8B5`), optional dot eyes + a curved smile and blush. Abstract, gentle — the app's mascot.
- Illustrations should feel hand-soft: layered blobs, no sharp corners.

---

## 7. Voice & Tone

- Warm, first-person, calm: "I'm right here — tell me what's going on."
- Plain language, no jargon; acknowledge feelings ("I'm sorry you're feeling rough").
- Always frame results as **urgency guidance**, and keep the disclaimer reachable: *"Guidance on urgency — not a diagnosis."*
- Reassure, don't alarm — even the "Seek care now" copy is about *timing*, not fear.

---

## 8. Chat-screen extensions (added 2026-07-10)

Tokens added to `app_theme.dart` while implementing the Chat screen —
values pulled from the approved `Pulse Chat.dc.html` mockup that weren't
yet covered by the sections above. Added here so the doc stays the
source of truth rather than drifting behind the code.

### Radii
| Token | Value | Justification |
|---|---|---|
| `AppRadii.crisisCard` | 28px | Crisis card is deliberately more spacious than the standard 24px assessment/urgency card — part of its "teal-tint, no tier machinery" distinct treatment. |
| `AppRadii.cardRowRadius` | 14px | Self-care checklist rows and monitoring rows inside the assessment card. |
| `AppRadii.pillRowRadius` | 13px | "Get care if…" (watch-for) warning pills inside the assessment card. |
| `AppRadii.inputBar` | 22px | The message input bar's own fixed radius (§5 says "radius 22px" explicitly, not the generic 999px pill token — the input bar can grow to 4 lines, where a true stadium and a fixed 22px corner look different). Numerically equal to `chatBubble` but kept separate — different component, coincidental match. Found during Task 16 code review. |

### Colors
| Token | Hex | Justification |
|---|---|---|
| `AppColors.crisisHeading` | `#2F4A4F` | Crisis card's opening line ("I'm really glad you told me") — darker than any existing text token, unique to the crisis card. |
| `AppColors.crisisBody` | `#3F5559` | Crisis card body copy, and the softer teal-tint Pulse bubble used for subsequent messages once a conversation is crisis-locked. |
| `AppColors.crisisFooterText` | `#7C9296` | Crisis card's closing reassurance line — distinct from (slightly cooler than) `--text-muted`. |
| `AppColors.selfCareRowBg` | `#F8F5EE` | Self-care checklist row background inside the assessment card. Found while implementing Task 14 — missed in the original Task 4 pass. |
| `AppColors.selfCareChecked` | `#8FB89A` | Checked-off self-care row's check-icon background. Numerically equal to `UrgencyColors.monitorAtHome.solid` (sage) but kept as its own token — a "done" state, not an urgency read; the mockup happens to reuse the same green. |
| `AppColors.selfCareUncheckedBorder` | `#CFD9D1` | Unchecked self-care row's checkbox border. |
| `AppColors.selfCareCheckedText` | `#9BA6A2` | Checked-off self-care row's strikethrough text color. |
| `AppColors.companionGradientLight` | `#8FC3CD` | Lighter stop of the companion-blob gradient (§6: "teal gradient #8FC3CD → #6FA8B5"); `--primary` is the darker stop. Found while implementing Task 15 (crisis card blob); also used by Task 17's chat header avatar. |

### Type
| Style | Font / weight | Size | Notes |
|---|---|---|---|
| `cardEyebrow` (implemented as `textTheme.labelMedium`) | Inter 600 | 10.5px | The "PULSE GUIDANCE" meta-label on the assessment card. Distinct from the Section 3 "Section eyebrow" style (Nunito 700, 12-13px, `--label-eyebrow`) — this is a smaller, Inter-based card meta-label, not a section header. Uppercase, letter-spacing 0.6px, `--text-faint`. |
| `cardSectionHeading` (implemented as `textTheme.titleSmall`) | Nunito 700 | 13.5px | In-card group headers ("Things you can do today", "Check in on yourself", "Get care if…"). Falls between the existing 15px (`titleMedium`) and 12.5px (`labelSmall`/eyebrow) slots, so needed its own entry rather than reusing either. `--text` color. |

Note: `titleSmall` is also Material's default for `TabBar`/`DataTable` heading
styles — if either is added later, give it its own explicit theme override
rather than relying on this default.

### Shadows
| Token | Value | Justification |
|---|---|---|
| Crisis card shadow | `0 12px 30px rgba(111,168,181,.18)` | Close to but distinct from the existing "Card (raised)" shadow (`0 10px 26px rgba(111,168,181,.16)`) — kept as its own token rather than reusing, since the two didn't match exactly in the mockup.
| `AppShadows.userBubble` | `0 6px 16px rgba(111,168,181,.28)` | User chat-bubble shadow — found while implementing (not in the original spec pass). Color is exactly `--primary` at 28% opacity, distinct enough from every existing teal shadow to warrant its own token. |

Pulse (assistant) bubble shadow (`0 6px 16px rgba(80,100,100,.08)`) reuses the
existing "Card (resting)" shadow rather than adding a third token — same
color/opacity, blur/offset close enough (16/6 vs. 22/8) not to duplicate.
