from sqlalchemy import inspect
from sqlmodel import create_engine

import database


def test_create_db_and_tables_adds_options_and_avatar_columns(tmp_path):
    test_engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_db_and_tables(test_engine)

    insp = inspect(test_engine)
    package_columns = {c["name"] for c in insp.get_columns("package")}
    user_columns = {c["name"] for c in insp.get_columns("user")}

    assert "options" in package_columns
    assert "avatar_url" in user_columns
