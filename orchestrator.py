import asyncio
import random

from models import Agent as AgentModel, Message, RuleSet, Session
from agent import Agent as AgentActor
from referee import Referee
import llm


# Used to advance the step-by-step playback queue.
_step_event = asyncio.Event()


def advance_step():
    """Signal the step-by-step orchestrator to reveal the next queued item."""
    _step_event.set()


def _clear_step_signal():
    """Consume any stale step signal (e.g. at the start of a new circle)."""
    _step_event.clear()


async def run_round(session: Session, broadcast):
    """Run one debate round and stream events via `broadcast`.

    Supports two modes:
    - realtime: agents speak and the referee evaluates as responses are generated.
    - step_by_step: a full circle (every agent once + referee) is generated up front,
      queued, and then revealed one item at a time when the user presses Next.

    Also supports auto-pause in realtime mode: after every full cycle the round
    pauses so the teacher can review. Clicking Start resumes from the same state.
    """
    if len(session.agents) < 2:
        await broadcast({"type": "error", "message": "Need at least 2 agents to start a round."})
        return

    resuming = session.status == "paused"
    if not resuming:
        session.history = []
        session.turn = 0
        session.consensus_reached = False
        session.last_evaluation = None
        session.step_queue = []
        session.step_index = 0

    session.status = "running"
    await broadcast({"type": "status", "state": "running"})

    if resuming:
        await broadcast({"type": "round_resumed"})
    else:
        await broadcast({"type": "round_started"})

    referee = Referee(session.rules_of_engagement)
    actors = {a.id: AgentActor(a) for a in session.agents}

    try:
        if session.rules.mode == "step_by_step":
            await _run_step_by_step(session, actors, referee, broadcast)
        else:
            await _run_realtime(session, actors, referee, broadcast, resuming)
    except Exception as e:
        await broadcast({"type": "error", "message": f"Round failed: {str(e)}"})

    finally:
        # Only change status if the round wasn't manually stopped or auto-paused.
        if session.status == "running":
            session.status = "idle"
            await broadcast({"type": "status", "state": "idle"})


async def _run_realtime(session: Session, actors: dict, referee: Referee, broadcast, resuming: bool):
    """Original real-time flow."""
    # Optional simultaneous proposal phase only on a fresh start.
    if not resuming and session.rules.turn_order == "simultaneous_proposal":
        session.turn += 1
        await broadcast({"type": "phase", "phase": "proposals", "message": "Everyone is making an opening proposal..."})
        tasks = [
            _agent_propose(agent, actors[agent.id], session, session.turn, broadcast, session.rules_of_engagement)
            for agent in session.agents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            agent_id, content = result
            session.history.append(Message(agent_id=agent_id, content=content, turn=session.turn))

    # Sequential reaction phase
    while session.turn < session.rules.max_turns and session.status == "running":
        session.turn += 1
        speaker = _pick_speaker(session, session.turn)

        await broadcast({"type": "agent_thinking", "agent_id": speaker.id})
        content = await actors[speaker.id].generate_reply(
            session.topic,
            _format_history(session, actors),
            session.rules,
            session.rules_of_engagement,
        )
        session.history.append(Message(agent_id=speaker.id, content=content, turn=session.turn))
        await broadcast({
            "type": "agent_speak",
            "agent_id": speaker.id,
            "content": content,
            "turn": session.turn,
        })

        # Let the Referee check in after every full cycle (every agent has spoken once),
        # but only after the minimum number of turns has passed.
        cycle_complete = session.turn >= len(session.agents) and session.turn % len(session.agents) == 0
        if cycle_complete and session.turn >= session.rules.min_turns:
            await broadcast({"type": "referee_thinking"})
            session.last_evaluation = await _referee_check_queued(session, actors, referee)
            await broadcast(_referee_event(session.last_evaluation))
            if session.last_evaluation and session.last_evaluation.consensus_reached:
                session.consensus_reached = True
                break

            # Auto-pause after interim referee checks so the teacher can review.
            # Don't pause if this is the last possible cycle; let the round finish.
            if session.rules.mode == "auto_pause" and session.turn < session.rules.max_turns:
                session.status = "paused"
                await broadcast({"type": "status", "state": "paused"})
                break

    # Final referee evaluation if the round ran to completion without consensus.
    if session.status == "running" and not session.consensus_reached:
        await broadcast({"type": "referee_thinking"})
        session.last_evaluation = await _referee_check_queued(session, actors, referee)
        await broadcast(_referee_event(session.last_evaluation))

    # Broadcast outcome if the round completed (not paused).
    if session.status == "running":
        await _broadcast_outcome(session, actors, session.last_evaluation, broadcast)


async def _run_step_by_step(session: Session, actors: dict, referee: Referee, broadcast):
    """Step-by-step flow: generate a full circle, queue it, then wait for Next clicks."""
    # Optional simultaneous proposal opening on a fresh start.
    if session.rules.turn_order == "simultaneous_proposal" and session.turn == 0:
        await broadcast({"type": "phase", "phase": "proposals", "message": "Everyone is making an opening proposal..."})
        opening_events = []
        session.turn += 1
        tasks = [
            _agent_propose_queued_with_indicator(agent, actors[agent.id], session, broadcast)
            for agent in session.agents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            agent_id, content = result
            session.history.append(Message(agent_id=agent_id, content=content, turn=session.turn))
            opening_events.append({
                "type": "agent_speak",
                "agent_id": agent_id,
                "content": content,
                "turn": session.turn,
            })

        if session.status != "running":
            return

        # The opening counts as a full circle, so include a referee evaluation.
        if session.turn >= session.rules.min_turns:
            await broadcast({"type": "referee_generating", "done": False})
            evaluation = await _referee_check_queued(session, actors, referee)
            await broadcast({"type": "referee_generating", "done": True})
        else:
            evaluation = None
        if evaluation:
            session.last_evaluation = evaluation
            opening_events.append(_referee_event(evaluation))
            if evaluation.consensus_reached:
                session.consensus_reached = True

        await _play_queue(session, opening_events, broadcast)
        if session.consensus_reached:
            return

    # Main loop: generate one full circle at a time, then play it back step by step.
    while session.status == "running":
        # We need enough remaining turns for every agent to speak once.
        if session.turn >= session.rules.max_turns:
            break
        if session.turn + len(session.agents) > session.rules.max_turns:
            break

        events = []
        circle_number = (session.turn // len(session.agents)) + 1
        await broadcast({"type": "phase", "phase": "circle", "message": f"Generating circle {circle_number}..."})
        speaker_order = _circle_speaker_order(session)

        for speaker in speaker_order:
            if session.status != "running":
                break
            session.turn += 1
            await broadcast({"type": "agent_generating", "agent_id": speaker.id, "done": False})
            content = await actors[speaker.id].generate_reply(
                session.topic,
                _format_history(session, actors),
                session.rules,
                session.rules_of_engagement,
            )
            session.history.append(Message(agent_id=speaker.id, content=content, turn=session.turn))
            await broadcast({"type": "agent_generating", "agent_id": speaker.id, "done": True})
            events.append({
                "type": "agent_speak",
                "agent_id": speaker.id,
                "content": content,
                "turn": session.turn,
            })

        if session.status != "running":
            break

        if session.turn >= session.rules.min_turns:
            await broadcast({"type": "referee_generating", "done": False})
            evaluation = await _referee_check_queued(session, actors, referee)
            await broadcast({"type": "referee_generating", "done": True})
        else:
            evaluation = None
        if evaluation:
            session.last_evaluation = evaluation
            events.append(_referee_event(evaluation))
            if evaluation.consensus_reached:
                session.consensus_reached = True

        await _play_queue(session, events, broadcast)
        if session.consensus_reached:
            break

    # Broadcast the final outcome once the round is complete.
    if session.status == "running":
        await _broadcast_outcome(session, actors, session.last_evaluation, broadcast)


async def _play_queue(session: Session, events: list, broadcast):
    """Make a queued circle available and wait for the user to step through it."""
    if not events:
        return

    # Make sure an earlier Next click doesn't skip the first step.
    _clear_step_signal()
    session.step_queue = events
    session.step_index = 0
    await broadcast({"type": "circle_ready", "steps": len(events)})

    while session.step_index < len(session.step_queue) and session.status == "running":
        await _step_event.wait()
        _clear_step_signal()

        if session.status != "running":
            break

        event = session.step_queue[session.step_index]
        await broadcast(event)
        session.step_index += 1

        if event["type"] == "referee_evaluation_bubble":
            evaluation = event["evaluation"]
            await broadcast({"type": "referee_evaluation", "evaluation": evaluation})
            if evaluation.get("consensus_reached"):
                session.consensus_reached = True

    # Full circle revealed: clear the board and prepare for the next circle.
    if session.status == "running":
        await broadcast({"type": "clear_bubbles"})
        session.step_queue = []
        session.step_index = 0


def _circle_speaker_order(session: Session) -> list:
    """Return one speaker per agent for a full step-by-step circle."""
    if session.rules.turn_order == "random":
        order = session.agents[:]
        random.shuffle(order)
        return order
    # sequential and simultaneous_proposal
    return session.agents[:]


async def _agent_propose(
    agent: AgentModel,
    actor: AgentActor,
    session: Session,
    turn: int,
    broadcast,
    rules_of_engagement,
):
    await broadcast({"type": "agent_thinking", "agent_id": agent.id})
    content = await actor.generate_reply(session.topic, "", session.rules, rules_of_engagement)
    await broadcast({
        "type": "agent_speak",
        "agent_id": agent.id,
        "content": content,
        "turn": turn,
    })
    return agent.id, content


async def _agent_propose_queued(agent: AgentModel, actor: AgentActor, session: Session):
    """Generate a simultaneous opening proposal without broadcasting it immediately."""
    content = await actor.generate_reply(session.topic, "", session.rules, session.rules_of_engagement)
    return agent.id, content


async def _agent_propose_queued_with_indicator(agent: AgentModel, actor: AgentActor, session: Session, broadcast):
    """Generate a simultaneous opening proposal and show a progress indicator."""
    await broadcast({"type": "agent_generating", "agent_id": agent.id, "done": False})
    try:
        content = await actor.generate_reply(session.topic, "", session.rules, session.rules_of_engagement)
    finally:
        await broadcast({"type": "agent_generating", "agent_id": agent.id, "done": True})
    return agent.id, content


def _pick_speaker(session: Session, turn: int) -> AgentModel:
    if session.rules.turn_order == "random":
        return random.choice(session.agents)
    # sequential and simultaneous_proposal both use sequential after the opening
    idx = (turn - 1) % len(session.agents)
    return session.agents[idx]


def _format_history(session: Session, actors: dict) -> str:
    lines = []
    for msg in session.history:
        actor = actors.get(msg.agent_id)
        name = actor.model.name if actor else "Referee"
        lines.append(f"{name}: {msg.content}")
    return "\n".join(lines)


async def _referee_check_queued(session: Session, actors: dict, referee: Referee):
    """Run a referee evaluation without broadcasting, so it can be queued for playback."""
    history_text = _format_history(session, actors)
    evaluation = await referee.evaluate(session.topic, history_text, session.agents)

    # Share the referee's evaluation with the agents so they can respond to warnings.
    referee_lines = [f"Status: {evaluation.status_summary}"]
    if evaluation.warnings:
        referee_lines.append("Warnings:")
        referee_lines.extend(f"- {w}" for w in evaluation.warnings)
    if evaluation.consensus_reached:
        referee_lines.append(f"Consensus proposal: {evaluation.consensus_proposal}")
        details = evaluation.proposal_details
        if details:
            referee_lines.append(f"Proposal details: {details}")
    session.history.append(Message(agent_id="referee", content="\n".join(referee_lines), turn=session.turn))

    return evaluation


def _referee_event(evaluation) -> dict:
    """Build a single speech-bubble event for a queued referee evaluation."""
    # The bubble carries the official status/consensus summary only.
    # Warnings are surfaced separately as warning toasts in the UI.
    parts = []
    if evaluation.status_summary:
        parts.append(evaluation.status_summary)
    if evaluation.consensus_reached:
        parts.append(f"Consensus: {evaluation.consensus_proposal}")
    content = " ".join(parts) if parts else "The referee is evaluating..."

    return {
        "type": "referee_evaluation_bubble",
        "agent_id": "referee",
        "content": content,
        "evaluation": evaluation.model_dump(),
    }


async def _broadcast_outcome(session: Session, actors: dict, evaluation, broadcast):
    if evaluation and evaluation.consensus_reached:
        outcome = evaluation.consensus_proposal or "Consensus reached"
    else:
        outcome = "No consensus yet"

    await broadcast({
        "type": "round_over",
        "outcome": outcome,
        "evaluation": evaluation.model_dump() if evaluation else None,
        "consensus_reached": bool(evaluation and evaluation.consensus_reached),
        "history": [m.model_dump() for m in session.history],
    })


async def _legacy_summarize(session: Session, actors: dict) -> tuple:
    """Fallback plain-text summarizer (kept for reference, currently unused)."""
    history_text = _format_history(session, actors)
    prompt = f"""Topic: {session.topic}
Conversation:
{history_text}
In one sentence, what did the group decide? In a second sentence, explain how they got there."""
    try:
        result = await llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=120)
        lines = [line.strip("-• ").strip() for line in result.split("\n") if line.strip()]
        outcome = lines[0] if lines else result.strip()
        summary = " ".join(lines[1:]) if len(lines) > 1 else ""
        return outcome, summary, {}, {}
    except Exception:
        return "The group talked but didn't settle on a proposal.", "", {}, {}
