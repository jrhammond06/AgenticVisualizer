import re
from typing import List, Optional

from models import Agent as AgentModel, AgentStance, Option, RuleOfEngagement, RuleSet
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

_STANCE_KEYS = {"WANT": "want", "OKWITH": "ok_with", "WONT": "wont"}


def _board_instruction(options: List[Option]) -> str:
    options_text = "\n".join(f"- {o.label}" for o in options)
    example_option = options[0].label if options else "Option A"
    return f"""

Output format (always required) — this negotiation uses a fixed set of options:
{options_text}

Reply using exactly these four lines, in this order:
STANCE: WANT or OK WITH or WON'T
OPTION: <one of the option names listed above, copied exactly>
REASON: <your reason, no more than 8 words>
FULL: <your full reply, 1-2 sentences>

Example:
STANCE: WANT
OPTION: {example_option}
REASON: Everyone can join in
FULL: I think {example_option} works best because everyone can join in, even people who don't like swimming."""


def _normalize_stance(raw: str) -> Optional[str]:
    key = re.sub(r"[^A-Za-z]", "", raw).upper()
    return _STANCE_KEYS.get(key)


def _cap_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


_BOARD_REPLY_RE = re.compile(
    r"STANCE:\s*(.+?)\s*\n"
    r"OPTION:\s*(.+?)\s*\n"
    r"REASON:\s*(.+?)\s*\n"
    r"FULL:\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_board_reply(reply: str, options: List[Option]) -> tuple[str, Optional[AgentStance]]:
    """Parse a board-mode reply into (full_text, stance). stance is None on malformed
    output or an option the agent invented that isn't in the declared list — the caller
    keeps the agent's previous stance unchanged in that case."""
    m = _BOARD_REPLY_RE.search(reply)
    if not m:
        return reply.strip(), None

    stance_raw, option_raw, reason_raw, full_raw = m.groups()
    full_text = full_raw.strip()

    stance_key = _normalize_stance(stance_raw)
    option_raw = option_raw.strip()
    matched = next((o for o in options if o.label.strip().lower() == option_raw.lower()), None)
    if not stance_key or not matched:
        return full_text, None

    reason = _cap_words(reason_raw.strip(), 8)
    return full_text, AgentStance(stance=stance_key, option_id=matched.id, reason=reason, full_text=full_text)


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
        self, topic: str, rules: RuleSet, rules_of_engagement: List[RuleOfEngagement], options: List[Option]
    ) -> str:
        rules_text = self._format_rules(rules_of_engagement)
        base_instructions = rules.agent_instructions.strip() or _DEFAULT_SPEAKING_INSTRUCTIONS
        speaking_instructions = base_instructions + (_board_instruction(options) if options else _POINT_INSTRUCTION)
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
        options: List[Option] = [],
    ) -> tuple[str, str, Optional[AgentStance]]:
        """Return (content, summary, stance). stance is None outside board mode, or when
        the model's board-mode output couldn't be parsed."""
        system_content = self._build_system_prompt(topic, rules, rules_of_engagement, options)

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

        if options:
            content, stance = _parse_board_reply(reply, options)
            summary = stance.reason if stance else ""
            return content, summary, stance

        content, summary = _parse_reply(reply)
        return content, summary, None


def _parse_reply(reply: str) -> tuple[str, str]:
    """Split 'POINT: X | full reply' into (full_reply, summary). Falls back to (reply, '')."""
    m = re.search(r'POINT:\s*(.+?)\s*\|\s*(.+)', reply, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return reply, ''
