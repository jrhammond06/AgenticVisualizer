from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session as DBSession

import config
import db_models  # noqa: F401 - imported to register models with SQLModel.metadata

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, echo=False, connect_args=connect_args)


def _migrate(engine=engine):
    migrations = [
        "ALTER TABLE user ADD COLUMN system_prompt_override TEXT",
        "ALTER TABLE ruleset ADD COLUMN agent_instructions TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN agent_prompt_template TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE formmodule ADD COLUMN preamble TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN goal TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN options TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE user ADD COLUMN avatar_url TEXT",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass


def create_db_and_tables(engine=engine):
    SQLModel.metadata.create_all(engine)
    _migrate(engine)


def get_db():
    with DBSession(engine) as session:
        yield session
