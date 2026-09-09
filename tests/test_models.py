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
