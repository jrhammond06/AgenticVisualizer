from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import os

from models import Agent, AgentUpdate, RuleOfEngagement, RuleSet, Session
from orchestrator import run_round, advance_step
import config


# Single in-memory classroom session
session = Session(
    topic="What should we order for the party menu?",
    agents=[
        Agent(
            name="Maya",
            avatar="🐶",
            goal="Get pizza and soda for the party.",
            system_prompt="You are a kid who really wants pizza and soda at the party. Pepperoni pizza is your favorite, but you will accept cheese pizza if needed. You are energetic and try to keep things fun, but you do not want anyone to feel left out.",
        ),
        Agent(
            name="Leo",
            avatar="🐱",
            goal="Make sure there is a vegetarian option.",
            system_prompt="You are a vegetarian kid. You do not eat meat, pepperoni, or chicken. You want the party to have a tasty vegetarian main option like cheese pizza, veggie pasta, or a bean burrito. You are friendly but firm about your dietary needs.",
        ),
        Agent(
            name="Sam",
            avatar="🦊",
            goal="Keep the menu safe for your peanut allergy.",
            system_prompt="You have a severe peanut allergy. You cannot eat anything with peanuts, peanut oil, or peanut butter, and you are cautious about desserts or snacks that might contain nuts. You want the menu to be safe for you and still fun for everyone. Speak up clearly when something is unsafe.",
        ),
        Agent(
            name="Zoe",
            avatar="🐼",
            goal="Keep the party food affordable and simple.",
            system_prompt="You are the practical kid who knows the party budget is tight. You prefer simple, cheap food and want every menu item to have a rough cost attached. You will push back on expensive items and suggest affordable alternatives like homemade snacks or bulk options.",
        ),
    ],
    rules=RuleSet(max_turns=10, min_turns=3, turn_order="sequential"),
    rules_of_engagement=[
        RuleOfEngagement(
            name="Voice requirement",
            text="Every kid must share their opinion before the group finalizes the menu.",
            severity="guideline",
        ),
        RuleOfEngagement(
            name="Budget tracking",
            text="Each proposed menu item must include a rough cost, and the total menu cost must stay within the party budget of $40.",
            severity="hard_constraint",
        ),
        RuleOfEngagement(
            name="Inclusive menu",
            text="The final menu must include at least one item that each kid can safely eat. A menu where one or more kids cannot eat anything is not allowed.",
            severity="hard_constraint",
        ),
    ],
)


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
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if not config.OPENROUTER_API_KEY:
        print("WARNING: OPENROUTER_API_KEY is not set. LLM calls will fail.")
    yield
    # Shutdown
    manager.active.clear()


app = FastAPI(title="AgenticVisualizer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/session")
async def get_session():
    return session.model_dump()


@app.post("/api/session/reset")
async def reset_session():
    global session
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot reset while a round is running.")
    session = Session(
        topic=session.topic,
        agents=session.agents,
        rules=session.rules,
        rules_of_engagement=session.rules_of_engagement,
    )
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


@app.post("/api/session/topic")
async def set_topic(payload: dict):
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot edit while a round is running.")
    session.topic = payload.get("topic", session.topic)
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


@app.post("/api/session/rules")
async def set_rules(rules: RuleSet):
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot edit while a round is running.")
    session.rules = rules
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


@app.post("/api/agents")
async def add_agent(agent: Agent):
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot edit while a round is running.")
    if len(session.agents) >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 agents allowed.")
    session.agents.append(agent)
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate):
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot edit while a round is running.")
    for agent in session.agents:
        if agent.id == agent_id:
            for field, value in update.model_dump(exclude_unset=True).items():
                setattr(agent, field, value)
            await manager.broadcast({"type": "session", "data": session.model_dump()})
            return session.model_dump()
    raise HTTPException(status_code=404, detail="Agent not found.")


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    if session.status == "running":
        raise HTTPException(status_code=400, detail="Cannot edit while a round is running.")
    session.agents = [a for a in session.agents if a.id != agent_id]
    await manager.broadcast({"type": "session", "data": session.model_dump()})
    return session.model_dump()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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
                asyncio.create_task(run_round(session, manager.broadcast))

            elif msg_type == "stop_round":
                if session.status == "running":
                    session.status = "idle"
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
                    session.rules_of_engagement = [
                        RuleOfEngagement(**r) for r in payload["rules_of_engagement"]
                    ]
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
