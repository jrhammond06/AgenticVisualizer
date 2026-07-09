# AgenticVisualizer

A classroom tool for teaching AI literacy through live multi-agent negotiation. Students build personal AI agents over several weeks by filling out structured profile forms. The instructor loads a negotiation scenario, selects which students participate, and runs the negotiation live on a projected screen while the class watches their agents interact — and argue, compromise, and (sometimes) reach consensus.

Built with FastAPI, WebSockets, SQLite, and vanilla JS. Runs against any OpenAI-compatible LLM endpoint (default: OpenRouter).

---

## Table of contents

1. [What this is](#what-this-is)
2. [Core concepts](#core-concepts)
3. [The admin panel — tab by tab](#the-admin-panel--tab-by-tab)
4. [Common points of confusion](#common-points-of-confusion)
5. [Step-by-step: setting up a new scenario](#step-by-step-setting-up-a-new-scenario)
6. [Negotiation modes](#negotiation-modes)
7. [LLM configuration](#llm-configuration)
8. [Project layout](#project-layout)
9. [Quick start](#quick-start)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)

---

## What this is

AgenticVisualizer has two phases:

**Phase 1 — Agent building (weeks before the session).** Students fill out a structured questionnaire called a "form." The form answers feed into their agent's *system prompt* — the hidden instruction that tells the LLM who the agent is, what it wants, and how it negotiates. The instructor controls which questions are released each week and writes the template that turns answers into a system prompt.

**Phase 2 — Live negotiation (in class).** The instructor loads a "package" — a scenario definition containing a topic, any hard outcome requirements (constraints), and a rule set that governs how agents interact. They select which students participate, hit **Load for Session**, and the agents assemble automatically from student data. The instructor then runs the negotiation on a projected screen. Students watch their agents speak, argue, and (hopefully) find a deal.

The pedagogical arc: students see their agents change as they refine their profiles; the instructor experiments with different rule sets to show how process rules shape outcomes even when agent personalities are held constant.

---

## Core concepts

Understanding these seven building blocks makes the admin panel self-explanatory.

### 1. Classes

A **class** is just a label (a short tag like `AI2026-S1`) that groups students together. It has no logic of its own — it is used to:
- Filter which students see which form modules
- Filter which packages are shown in a given context
- Associate packages and runs with a cohort

You can have multiple classes sharing one server instance (e.g. morning and afternoon sections, or different years).

### 2. Students

A **student** is a login account. Each student has:
- A username and password (set by the instructor)
- A display name (used as their agent's name during the negotiation)
- A class tag (which class they belong to)

Students only have access to `/form` — they never see the session, the admin panel, or any other student's data.

### 3. Agents

An **agent** is the LLM character that represents a student during a negotiation. It is assembled at load time from the student's form answers. An agent has three parts:

| Part | Source | Controls |
|---|---|---|
| **Identity** | Agent identity template (on the package) | Who the agent *is* in this scenario — its role, its framing |
| **Personality** | Student's form answers → system prompt | How the agent thinks, negotiates, and what it wants |
| **Behavior rules** | Agent speaking instructions (on the rule set) | How it communicates: reply length, style, format |

These three parts are intentionally separate so you can vary one while holding the others constant. For example: keep personality fixed and swap the identity template to turn the same student profile into a "UN mediator" in one scenario and a "corporate lawyer" in another. Or keep identity and personality fixed and swap the rule set to show students how process rules affect outcomes.

### 4. The Form system

The **form** is the multi-week questionnaire students fill out to build their agent profiles.

The instructor manages two things:

- **Form modules** — individual questionnaire sections, each containing one or more fields (short text or long text). Modules can be locked or unlocked; students only see unlocked modules. The instructor releases them week by week.

- **System prompt template** — a text template with `{field_key}` placeholders that combines all form answers into a coherent agent system prompt. For example: `You are {display_name}. Your position on the issue: {position}. Your non-negotiables: {limits}.`

When a package is loaded, the system renders each student's template using their current form answers. The result becomes the **personality** component of their agent's system prompt.

### 5. Rule Sets

A **rule set** is a reusable collection of rules that governs how a negotiation session runs. It lives in a library — you create it once and can attach it to many packages.

A rule set has two parts:

**Rules** — named statements that the referee monitors. Each rule has:
- A *name* and *text* (the actual rule)
- A *severity*: `Guideline` (soft, the referee warns) or `Hard constraint` (the referee blocks consensus until satisfied)
- An *applies to* setting: **Agents + Referee** (injected into agent prompts and monitored by the referee), **Referee only** (the referee monitors it but agents don't see it explicitly), or **Agents only** (agents see it but the referee doesn't enforce it)

Examples of rules:
- "Maintain a respectful tone at all times" → Guideline, Agents + Referee
- "No agreement is valid unless every participant explicitly agrees" → Hard constraint, Referee only
- "If deadlocked after 3 cycles, the referee may impose a majority-vote resolution" → Guideline, Referee only

**Agent speaking instructions** — a separate text block (not a rule, not monitored by the referee) that is injected directly into every agent's system prompt. This controls *how* agents communicate: reply length, whether to use bullet points, how directly to address other agents, etc.

Examples of agent speaking instructions:
- "Reply in 1 or 2 short sentences only. Address other agents by name."
- "You may be blunt. No diplomatic hedging. State your position plainly."
- "This is a formal board meeting. Speak in complete sentences. Do not interrupt."

If left blank, a built-in default is used (conversational, 1–2 sentences, no bullet points).

### 6. Packages

A **package** is a complete scenario definition for one negotiation. It combines:

- **Topic** — the question the agents are deciding (e.g. "What should our team focus on next quarter?")
- **Hard constraints** — topic-specific outcome requirements that the referee enforces (e.g. "The final budget cannot exceed $10,000"). These are always referee-only. Unlike rule set rules, they live on the package because they are scenario-specific, not reusable.
- **Rule set** — which rule set to apply (pulled from the library)
- **Agent identity template** — a text template that defines who agents *are* in this scenario. Uses these placeholders:

  | Placeholder | Filled with |
  |---|---|
  | `{name}` | Agent's display name |
  | `{goal}` | Agent's stated goal (currently always "Participate in the negotiation") |
  | `{topic}` | The negotiation topic |
  | `{rules}` | All rules of engagement (constraints + rule set rules), formatted |
  | `{system_prompt}` | The student's personal system prompt (from form answers) |
  | `{speaking_instructions}` | The rule set's agent speaking instructions |

  If left blank, a sensible built-in default is used ("You are {name}, a participant in a managed debate...").

  The identity template is the main lever for exploring the **identity vs. personality vs. rules** question in class: "What happens when an aggressive personality has to operate under a polite rule set? What happens when the same personality is reframed as a diplomat vs. a corporate executive?"

### 7. The Referee

The **Referee** is a separate, automatic LLM call (typically a more capable model than the agents) that runs at the end of every full speaking cycle. It:

- Reads the full conversation so far
- Checks whether any hard constraints or guidelines have been violated
- Issues warnings that all agents can see in the next turn
- Decides whether the group has reached valid consensus
- Produces a structured summary of the current state

The referee uses a different model from the agents (configured separately in `.env`) because it needs reliable structured output — it returns JSON, not free text.

### 8. Sessions and Runs

A **session** is the live, in-memory negotiation state. There is exactly one session at a time (it is reset when a new package is loaded). The session page (`/session`) shows a real-time speech bubble display with agent avatars.

A **run** is the permanent record of a completed session. It is saved automatically when a round ends or consensus is reached. Each run stores:
- Which package was used
- Which students participated
- The full event trace (every message, referee evaluation, and status update)
- Whether consensus was reached and what the final outcome was

Run traces can be downloaded as JSON from the **Runs** tab for analysis.

---

## The admin panel — tab by tab

### Students tab

**What it does:** Manages classes and student login accounts.

**Classes section:** Create a short tag (e.g. `AI2026-S1`) and an optional display name. The tag is what everything else references — keep it short and memorable.

**Students section:** Create student accounts. The display name becomes the agent's name in the negotiation. Assign each student a class tag so they see the right form modules.

> Tip: Students can change their form answers any time before you load the package. Their agent is assembled from their *current* answers at load time.

### Form tab

**What it does:** Designs the student questionnaire and the template that turns answers into a system prompt.

**Requires a class to be selected** (use the class dropdown at the top).

**Form modules (left column):** Each module is a section of the form (e.g. "Week 1: Your Position", "Week 3: Your Negotiating Style"). Each module contains one or more fields — either short text (one line) or long text (paragraph). Lock/unlock modules to control what students see each week.

**System prompt template (right column):** A text template that combines all form answers into a coherent agent system prompt. Use `{display_name}` for the student's name and `{field_key}` for any field defined in your modules. Use the **Preview** tool to see what the rendered prompt looks like for a specific student.

> Example: If you have a field with key `position`, the template can include `Your negotiating position: {position}.`

> Note: This template controls the agent's **personality** — what it wants and how it thinks. The agent's **identity** (who it is in the scenario) is set separately on each package via the Agent identity template.

### Rule Sets tab

**What it does:** Manages the library of reusable rule sets.

Each rule set has:
- A name and description
- A list of individual rules (see [Core concepts](#5-rule-sets) above for what each field means)
- An **Agent speaking instructions** block — freeform text injected into agent prompts to control communication style

The **+ Add rule** button adds a blank rule. Each rule has four fields: name, text, severity (Guideline / Hard constraint), and Applies to (Agents + Referee / Referee only / Agents only).

> Rule sets are reusable. If you want to compare "polite" vs. "aggressive" rule sets across the same scenario, create two rule sets and two packages pointing at the same topic but different rule sets.

### Packages tab

**What it does:** Manages negotiation scenarios.

**Requires a class to be selected** (use the class dropdown).

Each package has:
- A **name** and **topic** (the question agents will decide)
- A **rule set** (selected from the library)
- **Hard constraints** — topic-specific requirements the referee enforces. These differ from rule set rules in that they are *outcome* requirements specific to this scenario, not reusable process rules.
- An **Agent identity template** — see [Core concepts](#6-packages) for placeholders. Leave blank for the built-in default.

**Load for Session →** opens a modal where you select which students to include. Their form answers are used to assemble agents. Clicking **Load for Session** in the modal replaces the current session and redirects to the session page.

### Profiles tab

**What it does:** Lets you view and directly edit individual student system prompts.

Each student card shows their form answers and their current rendered system prompt (either from the template or a manual override). You can type directly into the system prompt box and click **Save override** to bypass the template for that student. **Reset** removes the override and returns to the template-rendered output.

> Use this to fine-tune a specific agent without touching the template, or to create a "ringer" agent with a carefully crafted prompt that you don't want generated from a form.

### Runs tab

**What it does:** Shows the history of completed negotiation runs.

Each row shows the package name, start time, class, and outcome (Consensus / No consensus). Click **⬇ Trace** to download the full event trace as a JSON file — useful for in-class analysis or grading.

---

## Common points of confusion

### "Rules" vs. "Agent speaking instructions" in a rule set

**Rules** are *monitored*. The referee reads them and warns agents when they are violated. They are about *what* is allowed or required in the negotiation: tone requirements, deadlock handling, voting procedures, outcome conditions.

**Agent speaking instructions** are *not monitored*. They are a formatting and style directive baked directly into every agent's system prompt. They control *how* agents write their responses: reply length, sentence structure, whether to use bullet points, whether to address other agents by name. The referee never sees these — they are purely about the format of agent outputs.

Think of it this way: rules define the *laws* of the negotiation; agent speaking instructions define the *house style*.

### "Package constraints" vs. "Rule set rules"

| | Package constraints | Rule set rules |
|---|---|---|
| **Topic** | Specific to this scenario | Reusable across scenarios |
| **Examples** | "Budget must not exceed $100", "Must include a vegetarian option" | "All participants must be heard", "Unanimous agreement required" |
| **Goes to** | Referee only | Configurable (Referee / Agents / Both) |
| **Severity** | Always hard constraint | Guideline or hard constraint |

### "System prompt template" (Form tab) vs. "Agent identity template" (Packages tab)

**System prompt template** (Form tab): Turns a student's form answers into their agent's **personality** — what it wants, what its position is, how it thinks about the topic. This is the student's unique, personal contribution to their agent.

**Agent identity template** (Packages tab): Defines the **role frame** for the entire scenario — who all the agents *are* in this context. It wraps the personality in a situational framing. Example: "You are `{name}`, a corporate lawyer representing a tech company in an acquisition negotiation. Your client's brief: `{system_prompt}`."

The separation lets you ask: *"What happens when the same student profile operates as a corporate lawyer vs. a UN mediator?"* — just change the package's identity template while keeping the student form answers identical.

### The student's form page vs. the admin's Form tab

**Students** at `/form` see a clean questionnaire and fill in their answers. That's it — they have no visibility into templates, other students' data, or the session.

**The admin** at `/admin` → Form tab designs the questionnaire (what questions to ask, in which order, which to unlock this week) and writes the template that turns answers into system prompts. Students never see the template.

---

## Step-by-step: setting up a new scenario

### One-time setup

**1. Install and start the app** (see [Quick start](#quick-start)).

**2. Create a class**
> Admin → Students tab → Classes section → enter a short tag (e.g. `spring2026`) and an optional display name → **+ Add class**

**3. Create student accounts**
> Admin → Students tab → Students section → enter username, display name, class, and initial password → **+ Add student**

Repeat for each student. Share usernames/passwords with students so they can log in.

**4. Design the form**
> Admin → Form tab → select your class

- Add modules one at a time with **+ Add module**. For each module, set a title and week number, add fields (key + label + type), and save.
- Leave modules **locked** until you're ready to release them. Students only see unlocked modules.
- Write the **system prompt template** in the right column. Use `{display_name}` and any `{field_key}` you defined.
- Click **Preview** with a student selected to check the rendered output.

**5. Create a rule set**
> Admin → Rule Sets tab → **+ New rule set**

A fresh rule set is created with a placeholder name. Click **Edit** to expand it:
- Set a name and description.
- Add rules with **+ Add rule**. For each: name, text, severity, and who it applies to.
- Write **Agent speaking instructions** (optional; leave blank for defaults).
- Click **Save**.

**6. Create a package**
> Admin → Packages tab → select your class → **+ New package**

Click **Edit** on the new package:
- Set a name, topic, and rule set.
- Add any **Hard constraints** specific to this scenario.
- Write an **Agent identity template** (optional; leave blank for defaults).
- Click **Save**.

### Before each session

**7. Have students fill out their forms**
Students log in at `/form` and answer any unlocked modules. They can update answers any time before you load the package.

**8. (Optional) Review profiles**
> Admin → Profiles tab → select your class

Check each student's rendered system prompt. You can set manual overrides here if needed.

### Running the session

**9. Load the package**
> Admin → Packages tab → find your package → **Load for Session →**

In the modal: check which students to include, then click **Load for Session**. You are redirected to `/session`.

**10. Configure and start**

On the session page you can adjust:
- **Max turns / Min turns** — how long the negotiation runs before the referee wraps up
- **Turn order** — Sequential, Random, or Simultaneous proposals
- **Mode** — Real-time, Auto-pause, or Step-by-step (see [Negotiation modes](#negotiation-modes))

Click **Start Round** to begin. Watch the agents talk. The referee evaluates after every full speaking cycle.

**11. After the session**

The run is saved automatically. Go to Admin → Runs tab to download the event trace.

---

## Scripting setup with seed_demo.py

For quick testing without manual UI setup, run the included demo seed script:

```bash
# Windows (.venv):
.venv\Scripts\python.exe seed_demo.py

# Mac/Linux (venv activated):
python seed_demo.py
```

This creates a complete demo scenario: four 10-year-old characters (Emma, Jake, Sofia, Marcus) planning a class party menu with a $100 budget and genuine dietary tensions. See the script itself — it is heavily annotated and is designed to serve as a template for writing your own seed scripts.

To load the demo after seeding:
> Admin → Packages tab → filter by class `demo-party` → **Load for Session** → select all four students → **Load for Session**

---

## Negotiation modes

| Mode | Behaviour | Best for |
|---|---|---|
| **Real-time** | Each agent speaks as its response arrives; referee evaluates at the end of each cycle | Live demos where pace matters |
| **Auto-pause** | Runs one full cycle (every agent speaks once), then pauses so the instructor can comment before continuing | Classroom discussion between cycles |
| **Step-by-step** | Generates a full cycle silently in the background, then reveals one message at a time on instructor keypress | Close reading; letting students predict what comes next |

**Turn order** options:
- **Sequential** — agents always speak in the same fixed order
- **Random** — order is shuffled each turn
- **Simultaneous proposals** — everyone submits an opening proposal at once, then the discussion continues sequentially

---

## LLM configuration

The default provider is **OpenRouter**, which lets you swap models by changing one `.env` variable.

```env
MODEL_NAME=openai/gpt-4o-mini          # agent model (called once per agent per turn)
REFEREE_MODEL_NAME=anthropic/claude-sonnet-4-5   # referee (needs reliable structured output)
```

Any OpenAI-compatible endpoint works:

```env
# OpenAI directly:
OPENROUTER_BASE_URL=https://api.openai.com/v1
OPENROUTER_API_KEY=sk-your-openai-key
MODEL_NAME=gpt-4o-mini

# Local (Ollama):
OPENROUTER_BASE_URL=http://localhost:11434/v1
OPENROUTER_API_KEY=ollama
MODEL_NAME=llama3.2
```

**Model selection guidance:**
- Agent model: almost anything works. Smaller/cheaper models (GPT-4o-mini, Haiku, Gemini Flash) are fast and cost-effective. Agents only need to produce 1–2 sentence replies.
- Referee model: needs to produce reliable structured JSON. Use a mid-tier or better model. Claude Sonnet, GPT-4o, and Gemini Pro all work well.

**Cost estimate:** A 10-turn, 4-agent session with GPT-4o-mini agents + Claude Haiku referee typically costs under $0.05 USD on OpenRouter.

---

## Project layout

```
AgenticVisualizer/
├── main.py              # FastAPI app: all routes, auth, DB access, run tracking
├── models.py            # In-memory session/agent Pydantic models
├── db_models.py         # SQLite table definitions (SQLModel)
├── database.py          # DB engine, session factory, and migrations
├── auth.py              # Password hashing, session cookie helpers
├── orchestrator.py      # Turn loop, step-by-step mode, auto-pause logic
├── agent.py             # Agent LLM reply generation; prompt template rendering
├── referee.py           # Referee evaluation (structured JSON output via LLM)
├── llm.py               # OpenAI-compatible async client wrapper
├── config.py            # Environment-based configuration
├── utils.py             # JSON extraction helper
├── seed_demo.py         # Annotated seed script: creates the party-planning demo
├── static/
│   ├── index.html       # Session/visualization page (admin only)
│   ├── app.js           # Session page logic + WebSocket client
│   ├── styles.css       # Shared styles: avatars, speech bubbles, layout
│   ├── admin.html       # Admin panel (tabbed)
│   ├── admin.js         # Admin panel logic (all tabs)
│   ├── form.html        # Student profile form page
│   ├── form.js          # Form page logic
│   └── login.html       # Login page
├── requirements.txt
├── .env.example
└── agenticvisualizer.db # Created automatically on first run (SQLite)
```

---

## Quick start

### 1. Install dependencies

```bash
# With uv (recommended):
uv pip install -r requirements.txt

# Or with plain pip inside a venv:
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Minimum required fields:

```env
SECRET_KEY=any-long-random-string     # generate: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

The app starts without an API key — auth, the admin panel, and student forms all work. Only **Start Round** requires a live LLM connection.

### 3. Run

```bash
# With uv:
uv run python main.py

# Or with venv activated:
python main.py
```

Navigate to `http://127.0.0.1:8000`. Log in as admin, then go to `/admin`.

### 4. Try the demo

Seed the demo scenario, then load it from the admin panel:

```bash
python seed_demo.py         # or: .venv\Scripts\python.exe seed_demo.py on Windows
```

> Admin → Packages → filter by `demo-party` → Load for Session → select all 4 → Load

---

## Deployment

**Recommended:** a single Vultr VPS running [Coolify](https://coolify.io) as a self-hosted PaaS. Coolify handles git-push deploys, automatic HTTPS, and reverse proxying — multiple small apps share one server.

Key production `.env` settings:

```env
DATABASE_URL=sqlite:////data/agenticvisualizer.db   # mount a persistent volume at /data
SITE_URL=https://yourdomain.com
SECRET_KEY=<long random string, never reuse dev key>
ADMIN_PASSWORD=<strong password>
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agents say "I'm having trouble thinking right now" | Check `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` in `.env` |
| "Admin login disabled" warning on startup | `ADMIN_PASSWORD` is not set in `.env` |
| WebSocket disconnects immediately | Admin auth is required on the WS endpoint — make sure you're logged in as admin before opening `/session` |
| Can't edit agents during a round | Editing is locked while a round is running; stop it first |
| Rounds feel slow | Lower **Max turns**, use a faster agent model, or use **Step-by-step** mode so generation happens in the background |
| Need to debug LLM calls | Set `LLM_LOG_FILE=llm_calls.jsonl` in `.env`; every request and response is logged (API key masked) |
| Student can't see form modules | Check that their `class_tag` matches the tag on the form modules, and that the modules are **Unlocked** |
| Form answer placeholders showing as `[key not provided]` | The `{field_key}` in your template doesn't match any field key in your modules — check spelling |
