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


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    avatar: str = "🤖"
    avatar_url: Optional[str] = None
    goal: str
    system_prompt: str


class Message(BaseModel):
    agent_id: str
    content: str
    turn: int


class RuleSet(BaseModel):
    max_rounds: int = MAX_ROUNDS_DEFAULT
    min_rounds: int = MIN_ROUNDS_DEFAULT
    turn_order: Literal["sequential", "random", "simultaneous_proposal"] = "sequential"
    mode: Literal["realtime", "auto_pause", "step_by_step"] = "realtime"
    agent_instructions: str = ""


class RuleOfEngagement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    text: str
    severity: Literal["hard_constraint", "guideline"] = "guideline"
    # "referee" = referee only; "agents" = agent prompts only; "both" = both.
    # Constraints on packages are always "referee". Process rules in rule sets
    # default to "referee" for backward compat; set to "both" for tone/behaviour rules.
    applies_to: Literal["referee", "agents", "both"] = "referee"


class RefereeEvaluation(BaseModel):
    warnings: List[str] = []
    consensus_reached: bool = False
    consensus_proposal: str = ""
    status_summary: str = ""
    checklist: dict = Field(default_factory=dict)


class Session(BaseModel):
    topic: str = "What should our team focus on next quarter?"
    goal: str = ""
    agents: List[Agent] = []
    history: List[Message] = []
    rules: RuleSet = Field(default_factory=RuleSet)
    rules_of_engagement: List[RuleOfEngagement] = Field(default_factory=list)
    status: Literal["idle", "running", "paused"] = "idle"
    # Loaded package metadata (set when admin loads a package for a run).
    loaded_package_id: Optional[int] = None
    loaded_package_name: Optional[str] = None
    agent_prompt_template: str = ""
    # Board mode: declared negotiation options and each agent's current stance.
    # Both empty means this session runs the original free-form room.
    options: List[Option] = []
    stances: Dict[str, AgentStance] = {}
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
