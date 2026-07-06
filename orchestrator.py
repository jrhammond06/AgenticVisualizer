import asyncio
import random

from models import Agent as AgentModel, Message, RuleSet, Session
from agent import Agent as AgentActor
from referee import Referee
import llm


async def run_round(session: Session, broadcast):
    """Run one debate round and stream events via `broadcast`.

    Supports auto-pause: after every full cycle (all agents + referee), the round
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

    session.status = "running"
    await broadcast({"type": "status", "state": "running"})

    if resuming:
        await broadcast({"type": "round_resumed"})
    else:
        await broadcast({"type": "round_started"})

    referee = Referee(session.rules_of_engagement)
    actors = {a.id: AgentActor(a) for a in session.agents}

    try:
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
                session.last_evaluation = await _referee_check(session, actors, referee, broadcast, session.turn)
                if session.last_evaluation and session.last_evaluation.consensus_reached:
                    session.consensus_reached = True
                    break

                # Auto-pause after interim referee checks so the teacher can review.
                # Don't pause if this is the last possible cycle; let the round finish.
                if session.rules.auto_pause and session.turn < session.rules.max_turns:
                    session.status = "paused"
                    await broadcast({"type": "status", "state": "paused"})
                    await broadcast({"type": "referee_popup"})
                    break

        # Final referee evaluation if the round ran to completion without consensus.
        if session.status == "running" and not session.consensus_reached:
            session.last_evaluation = await _referee_check(session, actors, referee, broadcast, session.turn)

        # Broadcast outcome if the round completed (not paused).
        if session.status == "running":
            await _broadcast_outcome(session, actors, session.last_evaluation, broadcast)

    except Exception as e:
        await broadcast({"type": "error", "message": f"Round failed: {str(e)}"})

    finally:
        # Only change status if the round wasn't manually stopped or auto-paused.
        if session.status == "running":
            session.status = "idle"
            await broadcast({"type": "status", "state": "idle"})


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


async def _referee_check(session: Session, actors: dict, referee: Referee, broadcast, turn: int):
    history_text = _format_history(session, actors)
    await broadcast({"type": "referee_thinking"})
    evaluation = await referee.evaluate(session.topic, history_text, session.agents)

    for warning in evaluation.warnings:
        await broadcast({"type": "referee_warning", "content": warning})

    # Share the full structured evaluation with the frontend.
    await broadcast({"type": "referee_evaluation", "evaluation": evaluation.model_dump()})

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
    session.history.append(Message(agent_id="referee", content="\n".join(referee_lines), turn=turn))

    return evaluation


async def _broadcast_outcome(session: Session, actors: dict, evaluation, broadcast):
    if evaluation and evaluation.consensus_reached:
        outcome = evaluation.consensus_proposal or "Consensus reached"
        summary = evaluation.status_summary
        await broadcast({
            "type": "round_over",
            "outcome": outcome,
            "summary": summary,
            "consensus_proposal": evaluation.consensus_proposal,
            "proposal_details": evaluation.proposal_details,
            "consensus_reached": True,
            "history": [m.model_dump() for m in session.history],
        })
    else:
        # No consensus: report where things stand
        summary = evaluation.status_summary if evaluation else "The group did not reach a consensus."
        await broadcast({
            "type": "round_over",
            "outcome": "No consensus yet",
            "summary": summary,
            "consensus_proposal": evaluation.consensus_proposal if evaluation else "",
            "proposal_details": evaluation.proposal_details if evaluation else {},
            "consensus_reached": False,
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
