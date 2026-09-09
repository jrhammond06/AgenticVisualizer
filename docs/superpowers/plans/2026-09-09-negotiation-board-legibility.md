# Negotiation Board Legibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the negotiation screen legible to 9-year-old ESL students by adding a per-package "board mode": structured stance output (WANT/OK WITH/WON'T + option + ≤8-word reason), a perimeter-room spatial layout, uploaded-image avatars, and paced reveal that drives the board.

**Architecture:** Additive, opt-in per package via a new `options` field — packages with 3-6 declared options run in board mode; every existing package (empty `options`) is byte-for-byte unaffected. Backend: a new stance-parsing convention extends the existing `POINT:`-tag pattern in `agent.py`; `orchestrator.py` threads the parsed stance through the same broadcast/queue events step-by-step mode already uses. Frontend: a new board renderer reuses the existing radial-placement math in `app.js`, sharing avatar-element construction with the current free-form room so image-avatar support lands in both.

**Tech Stack:** FastAPI + SQLModel (SQLite) backend, vanilla JS/CSS frontend, pytest for new backend unit tests (introduced in Task 1 — no test suite exists in this repo yet).

**Spec:** [docs/superpowers/specs/2026-09-09-negotiation-board-legibility-design.md](../specs/2026-09-09-negotiation-board-legibility-design.md)

## Global Constraints

- Stance vocabulary is fixed at exactly three values: `want`, `ok_with`, `wont` (internal keys) / `WANT`, `OK WITH`, `WON'T` (display/prompt text). No fourth value, no free-form stances.
- A package's `options`, when set, must have between 3 and 6 entries (validated server-side).
- Reason text is capped at 8 words (truncated server-side with a trailing `…` if longer).
- Board mode is entirely opt-in per package (via non-empty `options`); no existing package's behavior may change.
- No JSON-mode / tool-calling for LLM output — stance output uses the same tagged-line convention as the existing `POINT:` format, to preserve compatibility with non-function-calling endpoints (e.g. local Ollama models) per `README.md:383-386`.
- Avatar images are stored as files under `static/avatars/`, referenced by URL — no base64/DB blobs.

---

## File Structure

**Backend — modified:**
- `models.py` — new `Option`, `AgentStance` models; `validate_options()`; `Session.options` / `Session.stances` fields
- `db_models.py` — `PackageDB.options`; `User.avatar_url`
- `database.py` — new migrations; `_migrate`/`create_db_and_tables` take an optional `engine` param for testability
- `agent.py` — board-mode prompt instruction + stance parser; `generate_reply` gains an `options` param and a 3rd return value
- `orchestrator.py` — `_apply_stance` helper; all 5 `generate_reply` call sites pass `session.options` and thread `stance` into broadcast/queued events
- `main.py` — package endpoints carry `options`; `load_package` / `reset_session_route` populate `session.options`/`stances`; agents carry `avatar_url`; new avatar-upload endpoint; user endpoints carry `avatar_url`

**Backend — new:**
- `requirements-dev.txt` — `pytest`, `httpx` test extras (introduced in Task 1)
- `tests/__init__.py`, `tests/test_models.py`, `tests/test_agent_stance.py`, `tests/test_database.py`, `tests/test_orchestrator_stance.py`

**Frontend — modified:**
- `static/app.js` — shared avatar-element builder (image support); board renderer (`computeBoardPositions`, `renderBoard`, `applyBoardPositions`); WS handler threads `stance` payload
- `static/styles.css` — board-mode layout classes, stance chip, option label, `<img>` avatar sizing
- `static/admin.js` — Packages tab options editor (mirrors the existing constraints editor); Students tab avatar upload control
- `static/admin.html` — file-input markup for the avatar upload control

No new frontend files — the board renderer lives alongside the existing room renderer in `app.js` since they share state, DOM container, and avatar-building code; splitting them into separate files would just add an import boundary with no isolation benefit in a vanilla-JS single-page app this size.

---

### Task 1: Data models — Option, AgentStance, validate_options

**Files:**
- Modify: `models.py`
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `models.Option(id: str, label: str)`, `models.AgentStance(stance: Literal["want","ok_with","wont"], option_id: str, reason: str, full_text: str)`, `models.validate_options(options: list) -> None` (raises `ValueError`), `Session.options: List[Option]`, `Session.stances: Dict[str, AgentStance]`

- [ ] **Step 1: Add pytest to the project**

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0.0
```

Run: `pip install -r requirements-dev.txt` (or, if using uv: `uv pip install -r requirements-dev.txt`)

- [ ] **Step 2: Write the failing tests**

Create `tests/__init__.py` (empty file).

Create `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from models import Option, AgentStance, Session, validate_options


def test_option_requires_id_and_label():
    opt = Option(id="park", label="Park Party")
    assert opt.id == "park"
    assert opt.label == "Park Party"


def test_agent_stance_rejects_unknown_stance_value():
    with pytest.raises(ValidationError):
        AgentStance(stance="maybe", option_id="park", reason="it's fun", full_text="I like the park.")


def test_agent_stance_accepts_declared_values():
    for value in ("want", "ok_with", "wont"):
        stance = AgentStance(stance=value, option_id="park", reason="reason", full_text="full text")
        assert stance.stance == value


def test_session_defaults_to_no_options_and_no_stances():
    session = Session(topic="Test topic")
    assert session.options == []
    assert session.stances == {}


def test_validate_options_allows_empty_list():
    validate_options([])  # non-board package — no error


def test_validate_options_allows_three_to_six():
    for n in (3, 4, 5, 6):
        validate_options([{"id": str(i), "label": f"Option {i}"} for i in range(n)])


def test_validate_options_rejects_two():
    with pytest.raises(ValueError):
        validate_options([{"id": "1", "label": "One"}, {"id": "2", "label": "Two"}])


def test_validate_options_rejects_seven():
    with pytest.raises(ValueError):
        validate_options([{"id": str(i), "label": f"Option {i}"} for i in range(7)])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Option' from 'models'`

- [ ] **Step 4: Implement**

Edit `models.py` — add `Dict` to the typing import and add the new models near the top (after the existing imports, before `Agent`):

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from config import MAX_ROUNDS_DEFAULT, MIN_ROUNDS_DEFAULT


class Option(BaseModel):
    id: str
    label: str


class AgentStance(BaseModel):
    stance: Literal["want", "ok_with", "wont"]
    option_id: str
    reason: str
    full_text: str


def validate_options(options: list) -> None:
    """Raise ValueError unless `options` is empty (non-board package) or has 3-6 entries."""
    if options and not (3 <= len(options) <= 6):
        raise ValueError("A package's options must include between 3 and 6 entries.")
```

Edit the `Session` class to add two fields (after `agent_prompt_template: str = ""`, before the round-state fields):

```python
    agent_prompt_template: str = ""
    # Board mode: declared negotiation options and each agent's current stance.
    # Both empty means this session runs the original free-form room.
    options: List[Option] = []
    stances: Dict[str, AgentStance] = {}
    # Round state, preserved when auto-pause interrupts a round.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add models.py requirements-dev.txt tests/__init__.py tests/test_models.py
git commit -m "feat: add Option/AgentStance models and options validation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Board-mode stance parsing in agent.py

**Files:**
- Modify: `agent.py`
- Create: `tests/test_agent_stance.py`

**Interfaces:**
- Consumes: `models.Option`, `models.AgentStance`
- Produces: `agent._normalize_stance(raw: str) -> Optional[str]`, `agent._cap_words(text: str, max_words: int) -> str`, `agent._parse_board_reply(reply: str, options: List[Option]) -> tuple[str, Optional[AgentStance]]`, `Agent.generate_reply(..., options: List[Option] = []) -> tuple[str, str, Optional[AgentStance]]` (3rd element replaces the implicit "no stance" case; `summary` is the stance's `reason` when board mode is active, unchanged POINT-tag behavior otherwise)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_stance.py`:

```python
from agent import _normalize_stance, _cap_words, _parse_board_reply
from models import Option

OPTIONS = [
    Option(id="park", label="Park Party"),
    Option(id="bowling", label="Bowling"),
    Option(id="pool", label="Pool"),
]


def test_normalize_stance_accepts_exact_forms():
    assert _normalize_stance("WANT") == "want"
    assert _normalize_stance("OK WITH") == "ok_with"
    assert _normalize_stance("WON'T") == "wont"


def test_normalize_stance_tolerates_case_and_punctuation():
    assert _normalize_stance("want") == "want"
    assert _normalize_stance("wont") == "wont"
    assert _normalize_stance("ok with") == "ok_with"
    assert _normalize_stance("Won’t") == "wont"  # curly apostrophe


def test_normalize_stance_rejects_unknown_value():
    assert _normalize_stance("MAYBE") is None


def test_cap_words_leaves_short_text_untouched():
    assert _cap_words("no rain risk", 8) == "no rain risk"


def test_cap_words_truncates_long_text():
    text = "one two three four five six seven eight nine ten"
    result = _cap_words(text, 8)
    assert result == "one two three four five six seven eight…"


def test_parse_board_reply_extracts_all_fields():
    reply = (
        "STANCE: WANT\n"
        "OPTION: Bowling\n"
        "REASON: Everyone can play, even non-swimmers\n"
        "FULL: I think Bowling works best because everyone can join in."
    )
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert full_text == "I think Bowling works best because everyone can join in."
    assert stance is not None
    assert stance.stance == "want"
    assert stance.option_id == "bowling"
    assert stance.reason == "Everyone can play, even non-swimmers"
    assert stance.full_text == full_text


def test_parse_board_reply_caps_reason_to_eight_words():
    reply = (
        "STANCE: OK WITH\n"
        "OPTION: Pool\n"
        "REASON: this is a very long reason with way too many words in it\n"
        "FULL: Pool is fine with me."
    )
    _, stance = _parse_board_reply(reply, OPTIONS)
    assert stance.reason == "this is a very long reason with way…"


def test_parse_board_reply_returns_none_stance_on_malformed_output():
    reply = "I think we should go bowling because it's fun for everyone."
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert stance is None
    assert full_text == reply


def test_parse_board_reply_returns_none_stance_on_unknown_option():
    reply = (
        "STANCE: WANT\n"
        "OPTION: Laser Tag\n"
        "REASON: sounds exciting\n"
        "FULL: Laser tag would be so much fun."
    )
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert stance is None
    assert full_text == "Laser tag would be so much fun."


def test_parse_board_reply_matches_option_case_insensitively():
    reply = "STANCE: WANT\nOPTION: bowling\nREASON: fun\nFULL: Bowling please."
    _, stance = _parse_board_reply(reply, OPTIONS)
    assert stance.option_id == "bowling"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_stance.py -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_stance' from 'agent'`

- [ ] **Step 3: Implement**

Edit `agent.py`. Update the imports and add the new instruction template, normalizer, word-capper, and parser:

```python
import re
from typing import List, Optional

from models import Agent as AgentModel, AgentStance, Option, RuleOfEngagement, RuleSet
import config
import llm
```

Add near the existing `_POINT_INSTRUCTION` (after it, before `_DEFAULT_TEMPLATE`):

```python
_STANCE_KEYS = {"WANT": "want", "OKWITH": "ok_with", "WONT": "wont"}


def _board_instruction(options: List[Option]) -> str:
    options_text = "\n".join(f"- {o.label}" for o in options)
    example_option = options[0].label if options else "Option A"
    return f"""

Output format (always required) — this negotiation uses a fixed set of options:
{options_text}

Reply using exactly these four lines, in this order:
STANCE: WANT or OK WITH or WON'T
OPTION: <one of the option names listed above, copied exactly>
REASON: <your reason, no more than 8 words>
FULL: <your full reply, 1-2 sentences>

Example:
STANCE: WANT
OPTION: {example_option}
REASON: Everyone can join in
FULL: I think {example_option} works best because everyone can join in, even people who don't like swimming."""


def _normalize_stance(raw: str) -> Optional[str]:
    key = re.sub(r"[^A-Za-z]", "", raw).upper()
    return _STANCE_KEYS.get(key)


def _cap_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


_BOARD_REPLY_RE = re.compile(
    r"STANCE:\s*(.+?)\s*\n"
    r"OPTION:\s*(.+?)\s*\n"
    r"REASON:\s*(.+?)\s*\n"
    r"FULL:\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_board_reply(reply: str, options: List[Option]) -> tuple[str, Optional[AgentStance]]:
    """Parse a board-mode reply into (full_text, stance). stance is None on malformed
    output or an option the agent invented that isn't in the declared list — the caller
    keeps the agent's previous stance unchanged in that case."""
    m = _BOARD_REPLY_RE.search(reply)
    if not m:
        return reply.strip(), None

    stance_raw, option_raw, reason_raw, full_raw = m.groups()
    full_text = full_raw.strip()

    stance_key = _normalize_stance(stance_raw)
    option_raw = option_raw.strip()
    matched = next((o for o in options if o.label.strip().lower() == option_raw.lower()), None)
    if not stance_key or not matched:
        return full_text, None

    reason = _cap_words(reason_raw.strip(), 8)
    return full_text, AgentStance(stance=stance_key, option_id=matched.id, reason=reason, full_text=full_text)
```

Update `_build_system_prompt` to accept `options` and switch the instruction block:

```python
    def _build_system_prompt(
        self, topic: str, rules: RuleSet, rules_of_engagement: List[RuleOfEngagement], options: List[Option]
    ) -> str:
        rules_text = self._format_rules(rules_of_engagement)
        base_instructions = rules.agent_instructions.strip() or _DEFAULT_SPEAKING_INSTRUCTIONS
        speaking_instructions = base_instructions + (_board_instruction(options) if options else _POINT_INSTRUCTION)
        template = self.prompt_template.strip() or _DEFAULT_TEMPLATE
        ctx = _SafeDict(
            name=self.model.name,
            goal=self.model.goal,
            topic=topic,
            rules=rules_text,
            system_prompt=self.model.system_prompt,
            speaking_instructions=speaking_instructions,
        )
        try:
            return template.format_map(ctx)
        except Exception:
            return template
```

Update `generate_reply` to accept `options` and dispatch to the right parser:

```python
    async def generate_reply(
        self,
        topic: str,
        history_text: str,
        rules: RuleSet,
        rules_of_engagement: List[RuleOfEngagement],
        options: List[Option] = [],
    ) -> tuple[str, str, Optional[AgentStance]]:
        """Return (content, summary, stance). stance is None outside board mode, or when
        the model's board-mode output couldn't be parsed."""
        system_content = self._build_system_prompt(topic, rules, rules_of_engagement, options)

        user_parts = [f"Topic: {topic}"]
        if history_text.strip():
            user_parts.append(f"\nConversation so far:\n{history_text}")
        user_parts.append(
            f"\nIt's your turn, {self.model.name}. Say something short to move the discussion toward a decision."
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        reply = await llm.chat_completion(messages, temperature=0.8, max_tokens=config.AGENT_MAX_TOKENS)
        reply = reply.strip('"').strip("'").strip()

        if options:
            content, stance = _parse_board_reply(reply, options)
            summary = stance.reason if stance else ""
            return content, summary, stance

        content, summary = _parse_reply(reply)
        return content, summary, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_stance.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent_stance.py
git commit -m "feat: add board-mode stance output format and parser

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: DB schema — package options and student avatar_url

**Files:**
- Modify: `db_models.py`
- Modify: `database.py`
- Create: `tests/test_database.py`

**Interfaces:**
- Produces: `PackageDB.options: str` (JSON, default `"[]"`), `User.avatar_url: Optional[str]`, `database.create_db_and_tables(engine=engine)`, `database._migrate(engine=engine)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_database.py`:

```python
from sqlalchemy import inspect
from sqlmodel import create_engine

import database


def test_create_db_and_tables_adds_options_and_avatar_columns(tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_db_and_tables(test_engine)

    insp = inspect(test_engine)
    package_columns = {c["name"] for c in insp.get_columns("package")}
    user_columns = {c["name"] for c in insp.get_columns("user")}

    assert "options" in package_columns
    assert "avatar_url" in user_columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_database.py -v`
Expected: FAIL — either a `TypeError` (function doesn't accept an `engine` arg yet) or, once that's fixed in Step 3, `AssertionError` before the migration lines are added

- [ ] **Step 3: Implement**

Edit `db_models.py` — add `options` to `PackageDB` (after `topic: str`, before `goal`):

```python
class PackageDB(SQLModel, table=True):
    __tablename__ = "package"
    id: Optional[int] = Field(default=None, primary_key=True)
    class_tag: str = Field(index=True)
    name: str
    topic: str
    # JSON array: [{"id": str, "label": str}]. Empty = free-form room (not board mode);
    # 3-6 entries = board mode, enforced by models.validate_options at the API layer.
    options: str = "[]"
    # What a successful outcome looks like for the group as a whole (shown to the
    # referee alongside the topic; distinct from each agent's individual goal).
    goal: str = ""
```

Add `avatar_url` to `User` (after `class_tag`):

```python
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    display_name: str
    class_tag: str = ""
    # Uploaded avatar image, served from /static/avatars/. None = fall back to the emoji pool.
    avatar_url: Optional[str] = Field(default=None, nullable=True)
    system_prompt_override: Optional[str] = Field(default=None, nullable=True)
```

Edit `database.py` to take an optional engine (default the module-level one) and add the two migrations:

```python
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session as DBSession

import config

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, echo=False, connect_args=connect_args)


def _migrate(engine=engine):
    migrations = [
        "ALTER TABLE user ADD COLUMN system_prompt_override TEXT",
        "ALTER TABLE ruleset ADD COLUMN agent_instructions TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN agent_prompt_template TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE formmodule ADD COLUMN preamble TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN goal TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN options TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE user ADD COLUMN avatar_url TEXT",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass


def create_db_and_tables(engine=engine):
    SQLModel.metadata.create_all(engine)
    _migrate(engine)


def get_db():
    with DBSession(engine) as session:
        yield session
```

Note: `SQLModel.metadata.create_all(engine)` already creates brand-new tables (like this test's fresh temp DB) with every currently-declared column, including `options` and `avatar_url` straight from the model classes — the `_migrate` calls for those two columns exist for upgrading an *existing* production DB file that predates this change, matching the pattern every prior migration in this list already follows.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_database.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite so far**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-3)

- [ ] **Step 6: Commit**

```bash
git add db_models.py database.py tests/test_database.py
git commit -m "feat: add package.options and user.avatar_url columns

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Orchestrator wiring — apply and broadcast stances

**Files:**
- Modify: `orchestrator.py`
- Create: `tests/test_orchestrator_stance.py`

**Interfaces:**
- Consumes: `models.AgentStance`, `models.Session`
- Produces: `orchestrator._apply_stance(session: Session, agent_id: str, stance: Optional[AgentStance]) -> Optional[dict]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_stance.py`:

```python
from models import AgentStance, Session
from orchestrator import _apply_stance


def test_apply_stance_stores_and_returns_payload():
    session = Session(topic="t")
    stance = AgentStance(stance="want", option_id="park", reason="fun", full_text="Park sounds fun.")

    payload = _apply_stance(session, "agent-1", stance)

    assert session.stances["agent-1"] == stance
    assert payload == stance.model_dump()


def test_apply_stance_leaves_previous_stance_on_none():
    session = Session(topic="t")
    previous = AgentStance(stance="want", option_id="park", reason="fun", full_text="Park sounds fun.")
    session.stances["agent-1"] = previous

    payload = _apply_stance(session, "agent-1", None)

    assert session.stances["agent-1"] == previous  # unchanged
    assert payload is None


def test_apply_stance_returns_none_for_agent_with_no_prior_stance_and_none_input():
    session = Session(topic="t")
    payload = _apply_stance(session, "agent-1", None)
    assert payload is None
    assert "agent-1" not in session.stances
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator_stance.py -v`
Expected: FAIL with `ImportError: cannot import name '_apply_stance' from 'orchestrator'`

- [ ] **Step 3: Implement `_apply_stance`**

Edit `orchestrator.py` — add near the top, after the imports and the `_clear_step_signal` function:

```python
def _apply_stance(session: Session, agent_id: str, stance) -> dict | None:
    """Update session.stances if a valid stance was parsed; return its dict payload for
    the broadcast event, or None (board mode inactive, or the reply didn't parse — in
    which case the agent's previous stance, if any, is left untouched)."""
    if stance is None:
        return None
    session.stances[agent_id] = stance
    return stance.model_dump()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator_stance.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire `_apply_stance` and `session.options` into every `generate_reply` call site**

Edit `orchestrator.py`, `_run_realtime` (the sequential reaction loop):

```python
        await broadcast({"type": "agent_thinking", "agent_id": speaker.id})
        content, summary, stance = await actors[speaker.id].generate_reply(
            session.topic,
            _format_history(session, actors),
            session.rules,
            session.rules_of_engagement,
            session.options,
        )
        session.history.append(Message(agent_id=speaker.id, content=content, turn=session.turn))
        await broadcast({
            "type": "agent_speak",
            "agent_id": speaker.id,
            "content": content,
            "summary": summary,
            "turn": session.turn,
            "stance": _apply_stance(session, speaker.id, stance),
        })
        await asyncio.sleep(3)
```

Edit `_run_step_by_step`'s main per-circle loop:

```python
            session.turn += 1
            await broadcast({"type": "agent_generating", "agent_id": speaker.id, "done": False})
            content, summary, stance = await actors[speaker.id].generate_reply(
                session.topic,
                _format_history(session, actors),
                session.rules,
                session.rules_of_engagement,
                session.options,
            )
            session.history.append(Message(agent_id=speaker.id, content=content, turn=session.turn))
            await broadcast({"type": "agent_generating", "agent_id": speaker.id, "done": True})
            events.append({
                "type": "agent_speak",
                "agent_id": speaker.id,
                "content": content,
                "summary": summary,
                "turn": session.turn,
                "stance": _apply_stance(session, speaker.id, stance),
            })
```

Edit `_agent_propose`:

```python
async def _agent_propose(
    agent: AgentModel,
    actor: AgentActor,
    session: Session,
    turn: int,
    broadcast,
    rules_of_engagement,
):
    await broadcast({"type": "agent_thinking", "agent_id": agent.id})
    content, summary, stance = await actor.generate_reply(
        session.topic, "", session.rules, rules_of_engagement, session.options
    )
    await broadcast({
        "type": "agent_speak",
        "agent_id": agent.id,
        "content": content,
        "summary": summary,
        "turn": turn,
        "stance": _apply_stance(session, agent.id, stance),
    })
    return agent.id, content
```

Edit `_agent_propose_queued` (currently unused by any caller, kept consistent for whoever picks it up next):

```python
async def _agent_propose_queued(agent: AgentModel, actor: AgentActor, session: Session):
    """Generate a simultaneous opening proposal without broadcasting it immediately."""
    content, summary, stance = await actor.generate_reply(
        session.topic, "", session.rules, session.rules_of_engagement, session.options
    )
    return agent.id, content, summary, stance
```

Edit `_agent_propose_queued_with_indicator`:

```python
async def _agent_propose_queued_with_indicator(agent: AgentModel, actor: AgentActor, session: Session, broadcast):
    """Generate a simultaneous opening proposal and show a progress indicator."""
    await broadcast({"type": "agent_generating", "agent_id": agent.id, "done": False})
    try:
        content, summary, stance = await actor.generate_reply(
            session.topic, "", session.rules, session.rules_of_engagement, session.options
        )
    finally:
        await broadcast({"type": "agent_generating", "agent_id": agent.id, "done": True})
    return agent.id, content, summary, stance
```

Edit its caller inside `_run_step_by_step`'s simultaneous-proposal opening block:

```python
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            agent_id, content, summary, stance = result
            session.history.append(Message(agent_id=agent_id, content=content, turn=session.turn))
            opening_events.append({
                "type": "agent_speak",
                "agent_id": agent_id,
                "content": content,
                "summary": summary,
                "turn": session.turn,
                "stance": _apply_stance(session, agent_id, stance),
            })
```

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests) — this step has no new automated coverage of the 5 call sites themselves (they're `await`-heavy integration code exercising the live LLM/broadcast path); Task 11 verifies them end-to-end live.

- [ ] **Step 7: Commit**

```bash
git add orchestrator.py tests/test_orchestrator_stance.py
git commit -m "feat: thread board-mode stances through the orchestrator broadcast events

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Package API — options field, load/reset wiring, agent avatar_url

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `models.validate_options`, `models.Option`, `db_models.PackageDB.options`, `db_models.User.avatar_url`
- Produces: `GET/POST/PUT /api/admin/packages` now read/write `options`; `POST /api/admin/packages/{id}/load` populates `session.options`/`session.stances`; `models.Agent.avatar_url`

- [ ] **Step 1: Add `options` to the package endpoints**

Edit `main.py` imports to bring in the new validator and the `Option` model (also needed later in this task, for `load_package`):

```python
from models import Agent, Option, RuleOfEngagement, RuleSet, Session, validate_options
```

Edit `list_packages` (the response dict comprehension):

```python
    return [{"id": p.id, "class_tag": p.class_tag, "name": p.name, "topic": p.topic, "goal": p.goal,
             "options": json.loads(p.options), "constraints": json.loads(p.constraints),
             "rule_set_id": p.rule_set_id, "agent_prompt_template": p.agent_prompt_template}
            for p in packages]
```

Edit `create_package`:

```python
@app.post("/api/admin/packages")
async def create_package(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    options = body.get("options", [])
    try:
        validate_options(options)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pkg = PackageDB(
        class_tag=body.get("class_tag", ""),
        name=body.get("name", "New package"),
        topic=body.get("topic", ""),
        goal=body.get("goal", ""),
        options=json.dumps(options),
        constraints=json.dumps(body.get("constraints", [])),
        rule_set_id=body.get("rule_set_id"),
        agent_prompt_template=body.get("agent_prompt_template", ""),
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return {"id": pkg.id, "class_tag": pkg.class_tag, "name": pkg.name, "topic": pkg.topic, "goal": pkg.goal,
            "options": json.loads(pkg.options), "constraints": json.loads(pkg.constraints),
            "rule_set_id": pkg.rule_set_id, "agent_prompt_template": pkg.agent_prompt_template}
```

Edit `update_package`:

```python
@app.put("/api/admin/packages/{pkg_id}")
async def update_package(pkg_id: int, request: Request,
                         db: DBSession = Depends(get_db)):
    _require_admin(request)
    pkg = db.get(PackageDB, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404)
    body = await request.json()
    for field in ("name", "topic", "goal", "rule_set_id", "agent_prompt_template"):
        if field in body:
            setattr(pkg, field, body[field])
    if "options" in body:
        try:
            validate_options(body["options"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        pkg.options = json.dumps(body["options"])
    if "constraints" in body:
        pkg.constraints = json.dumps(body["constraints"])
    db.commit()
    return {"id": pkg.id, "class_tag": pkg.class_tag, "name": pkg.name, "topic": pkg.topic, "goal": pkg.goal,
            "options": json.loads(pkg.options), "constraints": json.loads(pkg.constraints),
            "rule_set_id": pkg.rule_set_id, "agent_prompt_template": pkg.agent_prompt_template}
```

- [ ] **Step 2: Add `avatar_url` to `models.Agent` and pass it through on load**

Edit `models.py`'s `Agent` class:

```python
class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    avatar: str = "🤖"
    avatar_url: Optional[str] = None
    goal: str
    system_prompt: str
```

- [ ] **Step 3: Wire `options`/`stances` and `avatar_url` into `load_package`**

Edit `main.py`'s `load_package`, in the per-student agent-building loop and the `Session(...)` construction:

```python
    for i, uid in enumerate(student_ids):
        user = db.get(User, int(uid))
        if not user:
            continue
        sub = db.exec(select(FormSubmission).where(FormSubmission.user_id == user.id)).first()
        answers = json.loads(sub.answers) if sub else {}
        base_prompt = user.system_prompt_override or render_system_prompt(template, user.display_name, answers)
        agents.append(Agent(
            name=user.display_name,
            avatar=avatar_pool[i % len(avatar_pool)],
            avatar_url=user.avatar_url,
            goal="Participate in the negotiation.",
            system_prompt=base_prompt + agent_rules_text,
        ))
        roster_ids.append(user.id)

    session = Session(
        topic=pkg.topic,
        goal=pkg.goal,
        agents=agents,
        rules=RuleSet(agent_instructions=rule_agent_instructions),
        rules_of_engagement=[RuleOfEngagement(**r) for r in all_roe],
        loaded_package_id=pkg.id,
        loaded_package_name=pkg.name,
        agent_prompt_template=pkg.agent_prompt_template or "",
        options=[Option(**o) for o in json.loads(pkg.options)],
    )
```

- [ ] **Step 4: Preserve `options` across a session reset**

Edit `reset_session_route`:

```python
    session = Session(
        topic=session.topic,
        goal=session.goal,
        agents=session.agents,
        rules=session.rules,
        rules_of_engagement=session.rules_of_engagement,
        loaded_package_id=session.loaded_package_id,
        loaded_package_name=session.loaded_package_name,
        agent_prompt_template=session.agent_prompt_template,
        options=session.options,
    )
```

(`stances` is intentionally *not* carried over — a reset clears round history, so every agent goes back to the undecided zone, matching what a fresh load already does.)

- [ ] **Step 5: Manual verification**

This task has no dedicated automated test (it's config plumbing through endpoints already covered structurally by Tasks 1-4's unit tests). Verify manually once Task 11's admin UI exists to create a package with options — tracked there.

- [ ] **Step 6: Commit**

```bash
git add main.py models.py
git commit -m "feat: wire package options and agent avatar_url through session load/reset

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Avatar upload endpoint

**Files:**
- Modify: `main.py`

**Interfaces:**
- Produces: `POST /api/admin/users/{user_id}/avatar` (multipart file upload) → `{"avatar_url": str}`; `GET/POST/PUT /api/admin/users` now include `avatar_url`

- [ ] **Step 1: Add the avatar directory and upload endpoint**

Edit `main.py`'s app-setup section (right after the existing `static_dir` mount):

```python
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

AVATAR_DIR = os.path.join(static_dir, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
```

Add `UploadFile`, `File` to the fastapi import:

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, UploadFile, File
```

Add the endpoint near the other Users endpoints, after `update_user`:

```python
@app.post("/api/admin/users/{user_id}/avatar")
async def upload_avatar(user_id: int, request: Request, db: DBSession = Depends(get_db),
                        file: UploadFile = File(...)):
    _require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        raise HTTPException(status_code=400, detail="Unsupported image type. Use PNG, JPEG, GIF, or WebP.")

    dest_path = os.path.join(AVATAR_DIR, f"{user_id}{ext}")
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    user.avatar_url = f"/static/avatars/{user_id}{ext}"
    db.commit()
    return {"avatar_url": user.avatar_url}
```

- [ ] **Step 2: Include `avatar_url` in the existing user endpoints**

Edit `list_users`:

```python
@app.get("/api/admin/users")
async def list_users(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    users = db.exec(select(User)).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name,
             "class_tag": u.class_tag, "avatar_url": u.avatar_url} for u in users]
```

Edit `create_user`'s return statement:

```python
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "class_tag": user.class_tag, "avatar_url": user.avatar_url}
```

Edit `update_user`'s return statement:

```python
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "class_tag": user.class_tag, "avatar_url": user.avatar_url}
```

- [ ] **Step 3: Manual verification**

No dedicated automated test — file-upload endpoints need a real multipart client and this project has no HTTP test-client pattern yet (see the spec's testing section: automated coverage is scoped to the stance parser and options validation). Verified live in Task 11 via the admin UI built in Task 10.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add student avatar upload endpoint

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend — shared avatar element builder with image support

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Produces: `buildAvatarEl(id, emoji, name, xPercent, yPercent, extraClass, onClick, avatarUrl) -> HTMLElement`, `buildAgentAvatarEl(agent, xPercent, yPercent) -> HTMLElement`
- Consumes (later tasks): both board mode (Task 8) and step-by-step board updates (Task 9) build avatar elements exclusively through these two functions

This task only refactors the **existing free-form room** to go through the shared builder — board mode itself lands in Task 8. Doing the image-avatar plumbing here, against the simpler existing renderer, keeps Task 8 focused on the new layout math.

- [ ] **Step 1: Add the shared builder functions**

Edit `static/app.js` — add above `renderAvatars()`:

```javascript
function buildAvatarEl(id, emoji, name, xPercent, yPercent, extraClass, onClick, avatarUrl) {
  const el = document.createElement("div");
  el.className = `avatar${extraClass ? " " + extraClass : ""}`;
  el.id = `avatar-${id}`;
  el.style.left = `${xPercent}%`;
  el.style.top = `${yPercent}%`;

  const face = document.createElement("div");
  face.className = "avatar-face";
  if (avatarUrl) {
    const img = document.createElement("img");
    img.src = avatarUrl;
    img.alt = name;
    face.appendChild(img);
  } else {
    face.textContent = emoji;
  }

  const nameEl = document.createElement("div");
  nameEl.className = "avatar-name";
  nameEl.textContent = name;

  el.appendChild(face);
  el.appendChild(nameEl);
  if (onClick) el.addEventListener("click", onClick);
  return el;
}

function buildAgentAvatarEl(agent, xPercent, yPercent) {
  return buildAvatarEl(
    agent.id, agent.avatar, agent.name, xPercent, yPercent, "",
    () => showTranscript(agent.id), agent.avatar_url
  );
}
```

- [ ] **Step 2: Refactor the existing free-form renderer to use them**

Replace the body of `renderAvatars()` (the per-agent `el`/`face`/`name` construction) — the function signature and the `agents.length === 0` early return stay the same:

```javascript
function renderAvatars() {
  if (!state.session) return;
  const container = els.avatarsContainer;
  container.innerHTML = "";
  container.classList.remove("board-mode");

  const agents = state.session.agents;
  if (agents.length === 0) {
    container.innerHTML = '<div class="empty-room">Add agents to start</div>';
    return;
  }

  const radius = 28; // percent of container
  const center = 50;

  agents.forEach((agent, i) => {
    const angle = (2 * Math.PI * i) / agents.length - Math.PI / 2;
    const left = center + radius * Math.cos(angle);
    const top = center + radius * Math.sin(angle);
    container.appendChild(buildAgentAvatarEl(agent, left, top));
  });

  // Add a clickable referee avatar in the center.
  container.appendChild(
    buildAvatarEl("referee", "🧐", "Referee", 50, 50, "referee-avatar",
      () => showRefereeEvaluations())
  );
}
```

- [ ] **Step 3: Add `<img>` sizing to styles.css**

Edit `static/styles.css` — add right after the existing `.avatar-face` rule (around line 357):

```css
.avatar-face img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}
```

- [ ] **Step 4: Manual verification**

Start the app (`python main.py`), log in as admin, load any existing package (e.g. the `demo-party` seed), confirm the free-form circular room renders exactly as before (emoji avatars, click-to-transcript, referee center) — this task changes no visible behavior yet, it's a pure refactor. Confirmed via the Browser tool as part of Task 11's final pass; no need to block here since there's no `avatar_url` data yet to visually check against (that arrives with Task 10's upload UI).

- [ ] **Step 5: Commit**

```bash
git add static/app.js static/styles.css
git commit -m "refactor: share avatar-element construction between room and board renderers

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Frontend — the perimeter-room board renderer

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Consumes: `buildAvatarEl`, `buildAgentAvatarEl` (Task 7); `state.session.options`, `state.session.stances`
- Produces: `isBoardMode() -> bool`, `computeBoardPositions(session) -> {referee: {x,y}, options: [{opt, x, y}], agents: Map<agentId, {x, y, stance}>}`, `renderBoard()`, `applyBoardPositions()`

- [ ] **Step 1: Add the board-mode detection and position-computation function**

Edit `static/app.js` — add above `renderAvatars()`:

```javascript
const BOARD_LABEL_RADIUS = 42;       // percent — where option labels sit, near the rim
const BOARD_START_RADIUS = 34;       // percent — first (outermost) avatar ring in a wedge
const BOARD_RADIUS_STEP = 11;        // percent — each ring steps this far inward
const BOARD_MIN_RADIUS = 20;         // percent — never place an avatar closer than this to center
const BOARD_UNDECIDED_RADIUS = 14;   // percent — the undecided ring around the referee
const BOARD_AVATARS_PER_RING = 3;    // avatars per ring before wrapping to the next ring inward
const BOARD_WEDGE_ARC_SPREAD = 0.5;  // radians — angular spread of avatars within one ring

function isBoardMode() {
  return !!(state.session && state.session.options && state.session.options.length > 0);
}

function computeBoardPositions(session) {
  const options = session.options;
  const stances = session.stances || {};
  const n = options.length;

  const byOption = new Map(options.map((o) => [o.id, []]));
  const undecided = [];
  session.agents.forEach((agent) => {
    const stance = stances[agent.id];
    if (stance && byOption.has(stance.option_id)) {
      byOption.get(stance.option_id).push(agent);
    } else {
      undecided.push(agent);
    }
  });

  const agentPositions = new Map();

  undecided.forEach((agent, i) => {
    const angle = (2 * Math.PI * i) / Math.max(undecided.length, 1) - Math.PI / 2;
    agentPositions.set(agent.id, {
      x: 50 + BOARD_UNDECIDED_RADIUS * Math.cos(angle),
      y: 50 + BOARD_UNDECIDED_RADIUS * Math.sin(angle),
    });
  });

  const optionPositions = options.map((opt, i) => {
    const theta = (2 * Math.PI * i) / n - Math.PI / 2;
    const wedgeAgents = byOption.get(opt.id);

    wedgeAgents.forEach((agent, k) => {
      const ring = Math.floor(k / BOARD_AVATARS_PER_RING);
      const radius = Math.max(BOARD_START_RADIUS - ring * BOARD_RADIUS_STEP, BOARD_MIN_RADIUS);
      const ringStart = ring * BOARD_AVATARS_PER_RING;
      const ringCount = Math.min(BOARD_AVATARS_PER_RING, wedgeAgents.length - ringStart);
      const posInRing = k - ringStart;
      const angleOffset = ringCount > 1 ? (posInRing / (ringCount - 1) - 0.5) * BOARD_WEDGE_ARC_SPREAD : 0;
      const angle = theta + angleOffset;
      agentPositions.set(agent.id, {
        x: 50 + radius * Math.cos(angle),
        y: 50 + radius * Math.sin(angle),
      });
    });

    return {
      opt,
      x: 50 + BOARD_LABEL_RADIUS * Math.cos(theta),
      y: 50 + BOARD_LABEL_RADIUS * Math.sin(theta),
    };
  });

  return { referee: { x: 50, y: 50 }, options: optionPositions, agents: agentPositions };
}
```

- [ ] **Step 2: Add the full-build and incremental-update renderers**

Add below `computeBoardPositions`:

```javascript
function renderBoard() {
  const container = els.avatarsContainer;
  container.innerHTML = "";
  container.classList.add("board-mode");

  const agents = state.session.agents;
  if (agents.length === 0) {
    container.innerHTML = '<div class="empty-room">Add agents to start</div>';
    return;
  }

  const positions = computeBoardPositions(state.session);

  container.appendChild(
    buildAvatarEl("referee", "🧐", "Referee", positions.referee.x, positions.referee.y,
      "referee-avatar", () => showRefereeEvaluations())
  );

  positions.options.forEach(({ opt, x, y }) => {
    const label = document.createElement("div");
    label.className = "board-option-label";
    label.textContent = opt.label;
    label.style.left = `${x}%`;
    label.style.top = `${y}%`;
    container.appendChild(label);
  });

  agents.forEach((agent) => {
    const pos = positions.agents.get(agent.id);
    const el = buildAgentAvatarEl(agent, pos.x, pos.y);
    const stance = (state.session.stances || {})[agent.id];
    if (stance && stance.reason) {
      const chip = document.createElement("div");
      chip.className = "stance-chip";
      chip.textContent = stance.reason;
      el.appendChild(chip);
    }
    container.appendChild(el);
  });
}

function applyBoardPositions() {
  if (!isBoardMode()) return;
  const positions = computeBoardPositions(state.session);

  const refereeEl = document.getElementById("avatar-referee");
  if (refereeEl) {
    refereeEl.style.left = `${positions.referee.x}%`;
    refereeEl.style.top = `${positions.referee.y}%`;
  }

  positions.agents.forEach((pos, agentId) => {
    const el = document.getElementById(`avatar-${agentId}`);
    if (!el) return;
    el.style.left = `${pos.x}%`;
    el.style.top = `${pos.y}%`;

    const stance = (state.session.stances || {})[agentId];
    let chip = el.querySelector(".stance-chip");
    if (stance && stance.reason) {
      if (!chip) {
        chip = document.createElement("div");
        chip.className = "stance-chip";
        el.appendChild(chip);
      }
      chip.textContent = stance.reason;
    } else if (chip) {
      chip.remove();
    }
  });
}
```

- [ ] **Step 3: Dispatch to the board renderer from `renderAvatars()`**

Edit `static/app.js` — `renderAvatars()` gains a board-mode check at the very top, before the free-form body added in Task 7 (that body, including its `container.classList.remove("board-mode")` line, is unchanged and now only runs when board mode is off):

```javascript
function renderAvatars() {
  if (!state.session) return;
  if (isBoardMode()) {
    renderBoard();
    return;
  }
  const container = els.avatarsContainer;
  container.innerHTML = "";
  container.classList.remove("board-mode");
  ...
```

(the rest of the function — the free-form loop and referee avatar — is unchanged from Task 7)

- [ ] **Step 4: Add board-mode CSS**

Edit `static/styles.css` — add after the `.avatar-face img` rule added in Task 7:

```css
.board-option-label {
  position: absolute;
  transform: translate(-50%, -50%);
  padding: 4px 10px;
  background: rgba(79, 70, 229, 0.92);
  color: white;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: var(--shadow);
  pointer-events: none;
  z-index: 2;
}

.stance-chip {
  margin-top: 3px;
  padding: 1px 6px;
  background: rgba(30, 27, 75, 0.9);
  color: #e0e7ff;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 600;
  white-space: nowrap;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.avatars-container.board-mode .avatar {
  z-index: 3;
}
```

- [ ] **Step 5: Manual verification**

Deferred to Task 11 (needs a package with `options` set, which the admin UI from Task 10 provides) — this task's geometry is exercised together with the crowding stress-test there rather than in isolation, since a meaningful visual check needs real option/agent data.

- [ ] **Step 6: Commit**

```bash
git add static/app.js static/styles.css
git commit -m "feat: add perimeter-room board layout renderer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Frontend — wire live stance updates into the board

**Files:**
- Modify: `static/app.js`

**Interfaces:**
- Consumes: `applyBoardPositions` (Task 8), the `stance` field now present on `agent_speak` WebSocket messages (Task 4)

- [ ] **Step 1: Update the `agent_speak` handler**

Edit `static/app.js`'s `handleMessage` — the `case "agent_speak":` branch gains stance handling before the existing bubble/transcript logic:

```javascript
    case "agent_speak":
      setThinking(msg.agent_id, false);
      document.querySelectorAll(".referee-warning").forEach((w) => w.remove());
      if (msg.stance) {
        state.session.stances = state.session.stances || {};
        state.session.stances[msg.agent_id] = msg.stance;
        applyBoardPositions();
      }
      showSpeech(msg.agent_id, msg.content, { persistent: true, summary: msg.summary });
      addTranscript(msg.agent_id, msg.content);
      log(`💬 ${getAgentName(msg.agent_id)}: ${msg.content}`);
      break;
```

No other WebSocket case needs a change: step-by-step mode's queued events are plain `agent_speak` messages replayed one at a time through the same `broadcast(event)` call in `orchestrator._play_queue` (see `orchestrator.py`'s `_run_step_by_step`), so they already carry `stance` and land in this same handler at reveal time — one keypress moves the avatar and shows the speech bubble together, satisfying A5's "board updates in lockstep with the existing reveal."

- [ ] **Step 2: Manual verification**

Deferred to Task 11 (needs a live or step-by-step round against a board-mode package).

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: move board avatars live as stance updates arrive

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Admin UI — package options editor and student avatar upload

**Files:**
- Modify: `static/admin.js`
- Modify: `static/admin.html`

**Interfaces:**
- Produces: package edit cards gain an options list editor (mirrors the existing constraints editor); student cards gain an avatar upload control

- [ ] **Step 1: Add the options editor to the package edit card**

Edit `static/admin.js` — add `renderOptions`, `addOption`, `removeOption`, `getOptions` near the existing `renderConstraints`/`addConstraint`/`removeConstraint`/`getConstraints` functions:

```javascript
function renderOptions(pkgId, options) {
  const container = document.getElementById(`pkg-options-${pkgId}`);
  container.innerHTML = "";
  options.forEach((o, idx) => {
    const row = document.createElement("div");
    row.className = "rule-item";
    row.innerHTML = `
      <div class="rule-item-fields">
        <input class="admin-input" placeholder="Option label (e.g. Bowling)" value="${esc(o.label)}" data-idx="${idx}" data-prop="label">
      </div>
      <button class="btn btn-danger" style="align-self:start" onclick="removeOption(${pkgId},${idx})">✕</button>
    `;
    container.appendChild(row);
  });
}

function addOption(pkgId) {
  const container = document.getElementById(`pkg-options-${pkgId}`);
  const count = container.querySelectorAll(".rule-item").length;
  if (count >= 6) { alert("A board-mode package can have at most 6 options."); return; }
  const idx = count;
  const row = document.createElement("div");
  row.className = "rule-item";
  row.innerHTML = `
    <div class="rule-item-fields">
      <input class="admin-input" placeholder="Option label (e.g. Bowling)" data-idx="${idx}" data-prop="label">
    </div>
    <button class="btn btn-danger" style="align-self:start" onclick="removeOption(${pkgId},${idx})">✕</button>
  `;
  container.appendChild(row);
}

function removeOption(pkgId, idx) {
  const items = document.querySelectorAll(`#pkg-options-${pkgId} .rule-item`);
  if (items[idx]) items[idx].remove();
}

function getOptions(pkgId) {
  const items = document.querySelectorAll(`#pkg-options-${pkgId} .rule-item`);
  const result = [];
  items.forEach((item, i) => {
    const label = item.querySelector('[data-prop="label"]').value.trim();
    if (label) result.push({ id: `opt-${i}`, label });
  });
  return result;
}
```

Edit the package card template (inside `loadPackages()`, right after the `Hard constraints` section and before `Agent identity template`):

```javascript
        <div class="section-title">Hard constraints (issue-specific)</div>
        <div id="pkg-constraints-${pkg.id}"></div>
        <button class="btn btn-secondary" style="margin-bottom:12px" onclick="addConstraint(${pkg.id})">+ Add constraint</button>
        <div class="section-title" style="margin-top:16px">Board options <span style="font-weight:400;color:var(--text-muted)">(3–6 named things agents can back — leave empty for the free-form room)</span></div>
        <div id="pkg-options-${pkg.id}"></div>
        <button class="btn btn-secondary" style="margin-bottom:12px" onclick="addOption(${pkg.id})">+ Add option</button>
        <div class="section-title" style="margin-top:16px">Agent identity template</div>
```

Edit `loadPackages()` to render the options rows (right after the existing `renderConstraints(pkg.id, pkg.constraints || [])` call):

```javascript
    renderConstraints(pkg.id, pkg.constraints || []);
    renderOptions(pkg.id, pkg.options || []);
```

Edit `savePackage` to send `options`:

```javascript
async function savePackage(pkgId) {
  const rsVal = document.getElementById(`pkg-rs-${pkgId}`).value;
  const options = getOptions(pkgId);
  if (options.length > 0 && (options.length < 3 || options.length > 6)) {
    alert("Board options must be either empty (free-form room) or between 3 and 6 entries.");
    return;
  }
  await api("PUT", `/api/admin/packages/${pkgId}`, {
    name: document.getElementById(`pkg-name-${pkgId}`).value,
    topic: document.getElementById(`pkg-topic-${pkgId}`).value,
    goal: document.getElementById(`pkg-goal-${pkgId}`).value,
    rule_set_id: rsVal ? parseInt(rsVal, 10) : null,
    constraints: getConstraints(pkgId),
    options: options,
    agent_prompt_template: document.getElementById(`pkg-template-${pkgId}`).value,
  });
  loadPackages();
}
```

- [ ] **Step 2: Add the avatar upload control to the student edit card**

Edit `static/admin.js`'s `loadStudents()` — extend the card template's edit section (inside `id="edit-student-${u.id}"`, after the `form-row cols-3` block and before the `Save` button):

```javascript
      <div id="edit-student-${u.id}" class="hidden" style="margin-top:12px">
        <div class="form-row cols-3">
          <div><span class="field-label">Display name</span>
               <input class="admin-input" id="edit-name-${u.id}" value="${esc(u.display_name)}"></div>
          <div><span class="field-label">Class</span>
               <select class="admin-select" id="edit-class-${u.id}" style="width:100%">
                 ${allClasses.map((c) => `<option value="${esc(c.tag)}" ${c.tag === u.class_tag ? "selected" : ""}>${esc(c.tag)}${c.name ? " — " + esc(c.name) : ""}</option>`).join("")}
               </select></div>
          <div><span class="field-label">New password (leave blank to keep)</span>
               <input class="admin-input" id="edit-pass-${u.id}" type="password" placeholder="unchanged"></div>
        </div>
        <div class="form-row cols-2" style="align-items:flex-end;margin-top:8px">
          <div>
            <span class="field-label">Avatar image (used on the board instead of the emoji)</span>
            <input class="admin-input" id="edit-avatar-${u.id}" type="file" accept="image/png,image/jpeg,image/gif,image/webp">
          </div>
          <div>
            ${u.avatar_url ? `<img src="${esc(u.avatar_url)}" alt="current avatar" style="width:40px;height:40px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:8px">` : ""}
            <button class="btn btn-secondary" onclick="uploadStudentAvatar(${u.id})">Upload</button>
          </div>
        </div>
        <button class="btn btn-primary" style="margin-top:8px" onclick="saveStudent(${u.id})">Save</button>
      </div>
```

Add the upload function near `saveStudent`:

```javascript
async function uploadStudentAvatar(id) {
  const input = document.getElementById(`edit-avatar-${id}`);
  const file = input.files[0];
  if (!file) { alert("Choose an image file first."); return; }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/admin/users/${id}/avatar`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || `Upload failed (${res.status})`);
    return;
  }
  loadStudents();
}
```

- [ ] **Step 3: Manual verification**

Verified together with Task 11's end-to-end pass.

- [ ] **Step 4: Commit**

```bash
git add static/admin.js
git commit -m "feat: add package options editor and student avatar upload to the admin panel

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: End-to-end verification and crowding stress test

**Files:** none (verification only — fixes for anything found go back into the relevant task's files)

- [ ] **Step 1: Run the full automated test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-4)

- [ ] **Step 2: Boot the app and seed demo data**

```bash
python seed_demo.py
python main.py
```

Using the Browser tool, log in as admin at `http://127.0.0.1:8000/login`.

- [ ] **Step 3: Confirm non-board packages are unaffected**

Go to Admin → Packages, filter by class `demo-party`, Load for Session with all 4 students, go to `/session`. Confirm the room renders exactly as it did before this feature: free-form circular layout, emoji avatars, no option labels or stance chips anywhere on screen. This is the regression check for the "board mode is opt-in" constraint.

- [ ] **Step 4: Create a board-mode package and run it live**

In Admin → Packages, create a new package for the `demo-party` class with 4 options (e.g. "Park Party", "Bowling", "Pool", "Arcade") using the new options editor, save it, and Load for Session with all 4 seeded students. On `/session`, confirm:
- all 4 avatars start in the undecided ring around the referee (no option backed yet)
- Start Round in real-time mode; as each agent speaks, its avatar animates outward into the wedge matching its stated option, and a short reason chip appears under it
- clicking an avatar still opens its full transcript (unchanged behavior from the free-form room)

If any agent's reply fails to parse into a valid stance (visible as an avatar that never leaves the undecided ring despite having spoken), check `llm_calls.jsonl` for the raw model output and adjust the prompt wording in `agent._board_instruction` if the model is consistently misformatting — this is the kind of model-compliance tuning the spec's fallback behavior exists for for.

- [ ] **Step 5: Stress-test wedge crowding with a synthetic worst case**

The real run in Step 4 only has 4 agents / 4 options, which won't naturally produce a crowded wedge. Use the Browser tool's JavaScript execution to inject a synthetic 8-agent/6-option worst case directly into the running page and re-render, without needing 8 real students or controllable LLM output:

```javascript
// Run in the browser console via the Browser tool against the loaded /session page
state.session.options = [
  {id: "opt-0", label: "Park Party"}, {id: "opt-1", label: "Bowling"},
  {id: "opt-2", label: "Pool"}, {id: "opt-3", label: "Arcade"},
  {id: "opt-4", label: "Museum"}, {id: "opt-5", label: "Home"},
];
state.session.agents = state.session.agents.slice(0, 1).concat(
  Array.from({length: 7}, (_, i) => ({
    id: `synth-${i}`, name: `Synth ${i}`, avatar: "🤖", avatar_url: null,
    goal: "", system_prompt: "",
  }))
).slice(0, 8);
state.session.stances = {};
const ids = state.session.agents.map(a => a.id);
// Worst case: 6 of 8 agents back the same option.
[0,1,2,3,4,5].forEach((i) => {
  state.session.stances[ids[i]] = {stance: "want", option_id: "opt-1", reason: "everyone likes bowling here", full_text: ""};
});
state.session.stances[ids[6]] = {stance: "ok_with", option_id: "opt-2", reason: "pool is fine too", full_text: ""};
renderBoard();
```

Take a screenshot of the result. Confirm: the 6 avatars backing "Bowling" pack into rings that step inward toward center without overlapping each other, the referee, or the undecided ring, and the "Bowling" label stays legible at the rim. If avatars overlap or spill past the container edge, adjust `BOARD_START_RADIUS`, `BOARD_RADIUS_STEP`, `BOARD_MIN_RADIUS`, or `BOARD_AVATARS_PER_RING` in `static/app.js` (Task 8) and re-run this step.

- [ ] **Step 6: Confirm step-by-step mode drives the board in lockstep**

Reload `/session` (clears the synthetic state), switch Mode to "Step-by-step", Start Round. Confirm each Next keypress reveals exactly one agent's speech bubble *and* moves its avatar into its wedge in the same keypress — not staggered, not all-at-once.

- [ ] **Step 7: Confirm avatar image upload renders on the board**

In Admin → Students, upload a small test image for one of the 4 seeded students (any small PNG). Reload `/session` (or load the board package again) and confirm that student's avatar shows the uploaded image instead of the emoji, both in the undecided ring and after it takes a stance.

- [ ] **Step 8: Fix and re-verify**

Any issues found in Steps 3-7 get fixed in the relevant task's file(s) and this task's steps re-run until all pass. Commit fixes individually with a message describing what was wrong (e.g. `fix: board wedge radius overlapped the undecided ring at 6 avatars`).

- [ ] **Step 9: Final commit**

```bash
git add -A
git commit -m "chore: verify negotiation board legibility end-to-end

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(Skip this commit if Step 8 needed no fixes and there's nothing new to stage.)
