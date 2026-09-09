# AgenticVisualizer — Classroom Extensions PRD
### *Build spec for an 8-session course with eight 9-year-olds*

**Audience:** the developer taking this on. **This document states outcomes and acceptance tests, not implementation.** Where a constraint is stated as a mechanism, it's because the classroom forces it — those are marked **[hard constraint]**. Everything else is yours to solve.

---

## 1. What this is for

AgenticVisualizer already runs multi-agent negotiations for a classroom: students fill in profile forms, those become agent system prompts, the instructor loads a scenario and runs the negotiation on a projected screen.

This build adapts it for a specific, real course: **eight nine-year-olds plan a real party**, each represented by an agent they wrote. The tool is the course's central mechanism, used in six of eight sessions. It is not a demo — decisions made on this screen result in a real booking, a real menu order, and a real event.

**The one-sentence product goal:**
> A nine-year-old, watching a projected screen for two minutes, can tell what their agent wants, how that differs from everyone else's, what was decided — and afterwards, why.

That last word is doing the most work. "Why" is where the current build has nothing, and it's requirement group C.

---

## 2. The classroom facts that drive everything

Every requirement below traces to one of these. If a design decision conflicts with one of these, the design decision loses.

| # | Fact | Consequence |
|---|---|---|
| **F1** | **No student devices. Ever.** One instructor laptop, one projector. | No student-facing UI at all. The `/form` page is unused. All input arrives via the instructor. **[hard constraint]** |
| **F2** | Students are 9 years old and ESL (fluent, international school — but not native). | Nobody flash-reads three sentences. Text is a last resort; position, movement and colour are the primary channel. |
| **F3** | Eight agents, all participating every round. | A cycle is 8 outputs. It must be legible and paceable, not a wall of prose. |
| **F4** | It runs live, in a room, with a class losing interest. | The instructor controls pace absolutely. No waiting on token generation in front of the room. |
| **F5** | Each agent represents a specific child who is sitting there watching. | Every output must be traceable to the child who caused it. Anonymous agents would defeat the course. |
| **F6** | Outcomes are real — a real booking, a real food order. | Data must persist correctly across 8 weeks and be exportable to a human-sendable form. |
| **F7** | Sessions are 2 hours with 10-minute breaks; the instructor enters all data. | Bulk instructor data entry must be fast enough for 8 students in under 10 minutes. |

---

## 3. Outcomes

These are the tests. If the build satisfies these, the implementation is correct regardless of how it's done.

### For the child

- **O1** — I can find *my* agent on screen in under two seconds, without reading.
- **O2** — I can see what my agent currently wants, and how that differs from the others, without reading a paragraph.
- **O3** — I can see my agent change its mind, as it happens.
- **O4** — After a decision, I can be shown exactly what my agent did and said, in order, and understand it.
- **O5** — I can see what my agent ordered for me, and *why it says it chose that*.
- **O6** — I can see how my agent's instructions changed from week 1 to week 8, and point at what I fixed.

### For the instructor

- **O7** — I control when each agent speaks. Nothing appears until I press a key.
- **O8** — I can set up a scenario's options, rules and constraints before class, and load it in under a minute.
- **O9** — I can deliberately break one thing (a rule, a constraint, a data source, an agent's profile) in seconds, run it, and restore it.
- **O10** — I can replay a finished round filtered to one child's agent.
- **O11** — I can record, in two clicks, how each child reacted to an outcome and what the replay found.
- **O12** — I can enter or update all eight profiles in under ten minutes.
- **O13** — I can see, across all eight weeks, how each child's agent accuracy and reaction pattern changed.

### For the system

- **O14** — Every child's rendered profile is snapshotted at the end of every session, permanently.
- **O15** — A locked food order exports as an itemised, human-readable message that can be sent to a café.
- **O16** — A public, static URL per child shows their current agent brief and its version history.

---

## 4. The two session modes

⚠️ **These are different screens with different flows. Do not build one screen that tries to serve both.**

### Mode A — Negotiation round *(Decisions 2 and 4: date/venue, run of show)*

Agents argue over a **fixed, enumerable set of 3–6 named options** and converge (or fail to). Conflict between agents is the point.

### Mode B — Order round *(Decision 3: food)*

Eight agents independently read the **same menu** and each produce a **tray** — one item per slot (main / side / drink) — with a short reason per pick. **No conflict, no convergence, no referee arbitration.** Each output is independently right or wrong *for its own owner*, and the owner judges it.

Mode B reuses profiles, avatars, snapshots and the spatial layout. It does not reuse the turn loop, the referee's consensus logic, or the reaction layer.

---

## 5. Requirements

Priority is **by the session that needs it**. `S2` means the course cannot run session 2 without it.

---

### Group A — Legibility *(needed by S2)*

The current build outputs conversational prose. Eight paragraphs of English is unreadable to this cohort in the time available. This group is the difference between the tool working and not.

**A1 · Structured stance output** `S2` `P0`
Each agent turn produces a small structured object rather than free prose:
- a **stance** from a **fixed, closed vocabulary** — suggested: `WANT` · `OK WITH` · `WON'T` · `TRADE`
- the **option** it applies to (must be one of the declared options)
- a **reason**, hard-capped at ~8 words
- *(optional)* the fuller prose, hidden behind a click

**[hard constraint]** The stance vocabulary is fixed and small. It is curriculum, not UI garnish — the class learns these four words as concepts. Do not let the model invent stances.

*Acceptance:* an 8-agent cycle is fully readable in under 45 seconds, read aloud, by a child.

**A2 · The board** `S2` `P0`
A persistent spatial view: the declared options laid across the screen; each agent's avatar positioned under the option it currently backs; **avatars visibly move** when an agent changes stance.

*Acceptance:* a child who reads nothing can correctly say which option is winning, and whether their agent is with the majority.

**[hard constraint]** This forces a rule on scenario design: **every negotiation package declares 3–6 named options.** Combinatorial or open-ended option spaces cannot be boarded and are out of scope. If a decision can't be enumerated, the instructor splits it into sequential rounds. Build to assume enumerated options.

**A3 · Avatars are the child's own artwork** `S2` `P0`
Each student has an image asset (drawn by them in session 1, digitised by the instructor) used as their agent's avatar everywhere — board, stance card, tray, replay, printed card.

*Acceptance:* O1. Also: the same asset renders acceptably at ~48px (board) and at print resolution (card face). Instructor uploads it; no generation needed.

**A4 · Reaction layer** `S2` `P1`
Agents *not* currently speaking display a one-token reaction to the current turn (👍 / 😐 / 👎). Derived rather than separately generated is fine and preferred.

*Acceptance:* every one of the eight children has something of theirs visibly responding on every turn.

**A5 · Instructor-paced reveal** `S2` `P0`
A full cycle is generated in the background, then revealed **one agent per keypress**. Nothing appears unattended.

*Acceptance:* O7. No visible token streaming during a paced round; zero dead air waiting on the model. (The existing step-by-step mode may already substantially cover this — verify and extend rather than rebuild.)

*Rhythm note, for context:* keypress → card appears and avatar moves → **the child reads their own agent's line aloud** → next keypress. The 8-word cap exists partly to make that readable aloud by a 9-year-old.

---

### Group B — Data in *(needed by S5)*

**B1 · Fast bulk profile entry** `S3` `P0`
The instructor enters and updates all eight profiles himself, in a 10-minute break, every week.

*Acceptance:* O12 — eight students' worth of field updates entered in under ten minutes by one person. Optimise for keyboard flow across students; avoid per-student page loads and modal round-trips.

**[hard constraint]** No student login flow is used. Do not invest in `/form`.

**B2 · Availability data** `S5` `P0`
A per-person availability table (people × candidate dates, values yes/no/maybe) loadable into a scenario, and **checkable by the referee** — the referee must verify a proposed date against the table rather than trusting the agents.

*Acceptance:* the referee blocks a date that violates the declared attendance threshold, and — critically — **names which specific people a proposed date excludes.**

*Why the naming matters:* the class writes a fairness rule ("at least N can attend"). The rule is only teachable if the excluded person is named out loud, because that's what forces the rule to be written honestly, and it's what triggers the consolation they designed in advance.

**B3 · Venue search** `S5` `P1`
Run a live location search (Naver API; instructor has keys and existing tooling), return results as candidate option cards with the fields the class will filter on: distance, capacity, price, private room, age suitability.

*Acceptance:*
- the query is **pinned and configurable**, and results are **cacheable** — a cached run must be loadable and presentable as a fallback if the live call fails mid-class;
- returns **8–12 results** including at least two that obviously fail the class's criteria. *(Tuning this is the instructor's pretest job, not the developer's — but the parameters must be exposed.)*

*Design note:* results are **not** the decision. The class filters them by hand down to 3–4 survivors, which the instructor then declares as the negotiation options.

**B4 · Menu data** `S6` `P0`
A structured menu — items, slots (main/side/drink), prices — loadable into a Mode B scenario.

*Acceptance:* an agent cannot order an item not on the menu; a tray total is computed against real prices.

---

### Group C — The trace *(needed by S5 — this is the pedagogical core)*

⚠️ **The most important group in this document, and the one with no equivalent in the current build.** Every contested session ends with a child saying "I didn't like that," and the entire course depends on being able to answer "why" in front of them.

**C1 · Single-agent replay** `S5` `P0`
Filter a completed round to **one agent's contributions, in sequence**, with enough surrounding context to make each one intelligible.

*Acceptance:* O4, O10. The instructor selects a child, and walks the class through what that child's agent did across the round, in order, in under two minutes.

**C2 · Trace logging** `S5` `P0`
Per child, per round, record:
- **reaction** — liked / didn't like (the paddle vote)
- **cause**, if traced — one of exactly three: `agent behaviour` · `profile gap` · `rule effect`
- **note** — one free-text line

*Acceptance:* O11 — two clicks per child. And O13 — the cause distribution is viewable across all eight weeks.

*Why these three categories and no others:* they are the three levers the course teaches — your instrument, your specification, the system's rules. The **shift in the mix over eight weeks is the course's measured learning curve**: early rounds should trace mostly to `profile gap` ("it didn't know"), later ones to `agent behaviour` and then `rule effect` ("our rules did that"). Do not let this become a free-tagging system; three fixed values.

**C3 · Referee cites rules by number** `S4` `P0`
Rules carry stable indices. Referee warnings and blocks reference the index (`⚠️ Rule 2`) rather than restating the rule in prose.

*Acceptance:* a child can match an on-screen warning to a numbered card on the classroom wall in under three seconds.

---

### Group D — Persistence and artifacts *(needed by S8)*

**D1 · Session-end profile snapshots** `S2` `P0`
Every student's **rendered** profile is snapshotted, timestamped and retained at the end of every session. Never overwritten.

**[hard constraint]** Non-negotiable and needed from session 2, even though nothing consumes it until session 8. If snapshots don't start in week 2, the entire final presentation is impossible and cannot be reconstructed.

**D2 · Public agent page** `S8` `P0`
A stable, public, static URL per child (NFC-tappable) showing:
- their agent's current brief, presented legibly;
- a **version timeline** across all snapshots;
- a **diff view** highlighting what changed between versions.

*Acceptance:* O6, O16. A child taps a physical card and can point at what they changed. No login. Must survive the course ending — this is the artifact they keep.

*Context:* this is the durable deliverable the whole course is sold on, and the diff view is the evidence behind the child's showcase sentence *"here's where my agent got me wrong, and here's what I fixed."*

**D3 · Order export** `S6` `P1`
Compile locked trays into an itemised, human-readable order (per person, per slot, with totals) plus a mealtime window, formatted as a message an adult can send to a café.

*Acceptance:* O15 — copy-paste-and-send with no editing required beyond a greeting.

**D4 · Order accuracy** `S6` `P1`
Per child, per slot, record whether the agent's pick matched what the child says they'd have ordered. 8 children × 3 slots = 24 checkable picks.

*Acceptance:* an accuracy figure per child per run, comparable across runs. This is the course's one crisp quantitative outcome — it should visibly improve after the profile tune-up, and it is what gets shown to parents.

---

### Group E — Mode B: the order round *(needed by S6)*

**E1 · Independent tray production** `S6` `P0`
Eight agents each read the same menu and produce one item per slot, each with a short reason. No inter-agent turn loop.

**E2 · Spatial presentation, reusing Group A vocabulary** `S6` `P1`
Menu items laid out; each avatar moves to the items it's selecting; each agent presents a completed **tray** for its owner's review.

*Acceptance:* O5. A child sees their own tray, with their own avatar, and can immediately say whether it's right.

**E3 · Per-tray validation** `S6` `P1`
Slot limits enforced (one per slot); item existence enforced; budget cap flagged when breached.

*Acceptance:* the "five ice creams" failure is prevented when the guardrail is on, and visibly occurs when the instructor turns it off (see F1).

---

### Group F — Deliberate failure *(needed by S4)*

Breaking things on purpose is a teaching method used in almost every session, not an edge case. It should be a **first-class, fast, reversible action**, not a config-file edit.

**F1 · One-click break/restore** `S4` `P0`
Toggle off, in seconds, without editing text: an individual rule · a package constraint · a data source (menu, prices, availability) · an individual agent's profile fields.

*Acceptance:* O9 — the instructor breaks one thing, runs, discusses, restores, and re-runs, inside a 40-minute block, without leaving the session screen.

**F2 · Profile swap** `S6` `P1`
Silently swap two students' profiles between their avatars, run, then reveal.

*Acceptance:* the trays come back with the wrong food under the right names, and the swap is reversible in one action.

*Purpose:* this is a specific planned demo ("wrong owner") — it teaches that the agent is a written artifact, not a mind-reader, and it works best when the class discovers the swap themselves.

**F3 · Agent argumentativeness controls** `S4` `P1`
Exposed, per-rule-set levers for making agents hold positions rather than immediately accommodating: concession limits ("give up at most one want"), banned hedging vocabulary, minimum turns before compromise, opening simultaneous proposals, and a separately configurable (smaller/blunter) agent model.

*Acceptance:* a scenario with genuine conflict produces at least two full cycles before convergence, rather than converging on turn one.

⚠️ **Known hard problem.** Current instruction-tuned models will not argue on request; getting real disagreement is an open engineering task requiring test time. Structural pressure (scarcity in the option set, countable concession budgets) works better than tone instructions. Budget for iteration here — a negotiation where everyone instantly agrees teaches nothing and is the single largest risk to the course.

---

## 6. Non-goals

Stated explicitly to prevent scope creep.

- **No student-facing UI.** No student logins, no student devices, no `/form` investment. *(F1)*
- **No autonomous booking, ordering, payment or sending.** The system drafts; a human sends. Always.
- **No open-ended option spaces.** If it can't be enumerated as 3–6 options, it isn't a negotiation this tool runs.
- **No grading, scoring of children, or leaderboards.** Accuracy (D4) is a child's private feedback on their own agent, never a ranking.
- **No mobile app.** Projector and instructor laptop only.
- **No multi-class scale-out** beyond what the current class-tag system already provides.
- **No live translation or Korean V/O.** English is deliberate.
- **Not a general-purpose debate platform.** Every ambiguity should be resolved toward this course.

---

## 7. Acceptance walkthroughs

Two end-to-end scenarios. If both run cleanly, the build is done.

### Walkthrough 1 — Session 5, the venue round

1. Before class: instructor loads the availability table, runs the pinned venue search, caches results.
2. In class: search runs live, ~10 results shown. Class filters by hand to 4. Instructor declares those 4 as the round's options.
3. Instructor loads the package. Eight agents assemble from current profiles.
4. Round begins. First cycle streams. Instructor switches to paced reveal.
5. Each keypress: one stance card appears, one avatar moves, non-speaking agents react. **The child whose agent spoke reads the line aloud.**
6. Referee evaluates each cycle, citing rules by number. It blocks a proposed date and names the two children it excludes.
7. Consensus reached. Board shows the final distribution.
8. **Paddles up: "do you like this?"** Two reds.
9. Instructor opens **replay filtered to one red child's agent**, walks the four turns with the class. The class concludes the agent conceded too early.
10. Instructor logs: reaction `red`, cause `agent behaviour`, note.
11. Class ratifies the outcome. Date and venue lock.
12. End of session: all eight profiles snapshotted.

### Walkthrough 2 — Session 6, the order round

1. Menu loaded with real items, slots and prices.
2. Mode B runs: eight trays produced, each with per-item reasons.
3. Trays presented one at a time; each child sees their own avatar and tray.
4. Each child judges: is this what I'd have ordered? Logged per slot → accuracy figure.
5. Instructor runs the **profile swap** demo, re-runs, reveals, restores.
6. Children revise profile fields on paper; instructor enters all eight during the break; re-run.
7. Accuracy compared before/after.
8. Trays lock. **Order exported** as a sendable itemised message.
9. Snapshots taken.

---

## 8. Suggested build order

Driven by session deadlines, and by what is unrecoverable if missed.

| Order | What | Why here |
|---|---|---|
| **1** | **D1 snapshots** | Trivial, and **unrecoverable if late** — must be live before session 2 or session 8 is impossible |
| **2** | **A1 · A2 · A3 · A5** (legibility core) | Needed by S2; without these the tool is unusable for this cohort |
| **3** | **F3 argumentativeness** | Long lead, empirical, high risk — start iterating early even though it's needed at S4 |
| **4** | **C1 · C2 · C3** (the trace) | Needed by S5; the pedagogical core |
| **5** | **B2 availability · F1 break/restore** | S4–S5 |
| **6** | **B3 venue search** | S5, but degrades gracefully to a cached run |
| **7** | **E1–E3 · B4 · D4** (Mode B) | S6 |
| **8** | **D2 public page + diff** | S8; can land as late as week 7 |
| **9** | **A4 reactions · D3 export · F2 swap** | Enhancements; the course survives their absence |

---

## 9. Open questions for the developer

1. **Reactions (A4):** derived from stance, or a separate call? Derived is cheaper and more predictable; recommend derived unless it looks obviously wrong on screen.
2. **Stance vocabulary:** are four values enough for a real negotiation, or is a fifth needed? Prefer the smallest set that works — this is curriculum.
3. **Board layout at 8 avatars:** does it stay legible at 6 options × 8 avatars on a projector, or does the option count need a lower cap?
4. **Does the referee already produce enough structure** to derive C2's cause categories automatically, or is that purely instructor-entered? Instructor-entered is acceptable and probably better.
5. **Snapshot granularity:** per session is the requirement; is per-change cheap enough to do instead, giving a richer diff view?
6. **Mode B and the referee:** does Mode B need the referee at all, or only validation (E3)? Suspect the latter.
