import asyncio
import json
import os
from collections import UserDict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session as DBSession, select
from starlette.middleware.sessions import SessionMiddleware

import config
from auth import (
    hash_password, verify_password,
    set_session, get_session_user, clear_session,
    redirect_if_not_admin, redirect_if_not_authenticated,
)
from database import create_db_and_tables, engine, get_db
from db_models import (
    User, FormModule, SystemPromptTemplate, FormSubmission,
    RuleSetDB, PackageDB, RunDB, ClassTagDB,
)
from models import Agent, RuleOfEngagement, RuleSet, Session
from orchestrator import run_round, advance_step


# ── In-memory negotiation state ───────────────────────────────────────────────

session = Session(topic="Load a package from the Admin page to begin.")

# Buffer for the run currently in progress; flushed to DB on round_over.
_run_buffer: dict = {"active": False, "id": None, "events": [], "started_at": None,
                     "package_id": None, "package_name": "", "class_tag": "", "roster_ids": []}

# Reference to the active round task so it can be cancelled on stop/restart.
_round_task: asyncio.Task | None = None


def _cancel_round() -> None:
    """Cancel the active round task if one is running."""
    global _round_task
    if _round_task and not _round_task.done():
        _round_task.cancel()
    _round_task = None


# ── System-prompt rendering ───────────────────────────────────────────────────

class _DefaultDict(UserDict):
    def __missing__(self, key):
        return f"[{key} not provided]"


def render_system_prompt(template: str, display_name: str, answers: dict) -> str:
    ctx = _DefaultDict(answers)
    ctx["display_name"] = display_name
    try:
        return template.format_map(ctx)
    except Exception:
        return template


# ── Run tracking ──────────────────────────────────────────────────────────────

def _start_run():
    _run_buffer["active"] = True
    _run_buffer["id"] = None
    _run_buffer["events"] = []
    _run_buffer["started_at"] = datetime.utcnow()
    _run_buffer["package_id"] = session.loaded_package_id
    _run_buffer["package_name"] = session.loaded_package_name or ""
    _run_buffer["class_tag"] = ""
    _run_buffer["roster_ids"] = []


async def _finalize_run(round_over_msg: dict):
    """Persist the completed run to the database (only when a package is loaded)."""
    if not _run_buffer["active"] or not _run_buffer["package_id"]:
        _run_buffer["active"] = False
        return
    with DBSession(engine) as db:
        run = RunDB(
            package_id=_run_buffer["package_id"],
            package_name=_run_buffer["package_name"],
            class_tag=_run_buffer["class_tag"],
            started_at=_run_buffer["started_at"],
            ended_at=datetime.utcnow(),
            roster_student_ids=json.dumps(_run_buffer["roster_ids"]),
            adhoc_agents="[]",
            event_trace=json.dumps(_run_buffer["events"]),
            consensus_reached=round_over_msg.get("consensus_reached", False),
            outcome_summary=round_over_msg.get("outcome", ""),
        )
        db.add(run)
        db.commit()
    _run_buffer["active"] = False


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)
        await websocket.send_json({"type": "session", "data": session.model_dump()})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict):
        if _run_buffer["active"]:
            _run_buffer["events"].append(message)
            if message.get("type") == "round_over":
                asyncio.create_task(_finalize_run(message))

        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


# ── App lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    if not config.OPENROUTER_API_KEY:
        print("WARNING: OPENROUTER_API_KEY is not set. LLM calls will fail.")
    if not config.ADMIN_PASSWORD:
        print("WARNING: ADMIN_PASSWORD is not set in .env — admin login will be disabled.")
    yield
    manager.active.clear()


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="AgenticVisualizer", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, https_only=False)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/session" if user["role"] == "admin" else "/form", status_code=302)


@app.get("/login")
async def login_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/", status_code=302)
    return FileResponse(os.path.join(static_dir, "login.html"))


@app.get("/form")
async def form_page(request: Request):
    redir = redirect_if_not_authenticated(request)
    return redir or FileResponse(os.path.join(static_dir, "form.html"))


@app.get("/admin")
async def admin_page(request: Request):
    redir = redirect_if_not_admin(request)
    return redir or FileResponse(os.path.join(static_dir, "admin.html"))


@app.get("/session")
async def session_page(request: Request):
    redir = redirect_if_not_admin(request)
    return redir or FileResponse(os.path.join(static_dir, "index.html"))


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/login")
async def do_login(request: Request, db: DBSession = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    if username == config.ADMIN_USERNAME:
        if config.ADMIN_PASSWORD and password == config.ADMIN_PASSWORD:
            set_session(request, "admin", "admin", "Admin")
            return RedirectResponse("/session", status_code=302)
        return RedirectResponse("/login?error=1", status_code=302)

    user = db.exec(select(User).where(User.username == username)).first()
    if user and verify_password(password, user.password_hash):
        set_session(request, user.id, "student", user.display_name, user.class_tag)
        return RedirectResponse("/form", status_code=302)

    return RedirectResponse("/login?error=1", status_code=302)


@app.post("/logout")
async def do_logout(request: Request):
    clear_session(request)
    return RedirectResponse("/login", status_code=302)


# ── Auth dependency ───────────────────────────────────────────────────────────

def _require_admin(request: Request):
    user = get_session_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403)


# ── Student API ───────────────────────────────────────────────────────────────

@app.get("/api/form/data")
async def get_form_data(request: Request, db: DBSession = Depends(get_db)):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401)

    if user["role"] == "admin":
        uid = int(request.query_params.get("user_id", 0))
        db_user = db.get(User, uid) if uid else None
        class_tag = db_user.class_tag if db_user else ""
        display_name = db_user.display_name if db_user else ""
    else:
        uid = user["user_id"]
        class_tag = user["class_tag"]
        display_name = user["display_name"]

    modules = db.exec(
        select(FormModule)
        .where(FormModule.class_tag == class_tag, FormModule.unlocked == True)
        .order_by(FormModule.week_number, FormModule.id)
    ).all()

    sub = db.exec(select(FormSubmission).where(FormSubmission.user_id == uid)).first()
    answers = json.loads(sub.answers) if sub else {}

    tmpl = db.exec(select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == class_tag)).first()
    template = tmpl.template if tmpl else ""
    preview = render_system_prompt(template, display_name, answers) if template else ""

    return {
        "display_name": display_name,
        "class_tag": class_tag,
        "modules": [
            {"id": m.id, "title": m.title, "week_number": m.week_number,
             "preamble": m.preamble, "field_defs": json.loads(m.field_defs)}
            for m in modules
        ],
        "answers": answers,
        "system_prompt_preview": preview,
    }


@app.post("/api/form/submit")
async def submit_form(request: Request, db: DBSession = Depends(get_db)):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=401)

    body = await request.json()
    answers = body.get("answers", {})

    sub = db.exec(select(FormSubmission).where(FormSubmission.user_id == user["user_id"])).first()
    if sub:
        sub.answers = json.dumps(answers)
        sub.updated_at = datetime.utcnow()
    else:
        sub = FormSubmission(user_id=user["user_id"], answers=json.dumps(answers))
        db.add(sub)
    db.commit()
    return {"ok": True}


# ── Admin API — Classes ───────────────────────────────────────────────────────

@app.get("/api/admin/classes")
async def list_classes(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    classes = db.exec(select(ClassTagDB).order_by(ClassTagDB.tag)).all()
    return [{"id": c.id, "tag": c.tag, "name": c.name} for c in classes]


@app.post("/api/admin/classes")
async def create_class(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    tag = body.get("tag", "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag is required.")
    if db.exec(select(ClassTagDB).where(ClassTagDB.tag == tag)).first():
        raise HTTPException(status_code=400, detail="Class tag already exists.")
    c = ClassTagDB(tag=tag, name=body.get("name", ""))
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "tag": c.tag, "name": c.name}


@app.delete("/api/admin/classes/{class_id}")
async def delete_class(class_id: int, request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    c = db.get(ClassTagDB, class_id)
    if not c:
        raise HTTPException(status_code=404)
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── Admin API — Users ─────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def list_users(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    users = db.exec(select(User)).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name,
             "class_tag": u.class_tag} for u in users]


@app.post("/api/admin/users")
async def create_user(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username required.")
    if db.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=400, detail="Username already exists.")
    user = User(
        username=username,
        password_hash=hash_password(body.get("password", "changeme")),
        display_name=body.get("display_name", username),
        class_tag=body.get("class_tag", ""),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "class_tag": user.class_tag}


@app.put("/api/admin/users/{user_id}")
async def update_user(user_id: int, request: Request,
                      db: DBSession = Depends(get_db)):
    _require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    body = await request.json()
    if "display_name" in body:
        user.display_name = body["display_name"]
    if "class_tag" in body:
        user.class_tag = body["class_tag"]
    if body.get("password"):
        user.password_hash = hash_password(body["password"])
    db.commit()
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "class_tag": user.class_tag}


@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: int, request: Request,
                      db: DBSession = Depends(get_db)):
    _require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    db.delete(user)
    db.commit()
    return {"ok": True}


# ── Admin API — Form modules ──────────────────────────────────────────────────

@app.get("/api/admin/modules")
async def list_modules(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    class_tag = request.query_params.get("class_tag", "")
    q = select(FormModule).order_by(FormModule.week_number, FormModule.id)
    if class_tag:
        q = q.where(FormModule.class_tag == class_tag)
    modules = db.exec(q).all()
    return [{"id": m.id, "class_tag": m.class_tag, "title": m.title, "week_number": m.week_number,
             "preamble": m.preamble, "field_defs": json.loads(m.field_defs), "unlocked": m.unlocked} for m in modules]


@app.post("/api/admin/modules")
async def create_module(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    mod = FormModule(
        class_tag=body.get("class_tag", ""),
        title=body.get("title", "New module"),
        week_number=body.get("week_number", 0),
        preamble=body.get("preamble", ""),
        field_defs=json.dumps(body.get("field_defs", [])),
        unlocked=body.get("unlocked", True),
    )
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return {"id": mod.id, "class_tag": mod.class_tag, "title": mod.title,
            "week_number": mod.week_number, "preamble": mod.preamble,
            "field_defs": json.loads(mod.field_defs), "unlocked": mod.unlocked}


@app.put("/api/admin/modules/{module_id}")
async def update_module(module_id: int, request: Request,
                        db: DBSession = Depends(get_db)):
    _require_admin(request)
    mod = db.get(FormModule, module_id)
    if not mod:
        raise HTTPException(status_code=404)
    body = await request.json()
    for field in ("title", "week_number", "unlocked", "preamble"):
        if field in body:
            setattr(mod, field, body[field])
    if "field_defs" in body:
        mod.field_defs = json.dumps(body["field_defs"])
    db.commit()
    return {"id": mod.id, "class_tag": mod.class_tag, "title": mod.title,
            "week_number": mod.week_number, "preamble": mod.preamble,
            "field_defs": json.loads(mod.field_defs), "unlocked": mod.unlocked}


@app.delete("/api/admin/modules/{module_id}")
async def delete_module(module_id: int, request: Request,
                        db: DBSession = Depends(get_db)):
    _require_admin(request)
    mod = db.get(FormModule, module_id)
    if not mod:
        raise HTTPException(status_code=404)
    db.delete(mod)
    db.commit()
    return {"ok": True}


# ── Admin API — System prompt template ───────────────────────────────────────

@app.get("/api/admin/template")
async def get_template(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    class_tag = request.query_params.get("class_tag", "")
    tmpl = db.exec(select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == class_tag)).first()
    return {"class_tag": class_tag, "template": tmpl.template if tmpl else ""}


@app.put("/api/admin/template")
async def save_template(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    class_tag = body.get("class_tag", "")
    text = body.get("template", "")
    tmpl = db.exec(select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == class_tag)).first()
    if tmpl:
        tmpl.template = text
    else:
        db.add(SystemPromptTemplate(class_tag=class_tag, template=text))
    db.commit()
    return {"ok": True}


@app.get("/api/admin/template/preview/{user_id}")
async def preview_template(user_id: int, request: Request,
                           db: DBSession = Depends(get_db)):
    _require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    tmpl = db.exec(select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == user.class_tag)).first()
    sub = db.exec(select(FormSubmission).where(FormSubmission.user_id == user_id)).first()
    answers = json.loads(sub.answers) if sub else {}
    preview = render_system_prompt(tmpl.template if tmpl else "", user.display_name, answers)
    return {"system_prompt": preview}


# ── Admin API — Rule sets ─────────────────────────────────────────────────────

@app.get("/api/admin/rulesets")
async def list_rulesets(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    rulesets = db.exec(select(RuleSetDB)).all()
    return [{"id": r.id, "name": r.name, "description": r.description,
             "rules": json.loads(r.rules), "agent_instructions": r.agent_instructions} for r in rulesets]


@app.post("/api/admin/rulesets")
async def create_ruleset(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    rs = RuleSetDB(name=body.get("name", "New rule set"), description=body.get("description", ""),
                   rules=json.dumps(body.get("rules", [])),
                   agent_instructions=body.get("agent_instructions", ""))
    db.add(rs)
    db.commit()
    db.refresh(rs)
    return {"id": rs.id, "name": rs.name, "description": rs.description,
            "rules": json.loads(rs.rules), "agent_instructions": rs.agent_instructions}


@app.put("/api/admin/rulesets/{rs_id}")
async def update_ruleset(rs_id: int, request: Request,
                         db: DBSession = Depends(get_db)):
    _require_admin(request)
    rs = db.get(RuleSetDB, rs_id)
    if not rs:
        raise HTTPException(status_code=404)
    body = await request.json()
    for field in ("name", "description", "agent_instructions"):
        if field in body:
            setattr(rs, field, body[field])
    if "rules" in body:
        rs.rules = json.dumps(body["rules"])
    db.commit()
    return {"id": rs.id, "name": rs.name, "description": rs.description,
            "rules": json.loads(rs.rules), "agent_instructions": rs.agent_instructions}


@app.delete("/api/admin/rulesets/{rs_id}")
async def delete_ruleset(rs_id: int, request: Request,
                         db: DBSession = Depends(get_db)):
    _require_admin(request)
    rs = db.get(RuleSetDB, rs_id)
    if not rs:
        raise HTTPException(status_code=404)
    db.delete(rs)
    db.commit()
    return {"ok": True}


# ── Admin API — Packages ──────────────────────────────────────────────────────

@app.get("/api/admin/packages")
async def list_packages(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    class_tag = request.query_params.get("class_tag", "")
    q = select(PackageDB)
    if class_tag:
        q = q.where(PackageDB.class_tag == class_tag)
    packages = db.exec(q).all()
    return [{"id": p.id, "class_tag": p.class_tag, "name": p.name, "topic": p.topic,
             "constraints": json.loads(p.constraints), "rule_set_id": p.rule_set_id,
             "agent_prompt_template": p.agent_prompt_template}
            for p in packages]


@app.post("/api/admin/packages")
async def create_package(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    body = await request.json()
    pkg = PackageDB(
        class_tag=body.get("class_tag", ""),
        name=body.get("name", "New package"),
        topic=body.get("topic", ""),
        constraints=json.dumps(body.get("constraints", [])),
        rule_set_id=body.get("rule_set_id"),
        agent_prompt_template=body.get("agent_prompt_template", ""),
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return {"id": pkg.id, "class_tag": pkg.class_tag, "name": pkg.name, "topic": pkg.topic,
            "constraints": json.loads(pkg.constraints), "rule_set_id": pkg.rule_set_id,
            "agent_prompt_template": pkg.agent_prompt_template}


@app.put("/api/admin/packages/{pkg_id}")
async def update_package(pkg_id: int, request: Request,
                         db: DBSession = Depends(get_db)):
    _require_admin(request)
    pkg = db.get(PackageDB, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404)
    body = await request.json()
    for field in ("name", "topic", "rule_set_id", "agent_prompt_template"):
        if field in body:
            setattr(pkg, field, body[field])
    if "constraints" in body:
        pkg.constraints = json.dumps(body["constraints"])
    db.commit()
    return {"id": pkg.id, "class_tag": pkg.class_tag, "name": pkg.name, "topic": pkg.topic,
            "constraints": json.loads(pkg.constraints), "rule_set_id": pkg.rule_set_id,
            "agent_prompt_template": pkg.agent_prompt_template}


@app.delete("/api/admin/packages/{pkg_id}")
async def delete_package(pkg_id: int, request: Request,
                         db: DBSession = Depends(get_db)):
    _require_admin(request)
    pkg = db.get(PackageDB, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404)
    db.delete(pkg)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/packages/{pkg_id}/load")
async def load_package(pkg_id: int, request: Request,
                       db: DBSession = Depends(get_db)):
    """Assemble student agents from form submissions and populate the live session."""
    global session
    _require_admin(request)
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Stop the current round before loading a new package.")

    pkg = db.get(PackageDB, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404)

    body = await request.json()
    student_ids: list = body.get("student_ids", [])

    rule_set_rules: list = []
    rule_agent_instructions: str = ""
    if pkg.rule_set_id:
        rs = db.get(RuleSetDB, pkg.rule_set_id)
        if rs:
            rule_set_rules = json.loads(rs.rules)
            rule_agent_instructions = rs.agent_instructions or ""

    constraints = json.loads(pkg.constraints)
    all_roe = constraints + rule_set_rules

    tmpl_row = db.exec(
        select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == pkg.class_tag)
    ).first()
    template = tmpl_row.template if tmpl_row else "You are {display_name}, participating in this negotiation."

    # Rules that should be injected into agent prompts (applies_to "agents" or "both").
    # Constraints are always referee-only; only rule-set process rules are injected.
    agent_rules = [r for r in rule_set_rules if r.get("applies_to") in ("agents", "both")]
    agent_rules_text = ""
    if agent_rules:
        lines = "\n".join(f"- {r['name']}: {r['text']}" for r in agent_rules)
        agent_rules_text = f"\n\nNegotiation process rules you must follow:\n{lines}"

    avatar_pool = ["🤖", "🐶", "🐱", "🦊", "🐼", "🐨", "🦁", "🐯", "🐷", "🐸", "🐙", "🦄"]
    agents = []
    roster_ids = []

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
            goal="Participate in the negotiation.",
            system_prompt=base_prompt + agent_rules_text,
        ))
        roster_ids.append(user.id)

    session = Session(
        topic=pkg.topic,
        agents=agents,
        rules=RuleSet(agent_instructions=rule_agent_instructions),
        rules_of_engagement=[RuleOfEngagement(**r) for r in all_roe],
        loaded_package_id=pkg.id,
        loaded_package_name=pkg.name,
        agent_prompt_template=pkg.agent_prompt_template or "",
    )
    _run_buffer["roster_ids"] = roster_ids
    _run_buffer["class_tag"] = pkg.class_tag

    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return {"ok": True, "agent_count": len(agents)}


# ── Admin API — Runs ──────────────────────────────────────────────────────────

@app.get("/api/admin/runs")
async def list_runs(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    pkg_id = request.query_params.get("package_id")
    q = select(RunDB).order_by(RunDB.started_at.desc())
    if pkg_id:
        q = q.where(RunDB.package_id == int(pkg_id))
    runs = db.exec(q).all()
    return [
        {"id": r.id, "package_id": r.package_id, "package_name": r.package_name,
         "class_tag": r.class_tag, "started_at": r.started_at.isoformat(),
         "ended_at": r.ended_at.isoformat() if r.ended_at else None,
         "consensus_reached": r.consensus_reached, "outcome_summary": r.outcome_summary}
        for r in runs
    ]


@app.get("/api/admin/runs/{run_id}/trace")
async def get_run_trace(run_id: int, request: Request,
                        db: DBSession = Depends(get_db)):
    _require_admin(request)
    run = db.get(RunDB, run_id)
    if not run:
        raise HTTPException(status_code=404)
    return JSONResponse(content=json.loads(run.event_trace))


# ── Admin API — Agent profiles ────────────────────────────────────────────────

@app.get("/api/admin/profiles")
async def list_profiles(request: Request, db: DBSession = Depends(get_db)):
    _require_admin(request)
    class_tag = request.query_params.get("class_tag", "")
    q = select(User)
    if class_tag:
        q = q.where(User.class_tag == class_tag)
    users = db.exec(q).all()
    profiles = []
    for user in users:
        tmpl = db.exec(
            select(SystemPromptTemplate).where(SystemPromptTemplate.class_tag == user.class_tag)
        ).first()
        sub = db.exec(select(FormSubmission).where(FormSubmission.user_id == user.id)).first()
        answers = json.loads(sub.answers) if sub else {}
        profiles.append({
            "user_id": user.id, "display_name": user.display_name, "class_tag": user.class_tag,
            "system_prompt": render_system_prompt(tmpl.template if tmpl else "", user.display_name, answers),
            "system_prompt_override": user.system_prompt_override,
            "answers": answers,
            "last_updated": sub.updated_at.isoformat() if sub else None,
        })
    return profiles


@app.put("/api/admin/profiles/{user_id}/prompt")
async def set_prompt_override(user_id: int, request: Request,
                              db: DBSession = Depends(get_db)):
    _require_admin(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    body = await request.json()
    user.system_prompt_override = body.get("system_prompt_override")
    db.commit()
    return {"ok": True}


# ── Existing session API (admin only) ─────────────────────────────────────────

@app.get("/api/session")
async def get_session_state(request: Request):
    _require_admin(request)
    return session.model_dump()


@app.post("/api/session/reset")
async def reset_session_route(request: Request):
    _require_admin(request)
    global session
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot reset while a round is running.")
    session = Session(
        topic=session.topic,
        agents=session.agents,
        rules=session.rules,
        rules_of_engagement=session.rules_of_engagement,
        loaded_package_id=session.loaded_package_id,
        loaded_package_name=session.loaded_package_name,
        agent_prompt_template=session.agent_prompt_template,
    )
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _round_task
    user = websocket.session.get("user") if hasattr(websocket, "session") else None
    if not user or user.get("role") != "admin":
        await websocket.close(code=4003)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "start_round":
                if session.status == "running":
                    await websocket.send_json({"type": "error", "message": "A round is already running."})
                    continue
                if len(session.agents) < 2:
                    await websocket.send_json({"type": "error", "message": "Need at least 2 agents."})
                    continue
                _cancel_round()  # kill any zombie task from a previous run
                _start_run()
                _round_task = asyncio.create_task(run_round(session, manager.broadcast))

            elif msg_type == "stop_round":
                if session.status == "running":
                    session.status = "idle"
                    _cancel_round()
                    await manager.broadcast({"type": "status", "state": "idle"})

            elif msg_type == "next_step":
                advance_step()

            elif msg_type == "update_session":
                if session.status == "running":
                    await websocket.send_json({"type": "error", "message": "Cannot edit while a round is running."})
                    continue
                payload = data.get("data", {})
                if "topic" in payload:
                    session.topic = payload["topic"]
                if "rules" in payload:
                    session.rules = RuleSet(**payload["rules"])
                if "rules_of_engagement" in payload:
                    session.rules_of_engagement = [RuleOfEngagement(**r) for r in payload["rules_of_engagement"]]
                if "agents" in payload:
                    session.agents = [Agent(**a) for a in payload["agents"]]
                await manager.broadcast({"type": "session", "data": session.model_dump()})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
