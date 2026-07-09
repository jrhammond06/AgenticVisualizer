# AgenticVisualizer

A classroom tool for teaching AI literacy through live multi-agent negotiation. Students build personal AI agents over the course of several weeks by filling out structured profile forms. The instructor loads a negotiation scenario, selects which students participate, and runs the negotiation live on a projected screen while students watch their agents interact.

Built with FastAPI, WebSockets, SQLite, and vanilla JS. Runs against any OpenAI-compatible LLM endpoint (default: OpenRouter).

![stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20WebSocket%20%7C%20SQLite%20%7C%20vanilla%20JS-blue)

## How it works in the classroom

1. **Before class:** The instructor creates student accounts and releases form modules week by week. Students fill in their profile (values, negotiating style, positions) — the answers feed into their agent's system prompt via a template the instructor writes.
2. **Before a session:** The instructor creates a **negotiation package** — a topic, a set of hard constraints (what a valid outcome must satisfy), and a rule set (how agents should engage: tone, deadlock rules, etc.).
3. **In class:** The instructor loads a package, selects which students participate, and clicks **Load for Session**. Agents are assembled from student form answers. The instructor runs the negotiation on a projected screen.
4. **After class:** The run is saved automatically — full event trace, outcome, and consensus result — and can be downloaded for analysis.

The learning arc: students watch their agents evolve over 8 weeks as they add more nuance to their profiles and the class experiments with different rule sets and constraints.

## Architecture overview

```
Three layers of configuration:
  1. Agent system prompts   — built from student form answers + instructor template
  2. Process rules          — how agents engage (tone, deadlock handling, etc.)
                              can be sent to agents, referee, or both
  3. Outcome constraints    — what a valid solution must satisfy (topic-specific)
                              referee-only

Two user roles:
  Admin (instructor)  — /admin, /session
  Student             — /form only; no access to the LLM or session controls
```

## Project layout

```
AgenticVisualizer/
├── main.py              # FastAPI app: all routes, auth, DB access, run tracking
├── models.py            # In-memory session/agent Pydantic models
├── db_models.py         # SQLite table models (SQLModel)
├── database.py          # DB engine + session factory
├── auth.py              # Password hashing, session helpers
├── orchestrator.py      # Turn loop, step-by-step mode, auto-pause
├── agent.py             # Agent LLM reply generation
├── referee.py           # Referee evaluation (structured JSON output)
├── llm.py               # OpenAI-compatible client wrapper
├── config.py            # Environment-based configuration
├── utils.py             # JSON extraction helper
├── static/
│   ├── index.html       # Session/visualization page (admin only)
│   ├── app.js           # Session page logic + WebSocket client
│   ├── styles.css       # Shared styles: avatars, speech bubbles, UI
│   ├── admin.html       # Admin page (tabbed)
│   ├── admin.js         # Admin page logic
│   ├── form.html        # Student profile form
│   ├── form.js          # Form page logic
│   └── login.html       # Login page
├── requirements.txt
├── .env.example
└── agenticvisualizer.db # Created automatically on first run (SQLite)
```

## Quick start (local)

### 1. Install dependencies

```bash
# With uv (recommended):
uv pip install -r requirements.txt

# Or with plain pip inside a venv:
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Minimum required fields in `.env`:

```env
SECRET_KEY=any-long-random-string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Generate a strong secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The app runs without an API key — auth, the admin page, and the student form all work fully. Only clicking **Start Round** requires a live LLM connection.

### 3. Run

```bash
# With uv:
uv run python main.py

# Or with venv activated:
python main.py
```

Navigate to `http://127.0.0.1:8000`. The SQLite database is created automatically on first run.

### 4. First-time setup

1. Log in as admin at `/login`.
2. Go to `/admin` → **Students** tab → create student accounts (username + password).
3. **Form** tab → pick a class tag, add form modules (released week by week), write the system prompt template using `{field_key}` placeholders.
4. **Rule Sets** tab → create named rule sets (process rules for agent behaviour and referee evaluation).
5. **Packages** tab → create a negotiation package: topic, constraints, rule set.
6. Students log in and fill out their forms at `/form`.
7. Admin loads a package → selects participants → lands on `/session` → runs the negotiation.

## LLM configuration

The default provider is **OpenRouter**, which lets you swap models by changing one env var:

```env
MODEL_NAME=openai/gpt-4o-mini                      # agent model
REFEREE_MODEL_NAME=anthropic/claude-sonnet-4-5     # referee (needs reliable structured output)
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

## Negotiation modes

| Mode | Behaviour |
|---|---|
| **Real-time** | Each agent speaks as its response is generated; fastest for live demos |
| **Auto-pause** | Runs one full cycle (every agent speaks once), then pauses for instructor review before continuing |
| **Step-by-step** | Generates a full cycle silently in the background, then reveals one message at a time on instructor keypress |

Turn order can be **sequential**, **random**, or **simultaneous proposals** (everyone opens at once, then sequential reactions).

## Rule sets vs. constraints

| | Rule sets | Package constraints |
|---|---|---|
| **Purpose** | Process rules — *how* agents engage | Outcome conditions — *what* a valid solution satisfies |
| **Scope** | Global library, reusable across packages | Specific to one package/topic |
| **Goes to** | Configurable per rule: agents, referee, or both | Referee only |
| **Examples** | "Maintain a polite tone", "majority vote breaks deadlocks" | "Budget under $10/person", "must include a vegetarian option" |

Each rule in a rule set has an **Applies to** setting:
- **Agents + Referee** — injected into every agent's system prompt *and* evaluated by the referee (use for tone and behaviour rules)
- **Referee only** — meta-rules the referee uses to manage the process (deadlock handling, voting mechanisms)
- **Agents only** — rare; gives agents instructions without referee enforcement

## Deployment (Vultr + Coolify)

Recommended setup: a single Vultr VPS in the **Seoul** region (~$6/month) running [Coolify](https://coolify.io) as a self-hosted PaaS. Coolify handles git-push deploys, automatic HTTPS, and reverse proxying — multiple small apps share one server bill.

Key production env vars to set:

```env
DATABASE_URL=sqlite:////data/agenticvisualizer.db  # mount a persistent volume at /data
SITE_URL=https://yourdomain.com
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agents say "I'm having trouble thinking right now" | Check `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` in `.env` |
| "Admin login disabled" warning on startup | `ADMIN_PASSWORD` is not set in `.env` |
| WebSocket disconnects immediately | Admin auth is required on the WS endpoint — make sure you're logged in as admin before opening `/session` |
| Can't edit agents during a round | Editing is locked while a round is running; stop it first |
| Rounds feel slow | Lower **Max turns**, use a faster model, or switch to **Step-by-step** mode so generation happens in the background |
| Need to debug LLM calls | Set `LLM_LOG_FILE=llm_calls.jsonl` in `.env`; every request and response is logged (API key masked) |
| Corporate proxy | Set `HTTP_PROXY` and `HTTPS_PROXY` in `.env` |
| Student can't see their form modules | Check that their `class_tag` matches the tag on the form modules, and that the modules are set to **Unlocked** |
