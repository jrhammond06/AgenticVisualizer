#!/usr/bin/env python3
"""Seed a default demo scenario: four 10-year-olds planning a party menu.

Run once:  python3 seed_demo.py
Re-running is safe — existing rows are skipped, not duplicated.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlmodel import Session as DBSession, select

from database import engine, create_db_and_tables
from db_models import ClassTagDB, PackageDB, RuleSetDB, User
from auth import hash_password

create_db_and_tables()

# ── Constants ─────────────────────────────────────────────────────────────────

CLASS_TAG = "demo-party"

TOPIC = (
    "What food should we serve at our class party? "
    "We have a $100 budget for all four of us."
)

AGENT_PROMPT_TEMPLATE = """\
You are {name}, a 10-year-old planning a class party menu with your three friends — Emma, Jake, Sofia, and Marcus.

About you and what you like to eat:
{system_prompt}

What you're deciding: {topic}

Ground rules for this conversation:
{rules}

{speaking_instructions}\
"""

AGENT_INSTRUCTIONS = """\
How to talk in this meeting:
- Sound like a real 10-year-old: enthusiastic, friendly, and occasionally silly — but always kind.
- Keep each turn to 1 or 2 sentences.
- You can suggest a food, agree with someone, ask a question, or raise a concern — but never be rude or dismissive.
- Nothing goes on the final menu unless all four friends say yes. Say something like "I'm okay with that!" to agree explicitly.
- If someone mentions a dietary restriction, take it seriously and suggest an alternative if you can.
- Use your friends' names when it helps move the conversation along.\
"""

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

# This goes in the package as a hard constraint so the referee enforces it as a
# blocking condition on consensus, and it also appears in {rules} for agents.
DIETARY_CONSTRAINT = {
    "name": "Dietary inclusion",
    "text": (
        "The final agreed menu must include at least one food item that every child "
        "can actually eat. A menu made entirely of food that any one child cannot eat "
        "due to a dietary restriction is not acceptable."
    ),
    "severity": "hard_constraint",
    "applies_to": "referee",
}

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

# ── Seed ──────────────────────────────────────────────────────────────────────

with DBSession(engine) as db:

    # Class
    if not db.exec(select(ClassTagDB).where(ClassTagDB.tag == CLASS_TAG)).first():
        db.add(ClassTagDB(tag=CLASS_TAG, name="Demo — Party Planning"))
        db.commit()
        print(f"  Created class: {CLASS_TAG}")
    else:
        print(f"  Class already exists: {CLASS_TAG}")

    # Rule set
    rs = db.exec(select(RuleSetDB).where(RuleSetDB.name == "Party Planning — Civil & Inclusive")).first()
    if not rs:
        rs = RuleSetDB(
            name="Party Planning — Civil & Inclusive",
            description=(
                "Constructive, friendly discussion between kids. "
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
        print(f"  Rule set already exists: {rs.name} (id={rs.id})")

    # Package
    pkg = db.exec(select(PackageDB).where(PackageDB.name == "Party Menu Planning")).first()
    if not pkg:
        pkg = PackageDB(
            class_tag=CLASS_TAG,
            name="Party Menu Planning",
            topic=TOPIC,
            constraints=json.dumps([DIETARY_CONSTRAINT]),
            rule_set_id=rs.id,
            agent_prompt_template=AGENT_PROMPT_TEMPLATE,
        )
        db.add(pkg)
        db.commit()
        db.refresh(pkg)
        print(f"  Created package: {pkg.name} (id={pkg.id})")
    else:
        print(f"  Package already exists: {pkg.name} (id={pkg.id})")

    # Students
    for s in STUDENTS:
        existing = db.exec(select(User).where(User.username == s["username"])).first()
        if not existing:
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

print()
print("Demo scenario ready.")
print(f"  Class:    {CLASS_TAG}")
print(f"  Package:  Party Menu Planning")
print(f"  Students: Emma, Jake, Sofia, Marcus  (password: 'password' for all)")
print()
print("To run: Admin > Packages > filter by 'demo-party' > Load for Session >")
print("        select all four students > Load for Session")
