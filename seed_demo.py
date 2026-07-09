#!/usr/bin/env python3
"""
seed_demo.py — Annotated demo seed script for AgenticVisualizer
================================================================

This script creates a complete, ready-to-run negotiation scenario without
needing to touch the admin UI. Run it once to populate the database; running
it again is safe (existing rows are skipped, not duplicated).

HOW TO RUN
----------
  Windows (.venv):    .venv\\Scripts\\python.exe seed_demo.py
  Mac/Linux (venv):   python seed_demo.py

The scenario it creates
-----------------------
Four 10-year-olds — Emma, Jake, Sofia, and Marcus — are planning the food
menu for a class party. They have a $100 budget.

This scenario is designed to demonstrate three things in a classroom:

  1. How AGENT PERSONALITY shapes negotiation behaviour.
     Each child has a distinct food situation and personal style:
       - Emma is vegetarian (no meat) and wants dessert.
       - Jake has a severe nut allergy and gets anxious when nuts come up.
       - Sofia is lactose intolerant (no dairy/cheese) and is constructive.
       - Marcus is a picky eater who needs coaxing but can be persuaded.

  2. How PROCESS RULES constrain agent behaviour.
     The rule set requires unanimous agreement and civil discussion.
     Students can observe: what happens when the rules push back on an agent
     that would naturally bulldoze the conversation?

  3. How HARD CONSTRAINTS create genuine negotiation tension.
     The dietary inclusion constraint means the group can't just vote to have
     cheese pizza (Sofia can't eat it) or a meat-only spread (Emma can't eat
     it). They must actively find foods that work for everyone.

     The tensions are real:
       - Cheese pizza: works for Emma, Jake, Marcus — but not Sofia (dairy).
       - Hot dogs: works for Jake, Sofia, Marcus — but not Emma (meat).
       - Peanut butter anything: works for nobody (Jake's allergy).
       - Tacos: potentially works for everyone — but Marcus finds them "weird".

     A resolution is possible, but it requires actual compromise.

AFTER RUNNING THIS SCRIPT
-------------------------
  1. Start the app:  python main.py
  2. Log in as admin at http://127.0.0.1:8000
  3. Admin > Packages tab > filter by class "demo-party"
  4. Click "Load for Session" next to "Party Menu Planning"
  5. Select all four students > click "Load for Session"
  6. You are redirected to /session — click "Start Round"

Student logins (for demonstrating the student form view):
  emma / password
  jake / password
  sofia / password
  marcus / password
"""

import json
import os
import sys

# Add the project root to the path so we can import project modules directly.
sys.path.insert(0, os.path.dirname(__file__))

from sqlmodel import Session as DBSession, select

from database import engine, create_db_and_tables
from db_models import ClassTagDB, PackageDB, RuleSetDB, User
from auth import hash_password

# Ensure the database file and all tables exist before we try to write to them.
create_db_and_tables()


# ── 1. CLASS ──────────────────────────────────────────────────────────────────
#
# A "class" in AgenticVisualizer is just a tag that groups students together.
# It controls which form modules students can see and which packages appear
# in the admin dropdowns. You can have multiple classes on one server.

CLASS_TAG = "demo-party"


# ── 2. AGENT IDENTITY TEMPLATE ────────────────────────────────────────────────
#
# The agent identity template (set on the package) defines WHO agents ARE in
# this scenario — the situational framing or role. It is a Python-style format
# string with named placeholders that the system fills in at load time.
#
# Available placeholders:
#   {name}                 — the agent's display name (the student's name)
#   {goal}                 — the agent's stated goal (currently always a generic
#                            "Participate in the negotiation" — you can override
#                            the full framing here instead)
#   {topic}                — the negotiation topic (from the package)
#   {rules}                — all rules of engagement, formatted as a list
#                            (combines package constraints + rule set rules)
#   {system_prompt}        — the agent's personal system prompt (from the
#                            student's form answers, or a manual override)
#   {speaking_instructions}— the rule set's "agent speaking instructions" block
#
# DESIGN NOTE: This template separates IDENTITY from PERSONALITY.
#   Identity = who you are in this scenario (a 10-year-old at a party meeting)
#   Personality = your specific preferences, style, dietary situation, etc.
#                 (lives in {system_prompt}, set per student)
#
# This separation lets you reuse the same student profiles across different
# scenario framings by just changing the identity template on the package.

AGENT_PROMPT_TEMPLATE = """\
You are {name}, a 10-year-old planning a class party menu with your three \
friends — Emma, Jake, Sofia, and Marcus.

About you and what you like to eat:
{system_prompt}

What you're deciding: {topic}

Ground rules for this conversation:
{rules}

{speaking_instructions}\
"""


# ── 3. AGENT SPEAKING INSTRUCTIONS ───────────────────────────────────────────
#
# Agent speaking instructions live on the rule set and control HOW agents
# communicate: their tone, reply length, and format. They are injected into
# every agent's system prompt via the {speaking_instructions} placeholder.
#
# These are NOT monitored by the referee. They are purely style/format
# directives. Think of them as the "house style" for this rule set.
#
# If this field is left blank, a built-in default is used (conversational,
# 1–2 sentences, no bullet points, address others by name).
#
# CONTRAST WITH RULES: a rule like "maintain a respectful tone" IS monitored
# by the referee and can trigger a warning. An instruction like "speak like a
# 10-year-old" shapes the output format but isn't enforced — the LLM just
# follows it as a writing style directive.

AGENT_INSTRUCTIONS = """\
How to talk in this meeting:
- Sound like a real 10-year-old: enthusiastic, friendly, and occasionally \
silly — but always kind.
- Keep each turn to 1 or 2 sentences.
- You can suggest a food, agree with someone, ask a question, or raise a \
concern — but never be rude or dismissive.
- Nothing goes on the final menu unless all four friends say yes. Say \
something like "I'm okay with that!" to agree explicitly.
- If someone mentions a dietary restriction, take it seriously and suggest \
an alternative if you can.
- Use your friends' names when it helps move the conversation along.\
"""


# ── 4. RULES OF ENGAGEMENT ────────────────────────────────────────────────────
#
# Rules are statements that the referee monitors. Each rule has:
#
#   name       — short label (shown in referee evaluations and agent prompts)
#   text       — the actual rule text
#   severity   — "guideline" (referee warns) or "hard_constraint" (referee
#                blocks consensus until satisfied)
#   applies_to — "referee" (referee sees it, agents don't get it injected),
#                "agents" (injected into agent prompts, referee doesn't enforce),
#                "both" (injected into agent prompts AND enforced by referee)
#
# These two rules live on the RULE SET (reusable across packages).
# The dietary inclusion rule lives on the PACKAGE (scenario-specific).
#
# WHY "referee" not "both" here?
#   The agent identity template already puts {rules} into every agent's system
#   prompt, so agents can already see all rules. Setting applies_to: "referee"
#   avoids duplicating the rule text inside the {system_prompt} block.

RULES = [
    {
        "name": "Civil discussion",
        "text": (
            "Everyone gets a turn to speak. Listen before responding "
            "and acknowledge what others said before moving on."
        ),
        "severity": "guideline",
        "applies_to": "referee",
    },
    {
        "name": "Unanimous agreement",
        "text": (
            "A food item is only added to the final menu when all four friends "
            "have explicitly said they agree to it."
        ),
        "severity": "guideline",
        "applies_to": "referee",
    },
]

# This is a PACKAGE-LEVEL hard constraint, not a rule set rule.
# The distinction: package constraints are topic-specific outcome requirements
# (what a valid solution must look like). Rule set rules are process rules
# (how the discussion should run). Package constraints are always sent to the
# referee only — they appear in {rules} in the agent template but are not
# re-injected into {system_prompt}.
#
# WHY a hard constraint and not a guideline?
#   We want the referee to actively BLOCK consensus if the proposed menu
#   leaves anyone without food. A guideline would only produce a warning.

DIETARY_CONSTRAINT = {
    "name": "Dietary inclusion",
    "text": (
        "The final agreed menu must include at least one food item that every "
        "child can actually eat. A menu made entirely of food that any one "
        "child cannot eat due to a dietary restriction is not acceptable."
    ),
    "severity": "hard_constraint",
    "applies_to": "referee",
}


# ── 5. NEGOTIATION TOPIC ──────────────────────────────────────────────────────
#
# The topic is the central question agents are trying to resolve. It appears
# in the {topic} placeholder in the agent identity template and is shown
# on the session page.

TOPIC = (
    "What food should we serve at our class party? "
    "We have a $100 budget for all four of us."
)


# ── 6. STUDENT PROFILES ───────────────────────────────────────────────────────
#
# Each student's system_prompt_override is the PERSONALITY component of their
# agent — what they personally want, their dietary situation, and their
# negotiating style. It fills the {system_prompt} placeholder in the identity
# template above.
#
# In a real class, this content would come from students' form answers (the
# form's system prompt template renders their answers into this text). For a
# demo/seed scenario we set it directly as a "manual override," which bypasses
# the form template entirely.
#
# DESIGN NOTE — the four characters are chosen to create genuine tension:
#
#   Emma (vegetarian):   Pizza works, tacos work, fruit works. No meat at all.
#   Jake (nut allergy):  Pizza works, hot dogs work, chips work. Nothing with
#                        peanuts or tree nuts — a medical necessity.
#   Sofia (no dairy):    Tacos work, fruit works, veggie sticks work. Regular
#                        cheese pizza does NOT work — dairy makes her sick.
#   Marcus (picky):      Plain nuggets, chips, bread rolls. Familiar foods only.
#                        Can be persuaded, but needs encouragement.
#
#   Key tensions to watch for:
#   - Pizza: Emma/Jake/Marcus say yes, Sofia says no (cheese = dairy).
#   - Hot dogs: Jake/Sofia/Marcus say yes, Emma says no (meat).
#   - Tacos: Emma/Sofia probably yes, Marcus probably no, Jake needs to check.
#   - Fruit/veggie sticks: probably universal agreement but Marcus may resist.
#   - Any dessert: Emma will advocate for it; the others may or may not care.

STUDENTS = [
    {
        "username": "emma",
        "display_name": "Emma",
        "system_prompt_override": (
            "You are vegetarian — you don't eat any meat at all: no chicken, hot dogs, "
            "beef, pepperoni, or fish. Cheese and dairy are completely fine for you. "
            "You love cheese pizza, pasta, fruit salad, and anything chocolate for dessert. "
            "You're good at compromise and genuinely care about making sure everyone feels included. "
            "You really want at least one dessert on the final menu and you'll keep gently pushing for it."
        ),
    },
    {
        "username": "jake",
        "display_name": "Jake",
        "system_prompt_override": (
            "You have a serious peanut and tree-nut allergy — even small traces can send you to hospital, "
            "so you always ask about ingredients. "
            "You love hot dogs, pepperoni pizza, plain chips, and soda. "
            "You're enthusiastic and jump into conversations quickly; you can get a little loud. "
            "You become genuinely anxious if anyone suggests anything nut-related and you'll push back firmly, "
            "but you trust your friends to look out for you."
        ),
    },
    {
        "username": "sofia",
        "display_name": "Sofia",
        "system_prompt_override": (
            "You are lactose intolerant — dairy makes you really sick, so you can't have cheese, "
            "milk, butter, cream, or ice cream. This means regular cheese pizza doesn't work for you. "
            "You love tacos with salsa and guacamole, veggie sticks with hummus, fresh fruit, and sparkling water. "
            "You're thoughtful and always check whether a suggestion works for everyone, not just yourself. "
            "You'll gently point out when something doesn't work for you and offer an alternative straight away."
        ),
    },
    {
        "username": "marcus",
        "display_name": "Marcus",
        "system_prompt_override": (
            "You're a pretty picky eater — strong flavours, unfamiliar sauces, and weird textures put you off. "
            "You like plain chicken nuggets, plain chips, plain bread rolls, and apple juice. "
            "You're not trying to be difficult; new foods just make you uneasy. "
            "You can be talked into trying something if your friends are patient and enthusiastic about it, "
            "but you need a bit of convincing. You push back with 'ew' or 'that sounds gross' but you do "
            "want everyone to have a good time."
        ),
    },
]


# ── 7. WRITE TO DATABASE ──────────────────────────────────────────────────────
#
# Everything below is database insertion. The pattern throughout:
#   - Check if the row already exists (by a unique field like name or tag).
#   - If it doesn't exist, create it.
#   - If it does, skip it (print a note and move on).
#
# This makes the script safe to run multiple times without creating duplicates.

with DBSession(engine) as db:

    # --- Class ---
    # Create the class tag that groups all demo students and the package together.
    existing_class = db.exec(
        select(ClassTagDB).where(ClassTagDB.tag == CLASS_TAG)
    ).first()
    if not existing_class:
        db.add(ClassTagDB(tag=CLASS_TAG, name="Demo — Party Planning"))
        db.commit()
        print(f"  Created class: {CLASS_TAG}")
    else:
        print(f"  Class already exists: {CLASS_TAG}")

    # --- Rule set ---
    # The rule set is created in the library and then linked to the package.
    # If you later want to reuse these exact process rules in a different
    # scenario (e.g. a budget negotiation with the same "civil + unanimous"
    # requirements), you'd just point that package at this same rule set.
    existing_rs = db.exec(
        select(RuleSetDB).where(RuleSetDB.name == "Party Planning — Civil & Inclusive")
    ).first()
    if not existing_rs:
        rs = RuleSetDB(
            name="Party Planning — Civil & Inclusive",
            description=(
                "Constructive, friendly discussion. "
                "Unanimous agreement required; dietary restrictions respected."
            ),
            rules=json.dumps(RULES),
            agent_instructions=AGENT_INSTRUCTIONS,
        )
        db.add(rs)
        db.commit()
        db.refresh(rs)
        print(f"  Created rule set: {rs.name} (id={rs.id})")
    else:
        rs = existing_rs
        print(f"  Rule set already exists: {rs.name} (id={rs.id})")

    # --- Package ---
    # The package ties together the topic, constraints, rule set, and the
    # agent identity template. When an admin clicks "Load for Session" on
    # this package, all of the above is pulled in automatically.
    existing_pkg = db.exec(
        select(PackageDB).where(PackageDB.name == "Party Menu Planning")
    ).first()
    if not existing_pkg:
        pkg = PackageDB(
            class_tag=CLASS_TAG,
            name="Party Menu Planning",
            topic=TOPIC,
            # The dietary inclusion constraint goes in the package (not the
            # rule set) because it is specific to THIS scenario — it would
            # make no sense to add it to a general-purpose "civil discussion"
            # rule set that might be reused for a budget or policy negotiation.
            constraints=json.dumps([DIETARY_CONSTRAINT]),
            rule_set_id=rs.id,
            agent_prompt_template=AGENT_PROMPT_TEMPLATE,
        )
        db.add(pkg)
        db.commit()
        db.refresh(pkg)
        print(f"  Created package: {pkg.name} (id={pkg.id})")
    else:
        print(f"  Package already exists: {existing_pkg.name} (id={existing_pkg.id})")

    # --- Students ---
    # Each student gets a login account and a manual system_prompt_override.
    # In a real class, the override would be empty and the system prompt would
    # be generated from form answers + the class's system prompt template.
    # Here we skip the form entirely and write the personality text directly.
    for s in STUDENTS:
        existing_user = db.exec(
            select(User).where(User.username == s["username"])
        ).first()
        if not existing_user:
            db.add(User(
                username=s["username"],
                password_hash=hash_password("password"),
                display_name=s["display_name"],
                class_tag=CLASS_TAG,
                system_prompt_override=s["system_prompt_override"],
            ))
            print(f"  Created student: {s['display_name']} (@{s['username']})")
        else:
            print(f"  Student already exists: {s['display_name']} (@{s['username']})")

    db.commit()

# ── 8. DONE ───────────────────────────────────────────────────────────────────

print()
print("Demo scenario ready.")
print(f"  Class:    {CLASS_TAG}")
print(f"  Package:  Party Menu Planning")
print(f"  Students: Emma, Jake, Sofia, Marcus  (password: 'password' for all)")
print()
print("To load:")
print("  Admin > Packages tab > filter by class 'demo-party'")
print("  'Load for Session' > select all four students > 'Load for Session'")
print()
print("Student login URL:  http://127.0.0.1:8000/form")
print("Session page URL:   http://127.0.0.1:8000/session")
