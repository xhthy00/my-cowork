"""Used only by the generated schema-v2 example; v1 never imports this file."""
import sqlite3
from contextlib import closing


def migrate(context):
    for path in context.data_root.glob("*/tasks.db"):
        with closing(sqlite3.connect(path)) as database:
            columns = {row[1] for row in database.execute("PRAGMA table_info(tasks)")}
            if not {"id", "title", "done"}.issubset(columns):
                raise ValueError("Unrecognized legacy task schema")
            with database:
                if "note" not in columns:
                    database.execute("ALTER TABLE tasks ADD COLUMN note TEXT NOT NULL DEFAULT ''")


def check(context):
    for path in context.data_root.glob("*/tasks.db"):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
            columns = {row[1] for row in database.execute("PRAGMA table_info(tasks)")}
            if not {"id", "title", "done", "note"}.issubset(columns):
                raise ValueError("Task database is incompatible with this version")
