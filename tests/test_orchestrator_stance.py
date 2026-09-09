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
