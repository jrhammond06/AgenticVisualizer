from typing import List

from models import Agent as AgentModel, RuleOfEngagement, RuleSet
import config
import llm


class Agent:
    def __init__(self, model: AgentModel):
        self.model = model

    def _format_rules(self, rules_of_engagement: List[RuleOfEngagement]) -> str:
        if not rules_of_engagement:
            return "No special rules of engagement have been set."
        lines = []
        for rule in rules_of_engagement:
            label = "HARD CONSTRAINT" if rule.severity == "hard_constraint" else "GUIDELINE"
            lines.append(f"- [{label}] {rule.name}: {rule.text}")
        return "\n".join(lines)

    def _build_system_prompt(
        self, topic: str, rules: RuleSet, rules_of_engagement: List[RuleOfEngagement]
    ) -> str:
        rules_text = self._format_rules(rules_of_engagement)
        return f"""You are {self.model.name}, a participant in a managed debate.

Your visible goal: {self.model.goal}
The group is discussing this topic: {topic}

Rules of engagement:
{rules_text}

Additional instructions from the moderator (this is what you, as this participant, want and need):
{self.model.system_prompt}

The Referee checks the discussion every few turns and will warn the group if a proposal breaks a hard constraint or guideline. If the Referee raises a warning, you MUST help address it in your next reply.

Speaking rules:
- Reply in 1 or 2 short sentences only.
- Stay in character and advocate for your goal, but be willing to compromise if it makes sense.
- Keep the rules of engagement in mind when making or evaluating proposals.
- If the Referee says the group is violating a rule, help fix it — do not ignore the warning.
- Speak directly to the other agents by name when relevant.
- Do not use lists, bullet points, or long explanations.
- Be clear, respectful, and concise."""

    async def generate_reply(
        self,
        topic: str,
        history_text: str,
        rules: RuleSet,
        rules_of_engagement: List[RuleOfEngagement],
    ) -> str:
        system_content = self._build_system_prompt(topic, rules, rules_of_engagement)

        user_parts = [f"Topic: {topic}"]
        if history_text.strip():
            user_parts.append(f"\nConversation so far:\n{history_text}")
        user_parts.append(
            f"\nIt's your turn, {self.model.name}. Say something short to move the discussion toward a decision."
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        reply = await llm.chat_completion(messages, temperature=0.8, max_tokens=config.AGENT_MAX_TOKENS)
        # Strip quotes if the model added them
        reply = reply.strip('"').strip("'").strip()
        return reply
