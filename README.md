# AgenticVisualizer

A live, classroom-friendly visualization of 2–10 AI agents negotiating in a shared "room." Built for teaching elementary-school kids how agents interact, how prompts shape behavior, and how an orchestrator controls the rules of engagement.

![architecture](https://img.shields.io/badge/stack-FastAPI%20%7C%20WebSocket%20%7C%20vanilla%20JS-blue)

## What it does

- Shows agents as cartoon avatars in a circle.
- Streams each turn live via WebSocket: who is thinking, who is speaking, and what they said.
- Lets the teacher edit each agent’s visible goal and hidden system prompt between rounds.
- Supports different turn-order rules (sequential, random, simultaneous proposals).
- Enforces menu constraints: budget, number of items, dietary/allergy rules.
- **Referee agent** enforces rules of engagement (allergies, budget logic, everyone-gets-something) and evaluates whether real consensus exists.
- Produces a structured party menu outcome when consensus is reached, or a "where things stand" summary when it isn't.
- Runs against any OpenAI-compatible chat completions endpoint.

## Quick start

### 1. Install dependencies

```bash
cd AgenticVisualizer
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your LLM endpoint

```bash
cp .env.example .env
```

The prototype defaults to **OpenRouter**, so a minimal `.env` looks like:

```env
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=sk-or-v1-your-key-here
MODEL_NAME=openai/gpt-4o-mini
```

You can switch models just by changing `MODEL_NAME`:

```env
MODEL_NAME=anthropic/claude-3.5-haiku
# or
MODEL_NAME=google/gemini-flash-1.5
```

The referee can use a different, usually stronger model via `REFEREE_MODEL_NAME`:

```env
REFEREE_MODEL_NAME=~anthropic/claude-sonnet-latest
```

If you prefer to use OpenAI directly, change the variables:

```env
OPENROUTER_BASE_URL=https://api.openai.com/v1
OPENROUTER_API_KEY=sk-your-openai-key-here
MODEL_NAME=gpt-4o-mini
```

Any OpenAI-compatible endpoint works (Azure, OpenRouter, local vLLM/Ollama, etc.).

### 3. Run the server

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 4. Open in a browser

Navigate to `http://127.0.0.1:8000`.

For the classroom: open the page on the projector, then click the **☰** button to collapse the teacher panel so the kids only see the room.

## How to use in class

1. **Set the topic** in the teacher panel (default: "What should the menu be for our party?").
2. **Set menu constraints**: budget, number of items, and dietary/allergy rules (e.g., "No nuts; at least one vegan option").
3. **Edit Referee rules of engagement**: define how the Referee assesses budget, enforces allergies, and pushes for fairness (e.g., "everyone gets at least one thing they want").
4. **Add or edit agents** — each agent represents one kid’s preferences:
   - **Goal**: what they want, shown to the class.
   - **System prompt**: their full preferences, allergies, dislikes, and strategy (hidden from the class but drives the agent).
5. **Pick rules**: sequential turns, random turns, or simultaneous opening proposals; set max/min turns.
6. Click **▶ Start Round** and watch the agents negotiate.
7. The **Referee** evaluates after each full cycle, broadcasting warnings if rules are violated and checking for real consensus.
8. When the round ends, you either see a **Party Menu** card (consensus reached) or a **Where Things Stand** summary (no consensus yet).
9. Change prompts, constraints, or Referee rules and run again.

## Project layout

```
AgenticVisualizer/
├── main.py              # FastAPI app, REST + WebSocket routes
├── models.py            # Pydantic data models
├── agent.py             # Agent reply generation
├── orchestrator.py      # Turn loop, rules, termination, summarizer
├── llm.py               # OpenAI-compatible client wrapper
├── config.py            # Environment-based settings
├── static/
│   ├── index.html       # UI
│   ├── app.js           # Frontend logic + WebSocket
│   └── styles.css       # Room, avatars, speech bubbles
├── requirements.txt
└── .env.example
```

## Customization ideas

- **Change the default scenario** in `main.py` where the initial `Session` is created.
- **Tighten or loosen consensus** by editing `_check_consensus()` in `orchestrator.py`.
- **Add new rules** (e.g., “must make a proposal,” “no repeating”) in `orchestrator.py` and expose them in the teacher panel.
- **Change how the Referee evaluates consensus** by editing `referee.py`. It returns JSON with `warnings`, `consensus_reached`, `proposed_menu`, `estimated_cost`, and `status_summary`.
- **Change how the menu is summarized** by editing `_broadcast_outcome()` in `orchestrator.py`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agents say “I’m having trouble thinking right now” | Check that `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` are set correctly in `.env`. |
| Page is blank | Make sure the server is running and you’re visiting the right port. |
| Can’t edit agents | Editing is locked while a round is running. Stop the round first. |
| Rounds feel slow | Lower **Max turns** or use a faster model. The simultaneous-proposal rule also speeds up the opening. |
| Need to debug OpenRouter errors | Run `python test_openrouter.py` for a standalone connectivity check, or run the server with `LOG_LEVEL=DEBUG`. Every request/response to the LLM endpoint is logged (API key is masked). |
| Connection error / cannot reach openrouter.ai | Check your network/firewall. If you're behind a corporate proxy, set `HTTP_PROXY` and `HTTPS_PROXY` in `.env`. |

## Notes

- Session state is held in memory, so restarting the server resets everything. For a persistent classroom setup, add a simple JSON file or database backend.
- This is a prototype. The consensus detection and outcome summary are heuristic LLM calls designed for kid-friendly demonstrations, not formal negotiation research.
