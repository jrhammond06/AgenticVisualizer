from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session as DBSession

import config

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, echo=False, connect_args=connect_args)


def _migrate():
    migrations = [
        "ALTER TABLE user ADD COLUMN system_prompt_override TEXT",
        "ALTER TABLE ruleset ADD COLUMN agent_instructions TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE package ADD COLUMN agent_prompt_template TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE formmodule ADD COLUMN preamble TEXT NOT NULL DEFAULT ''",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    _migrate()


def get_db():
    with DBSession(engine) as session:
        yield session
