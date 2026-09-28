"""A small task manager loaded inside the existing FastAPI process."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.industry_apps.sdk import AppContext, AppContribution


class NewTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    workspace_id: str = "local"

    @field_validator("title")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title is required")
        return value


class TaskPatch(BaseModel):
    done: bool
    workspace_id: str = "local"


def register(context: AppContext) -> AppContribution:
    router = APIRouter()

    def connect(workspace_id: str) -> sqlite3.Connection:
        database = context.workspace_data_dir(workspace_id) / "tasks.db"
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)"
        )
        connection.commit()
        return connection

    @router.get("/tasks")
    def list_tasks(workspace_id: str = "local") -> dict:
        with closing(connect(workspace_id)) as db:
            rows = db.execute("SELECT id, title, done FROM tasks ORDER BY id DESC").fetchall()
            return {"tasks": [{**dict(row), "done": bool(row["done"])} for row in rows]}

    @router.post("/tasks")
    def create_task(body: NewTask) -> dict:
        with closing(connect(body.workspace_id)) as db:
            cursor = db.execute("INSERT INTO tasks (title) VALUES (?)", (body.title.strip(),))
            db.commit()
            return {"id": cursor.lastrowid, "title": body.title.strip(), "done": False}

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: int, body: TaskPatch) -> dict:
        with closing(connect(body.workspace_id)) as db:
            cursor = db.execute(
                "UPDATE tasks SET done = ? WHERE id = ?",
                (int(body.done), task_id),
            )
            db.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="task not found")
            return {"id": task_id, "done": body.done}

    return AppContribution(router=router)
