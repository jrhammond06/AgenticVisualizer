from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from uuid import uuid4

from config import MAX_TURNS_DEFAULT, MIN_TURNS_DEFAULT


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    avatar: str = "🤖"
    goal: str
    system_prompt: str


class Message(BaseModel):
    agent_id: str
    content: str
    turn: int


class RuleSet(BaseModel):
    max_turns: int = MAX_TURNS_DEFAULT
    min_turns: int = MIN_TURNS_DEFAULT
    turn_order: Literal["sequential", "random", "simultaneous_proposal"] = "sequential"
    auto_pause: bool = False
    mode: Literal["realtime", "step_by_step"] = "realtime"


class RuleOfEngagement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    text: str
    severity: Literal["hard_constraint", "guideline"] = "guideline"


class RefereeEvaluation(BaseModel):
    warnings: List[str] = []
    consensus_reached: bool = False
    consensus_proposal: str = ""
    proposal_details: dict = Field(default_factory=dict)
    status_summary: str = ""
    checklist: dict = Field(default_factory=dict)


class Session(BaseModel):
    topic: str = "What should our team focus on next quarter?"
    agents: List[Agent] = []
    history: List[Message] = []
    rules: RuleSet = Field(default_factory=RuleSet)
    rules_of_engagement: List[RuleOfEngagement] = Field(default_factory=list)
    status: Literal["idle", "running", "paused"] = "idle"
    # Round state, preserved when auto-pause interrupts a round.
    turn: int = 0
    consensus_reached: bool = False
    last_evaluation: Optional[RefereeEvaluation] = None
    # Step-by-step playback queue (not serialized to the frontend).
    step_queue: List[dict] = Field(default_factory=list, exclude=True)
    step_index: int = Field(default=0, exclude=True)


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    goal: Optional[str] = None
    system_prompt: Optional[str] = None
