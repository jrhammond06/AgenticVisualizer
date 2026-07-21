from typing import List

from models import Agent, RefereeEvaluation, RuleOfEngagement
from utils import extract_json
import config
import llm


class Referee:
    def __init__(self, rules_of_engagement: List[RuleOfEngagement]):
        self.rules_of_engagement = rules_of_engagement

    def _format_rules(self) -> str:
        if not self.rules_of_engagement:
            return "No rules of engagement have been defined."
        lines = []
        for i, rule in enumerate(self.rules_of_engagement, start=1):
            label = "HARD CONSTRAINT" if rule.severity == "hard_constraint" else "GUIDELINE"
            lines.append(f"{i}. [{label}] {rule.name}: {rule.text}")
        return "\n".join(lines)

    def _build_system_prompt(self, topic: str) -> str:
        rules_text = self._format_rules()
        rule_names = [rule.name for rule in self.rules_of_engagement]
        checklist_example = {name: {"status": "satisfied|violated|not_applicable", "note": "short explanation"} for name in rule_names}

        return f"""You are the Referee for a managed debate.

Topic: {topic}

Rules of engagement to enforce:
{rules_text}

How to enforce severity:
- HARD CONSTRAINT rules are non-negotiable. Any proposal that violates a hard constraint is invalid, and you must warn the group clearly.
- GUIDELINE rules are strongly preferred negotiation norms. A violation should produce a warning and a suggestion, but it does not automatically invalidate a proposal unless the group agrees it should.

Your job:
1. Monitor the conversation closely.
2. Use the provided agent roster to track who has spoken and who has not. Do not declare consensus until every agent in the room has had a chance to contribute.
3. Check every proposal or emerging consensus against each rule of engagement. List specific, clear warnings for any VIOLATED rule and suggest concrete adjustments.
4. Decide whether the group has genuinely reached consensus on a final proposal.
5. If consensus is reached, summarize the agreed proposal in plain language.
6. If consensus is NOT reached, return a brief "where things stand" summary: what each side wants, what conflicts remain, and what would need to change to reach agreement. Do NOT force a conclusion.

Return ONLY a JSON object with exactly these keys:
- "warnings": list of strings (empty if nothing is wrong)
- "consensus_reached": boolean
- "consensus_proposal": string (plain-language summary if consensus reached, otherwise empty string)
- "status_summary": one short sentence summarizing the state of the negotiation
- "checklist": object with one entry per rule of engagement keyed by rule name: {checklist_example!r}

Your entire response must fit within {config.REFEREE_MAX_TOKENS} tokens. Keep checklist notes to one short phrase each. Be concise."""

    def _format_agents(self, agents: List[Agent], history_text: str) -> str:
        agent_names = [f"- {agent.name}" for agent in agents]
        spoken_names = set()
        for line in history_text.splitlines():
            if ":" in line:
                name = line.split(":", 1)[0].strip()
                if name:
                    spoken_names.add(name)
        all_names = {agent.name for agent in agents}
        unheard = sorted(all_names - spoken_names)
        heard = sorted(all_names & spoken_names)
        lines = ["Agents in the room:"]
        lines.extend(agent_names)
        lines.append("\nAgents who have spoken so far:")
        if heard:
            lines.extend(f"- {name}" for name in heard)
        else:
            lines.append("- (none yet)")
        lines.append("\nAgents who have NOT spoken yet:")
        if unheard:
            lines.extend(f"- {name}" for name in unheard)
        else:
            lines.append("- (everyone has spoken)")
        return "\n".join(lines)

    async def evaluate(self, topic: str, history_text: str, agents: List[Agent]) -> RefereeEvaluation:
        system = self._build_system_prompt(topic)
        agents_text = self._format_agents(agents, history_text)
        user = f"{agents_text}\n\nConversation so far:\n{history_text}\n\nEvaluate the current state of the negotiation."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = await llm.chat_completion(
            messages,
            temperature=0.3,
            max_tokens=config.REFEREE_MAX_TOKENS,
            model=config.REFEREE_MODEL_NAME,
        )
        parsed = extract_json(result)
        if parsed:
            try:
                return RefereeEvaluation(**parsed)
            except Exception:
                pass
        return RefereeEvaluation(
            warnings=[],
            consensus_reached=False,
            status_summary="The Referee couldn't evaluate the negotiation clearly.",
        )
