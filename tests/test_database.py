from sqlalchemy import inspect, text
from sqlmodel import create_engine

import database


# Columns as they existed before the board-legibility change: `package` has no `options`
# and `user` has no `avatar_url`. Mirrors the real pre-existing schema closely enough that
# `ALTER TABLE ... ADD COLUMN` is a meaningful operation against it.
_LEGACY_SCHEMA = [
    """
    CREATE TABLE package (
        id INTEGER NOT NULL PRIMARY KEY,
        class_tag VARCHAR NOT NULL,
        name VARCHAR NOT NULL,
        topic VARCHAR NOT NULL,
        goal VARCHAR NOT NULL DEFAULT '',
        constraints VARCHAR NOT NULL DEFAULT '[]',
        rule_set_id INTEGER,
        agent_prompt_template VARCHAR NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE user (
        id INTEGER NOT NULL PRIMARY KEY,
        username VARCHAR NOT NULL,
        password_hash VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        class_tag VARCHAR NOT NULL DEFAULT '',
        system_prompt_override VARCHAR
    )
    """,
]


def _legacy_engine(tmp_path):
    """A temp SQLite DB carrying the pre-board-mode schema, built with raw SQL so that
    SQLModel.metadata.create_all() never gets a chance to add the new columns for us."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.connect() as conn:
        for ddl in _LEGACY_SCHEMA:
            conn.execute(text(ddl))
        conn.execute(text(
            "INSERT INTO package (class_tag, name, topic) VALUES ('demo', 'Legacy pkg', 'Legacy topic')"
        ))
        conn.execute(text(
            "INSERT INTO user (username, password_hash, display_name) VALUES ('kid', 'x', 'Kid')"
        ))
        conn.commit()
    return engine


def test_legacy_db_starts_without_the_new_columns(tmp_path):
    """Guards the fixture itself: if this ever starts failing, the migration test below
    would be passing vacuously."""
    engine = _legacy_engine(tmp_path)
    insp = inspect(engine)

    assert "options" not in {c["name"] for c in insp.get_columns("package")}
    assert "avatar_url" not in {c["name"] for c in insp.get_columns("user")}


def test_migrate_adds_options_and_avatar_columns_to_an_existing_db(tmp_path):
    """The path that actually matters: upgrading a DB file that predates board mode.
    Fails if either new ALTER TABLE line is removed from database._migrate."""
    engine = _legacy_engine(tmp_path)

    database._migrate(engine)

    insp = inspect(engine)
    package_columns = {c["name"] for c in insp.get_columns("package")}
    user_columns = {c["name"] for c in insp.get_columns("user")}

    assert "options" in package_columns
    assert "avatar_url" in user_columns


def test_migrate_preserves_existing_rows_and_defaults(tmp_path):
    """Existing rows survive the upgrade and pick up the new columns' defaults."""
    engine = _legacy_engine(tmp_path)

    database._migrate(engine)

    with engine.connect() as conn:
        options = conn.execute(text("SELECT options FROM package WHERE name = 'Legacy pkg'")).scalar_one()
        avatar_url = conn.execute(text("SELECT avatar_url FROM user WHERE username = 'kid'")).scalar_one()

    assert options == "[]"
    assert avatar_url is None


def test_migrate_is_idempotent(tmp_path):
    """Running the migration twice (every app boot re-runs it) is a no-op, not an error."""
    engine = _legacy_engine(tmp_path)

    database._migrate(engine)
    database._migrate(engine)

    insp = inspect(engine)
    assert "options" in {c["name"] for c in insp.get_columns("package")}
    assert "avatar_url" in {c["name"] for c in insp.get_columns("user")}


def test_create_db_and_tables_adds_options_and_avatar_columns(tmp_path):
    """Fresh-DB path: metadata.create_all() declares the new columns straight from the
    model classes. Keeps the model definitions honest; the migration coverage is above."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_db_and_tables(test_engine)

    insp = inspect(test_engine)
    package_columns = {c["name"] for c in insp.get_columns("package")}
    user_columns = {c["name"] for c in insp.get_columns("user")}

    assert "options" in package_columns
    assert "avatar_url" in user_columns
