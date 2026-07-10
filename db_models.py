from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    display_name: str
    class_tag: str = ""
    system_prompt_override: Optional[str] = Field(default=None, nullable=True)


class FormModule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    class_tag: str = Field(index=True)
    title: str
    week_number: int = 0
    preamble: str = ""
    # JSON array: [{key, label}]
    field_defs: str = "[]"
    unlocked: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SystemPromptTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    class_tag: str = Field(unique=True, index=True)
    # Template string with {field_key} placeholders; {display_name} always available.
    template: str = ""


class FormSubmission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # JSON dict: {field_key: answer_string}
    answers: str = "{}"
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RuleSetDB(SQLModel, table=True):
    __tablename__ = "ruleset"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    # JSON array: [{name, text, severity}]
    rules: str = "[]"
    # Replaces the hardcoded speaking-rules block in agent prompts; empty = use defaults.
    agent_instructions: str = ""


class PackageDB(SQLModel, table=True):
    __tablename__ = "package"
    id: Optional[int] = Field(default=None, primary_key=True)
    class_tag: str = Field(index=True)
    name: str
    topic: str
    # JSON array of hard constraints: [{name, text, severity: "hard_constraint"}]
    constraints: str = "[]"
    rule_set_id: Optional[int] = Field(default=None, foreign_key="ruleset.id")
    # Full agent system-prompt template; empty = use built-in default structure.
    agent_prompt_template: str = ""


class ClassTagDB(SQLModel, table=True):
    __tablename__ = "classtag"
    id: Optional[int] = Field(default=None, primary_key=True)
    tag: str = Field(unique=True, index=True)
    name: str = ""


class RunDB(SQLModel, table=True):
    __tablename__ = "run"
    id: Optional[int] = Field(default=None, primary_key=True)
    package_id: int = Field(foreign_key="package.id", index=True)
    package_name: str = ""
    class_tag: str = Field(index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    # JSON arrays
    roster_student_ids: str = "[]"
    adhoc_agents: str = "[]"
    event_trace: str = "[]"
    consensus_reached: bool = False
    outcome_summary: str = ""
