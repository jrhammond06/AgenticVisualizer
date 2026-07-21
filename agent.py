import re
from typing import List

from models import Agent as AgentModel, RuleOfEngagement, RuleSet
import config
import llm

_DEFAULT_SPEAKING_INSTRUCTIONS = """Speaking rules:
- Stay in character and advocate for your goal, but be willing to compromise if it makes sense.
- Keep the rules of engagement in mind when making or evaluating proposals.
- If the Referee says the group is violating a rule, help fix it — do not ignore the warning.
- Speak directly to the other agents by name when relevant.
- Do not use lists, bullet points, or long explanations.
- Be clear, respectful, and concise."""

# Appended to every system prompt regardless of rule set overrides.
_POINT_INSTRUCTION = """
Output format (always required):
- Begin your reply with exactly this format: POINT: [your single most important takeaway — include any key qualifier or caveat, max 10 words] | [your full reply in 1–2 sentences]
- Example: POINT: Open to pizza, but need dairy-free option | Pizza works for me as long as we get a dairy-free alternative — I'm lactose-intolerant, so that's a hard requirement."""

_DEFAULT_TEMPLATE = """You are {name}, a participant in a managed debate.

Your visible goal: {goal}
The group is discussing this topic: {topic}

Rules of engagement:
{rules}

Additional instructions from the moderator (this is what you, as this participant, want and need):
{system_prompt}

The Referee checks the discussion every few turns and will warn the group if a proposal breaks a hard constraint or guideline. If the Referee raises a warning, you MUST help address it in your next reply.

{speaking_instructions}"""


class _SafeDict(dict):
    def __missing__(self, key):
        return f"[{key} not provided]"


class Agent:
    def __init__(self, model: AgentModel, prompt_template: str = ""):
        self.model = model
        self.prompt_template = prompt_template

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
        base_instructions = rules.agent_instructions.strip() or _DEFAULT_SPEAKING_INSTRUCTIONS
        speaking_instructions = base_instructions + _POINT_INSTRUCTION
        template = self.prompt_template.strip() or _DEFAULT_TEMPLATE
        ctx = _SafeDict(
            name=self.model.name,
            goal=self.model.goal,
            topic=topic,
            rules=rules_text,
            system_prompt=self.model.system_prompt,
            speaking_instructions=speaking_instructions,
        )
        try:
            return template.format_map(ctx)
        except Exception:
            return template

    async def generate_reply(
        self,
        topic: str,
        history_text: str,
        rules: RuleSet,
        rules_of_engagement: List[RuleOfEngagement],
    ) -> tuple[str, str]:
        """Return (content, summary). summary is the POINT chip text; content is the full reply."""
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
        reply = reply.strip('"').strip("'").strip()
        return _parse_reply(reply)


def _parse_reply(reply: str) -> tuple[str, str]:
    """Split 'POINT: X | full reply' into (full_reply, summary). Falls back to (reply, '')."""
    m = re.search(r'POINT:\s*(.+?)\s*\|\s*(.+)', reply, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return reply, ''
