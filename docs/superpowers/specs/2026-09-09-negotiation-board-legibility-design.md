# Negotiation board legibility (PRD Group A: A1, A2, A3, A5)

**Status:** approved for planning
**Source:** [agenticvisualizer-prd.md](../../../agenticvisualizer-prd.md), Group A (§5) — sub-project #2 of the PRD's suggested build order (§8)
**Depends on:** nothing (first substantive sub-project; D1 snapshots is smaller/independent and can land before or after)
**Feeds into:** Group C (trace/replay) will read the stance data this introduces; Group E (Mode B) will reuse the avatar/board vocabulary but not the option-wedge layout as-is

## 1. Problem

The current negotiation screen (free-form circular avatars + prose speech bubbles, `static/app.js` / `static/index.html`) is illegible to a classroom of 9-year-old ESL students in the time available: 8 paragraphs of English per cycle cannot be read aloud or skimmed in 45 seconds, and there's no spatial signal for "who wants what" or "what's winning" without reading. Group A is the minimum UI/data change that makes the tool usable for this cohort — everything else in the PRD depends on this being solid first.

## 2. Scope

In scope: A1 (structured stance output), A2 (the board), A3 (avatars as uploaded artwork), A5 (instructor-paced reveal, extended to drive the board).

Explicitly out of scope for this sub-project (per the PRD's own build order): A4 (reaction layer — bundled with later enhancements), Mode B / Group E (order round — different screen entirely), Group B/C/D/F requirements. Mentioned here only where this design needs to leave room for them.

## 3. Design

### 3.1 Board mode is per-package, opt-in

`PackageDB` gains a new field:

```python
options: str = "[]"  # JSON array: [{"id": str, "label": str}], 3-6 entries when set
```

If a package declares `options`, its loaded session runs in **board mode**: perimeter-room layout, structured stances, image avatars, board-driven paced reveal. If `options` is empty (every package that predates this feature, and any package for a class that isn't running this course), the session behaves exactly as it does today — free-form circular room, prose replies, emoji avatars. No separate toggle is needed; declaring options *is* opting in, and it enforces the PRD's own hard constraint that board packages must enumerate 3-6 options (validated server-side on package save when `options` is non-empty: reject fewer than 3 or more than 6).

`Session` (in-memory model) gains matching fields: `options: List[Option] = []` and a per-agent stance map `stances: Dict[str, AgentStance] = {}` (keyed by agent id), where:

```python
class Option(BaseModel):
    id: str
    label: str

class AgentStance(BaseModel):
    stance: Literal["want", "ok_with", "wont"]
    option_id: str
    reason: str  # capped ~8 words server-side
    full_text: str
```

`stances` starts empty (every agent begins in the undecided zone) and is updated in place each time an agent speaks in a board-mode round — it is not appended to a list; the board always reflects each agent's *current* (most recent) stance, per A2's "avatars visibly move when an agent changes stance."

### 3.2 A1 — structured stance output

Extends the existing `POINT: [reason] | [full reply]` convention (`agent.py:17-20`, parsed at `agent.py:104-109`) rather than switching to JSON-mode or tool-calling. That convention already works reliably against cheap models in production, and this app explicitly supports arbitrary OpenAI-compatible endpoints including local Ollama models (`README.md:383-386`) — tagged-line parsing degrades far better across model quality than strict schema enforcement would.

When a session is in board mode, `Agent._build_system_prompt` swaps in a new output-format instruction (replacing `_POINT_INSTRUCTION`) that requires exactly:

```
STANCE: WANT | OK WITH | WON'T
OPTION: <one of the declared option labels, verbatim>
REASON: <max 8 words>
FULL: <1-2 sentence prose, unchanged from today>
```

The stance vocabulary is fixed at three values: `WANT`, `OK WITH`, `WON'T` (the PRD's suggested fourth value, `TRADE`, is dropped for this pass — conditional/trade offers are the hardest concept and can be layered in later once the simpler three are proven in the classroom). The prompt lists the declared options verbatim so the model can only choose among them.

A new parser (`agent.py`, alongside `_parse_reply`) extracts `(stance, option_id, reason, full_text)`. Fallback behavior on malformed output or an unrecognized option label:
- Keep the agent's previous stance unchanged (don't move its avatar).
- Log the parse failure (existing `LLM_LOG_FILE` mechanism already captures raw request/response).
- Surface a small non-blocking indicator in the transcript/log ("Agent didn't respond in the expected format this turn") rather than crashing the board or blocking the round.

The referee's rule/constraint checking is unaffected — it continues to see `full_text` as it does today (referee logic is not board-mode-aware in this sub-project; that comes with Group C's rule-citation work).

### 3.3 A2 — the board (perimeter rooms)

Reuses the existing radial-placement engine (`app.js:520-673`, currently used for speech-bubble collision avoidance) rather than inventing new layout math — this was chosen over two other layouts (a horizontal "lanes" board and a 2-row "islands" grid) specifically because it extends code that already exists and handles the crowding case gracefully.

Layout, in board mode only:
- **Center**: the referee avatar, exactly where it sits today.
- **Inner ring**: the undecided/neutral zone. Every agent starts here; anyone without a current stance (hasn't spoken yet this run, or — future-proofing — had a stance explicitly cleared) stays here.
- **Outer perimeter**: divided into one wedge per declared option, evenly spaced, labeled at the rim with the option's text.

Movement: when an agent's stance updates, its avatar animates from its current position to a point inside its option's wedge (or back to the inner ring if a future feature clears stances — not needed for this sub-project, but the data model doesn't preclude it).

Crowding fix (the concern flagged when comparing layouts): each wedge lays out its own avatars in a small internal grid that grows inward toward the center as it fills, rather than a single arc at fixed radius. This is what lets a wedge with 5-6 backers stay legible without spilling into a neighboring wedge — validated against the PRD's own open question #3 (does 6 options × 8 avatars stay legible) by manual stress-testing in the browser before this sub-project is called done.

Board mode replaces the avatar container's rendering (`renderAvatars` / `positionBubbles` in `app.js`) with board-aware versions; non-board-mode sessions keep the current circular free-form renderer untouched.

### 3.4 A3 — avatars as uploaded artwork

`User` gains a new nullable column: `avatar_url: Optional[str] = None`. Ad-hoc agents (added via the admin's "+ Ad-hoc" button, not tied to a real student) and any student without an uploaded image keep using the current emoji pool (`avatarPool` in `app.js` / `avatar_pool` in `main.py`) as a fallback — this field is additive, not a replacement of the emoji system.

Admin's **Students** tab gets a per-student image upload control: a multipart file upload endpoint that stores the file at `static/avatars/{user_id}.{ext}` and records the served path in `avatar_url`. Served as a normal static asset (no new serving infrastructure needed — `static/` is already mounted).

Rendering: wherever an avatar is drawn (`avatar-face` divs in `app.js`, and the corresponding admin-panel previews), swap to an `<img src="{avatar_url}">` when set, else keep the emoji `<div>`. Sized via existing CSS classes so it works at the ~48px board size; using a real uploaded image file now (rather than, say, a cropped inline base64 blob) also means it's already suitable for print resolution when D2 (public card / print asset) is built later — no format migration needed then.

No image generation, cropping UI, or moderation is in scope — PRD A3 is explicit that the instructor uploads a pre-digitized image and no generation is needed.

### 3.5 A5 — paced reveal, extended

Step-by-step mode's existing mechanism (`orchestrator.py:275-306`) — queue a full cycle server-side, reveal one event per keypress via `next_step` — is sound and is not being rebuilt. What's new: in board mode, each queued reveal step carries its `AgentStance` payload alongside the speech content, so when the instructor presses next, the board's avatar movement animates in the same keypress as the speech bubble appears, rather than the board silently jumping to its end state on its own schedule.

Real-time and auto-pause modes (which don't queue/replay, they stream live) get the same board update logic, just driven directly off each `agent_speak` WebSocket event as it arrives instead of off a keypress. The board-update function is shared between both paths; only the trigger differs.

## 4. Data flow summary

1. Instructor creates/edits a package with 3-6 `options` in the admin Packages tab → validated server-side (3-6 required once any options are set).
2. `Load for Session` assembles the session as today, plus copies `pkg.options` onto `session.options` and initializes `session.stances = {}`.
3. Frontend sees non-empty `session.options` → renders board mode (perimeter layout) instead of the free-form room.
4. Each agent turn: LLM produces `STANCE/OPTION/REASON/FULL` → parsed → `session.stances[agent_id]` updated → broadcast (or queued for step-by-step) → frontend animates the avatar into its wedge and shows the reason as a small stance chip.
5. Malformed output → previous stance retained, failure logged and flagged non-blockingly.

## 5. Testing

- **Backend (automated):** unit tests for the new stance parser (valid formats, malformed output, unknown/unlisted option label, missing fields) and for package option validation (reject <3 or >6 when `options` is set; empty `options` passes through unchanged — non-board packages must be unaffected).
- **Frontend (manual, in-browser):** no JS test suite currently exists in this project, and the PRD explicitly prioritizes eyes-on classroom legibility over automated UI testing. Verified live via the Browser tool against seed-demo-style data stretched to 8 agents / 6 options, specifically stress-testing: an uneven split (one option with 5-6 backers) for the wedge crowding fix, the undecided-ring behavior before any agent has spoken, and that non-board packages (e.g. the existing `demo-party` seed, which has no `options`) render exactly as they do today.

## 6. Non-goals for this sub-project

- Reaction layer (A4) — bundled with later enhancements (sub-project #9 in the build order).
- Anything from Mode B / Group E (order round) — different screen, later sub-project.
- Rule citation by number (C3) or any trace/replay functionality (Group C) — depends on this sub-project's stance data but is built separately.
- Image cropping, moderation, or generation for avatars — instructor supplies a pre-digitized image as-is.
- The `TRADE` stance value — deferred; the data model (`stance: Literal[...]`) can be widened later without a migration beyond adding the value.
