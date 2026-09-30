"""A small task manager loaded inside the existing FastAPI process."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.industry_apps.sdk import AppContext, AppContribution, AppTool, AppToolCallContext


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


class QueryTasks(BaseModel):
    done: bool | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CreateSubtask(BaseModel):
    parent_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)


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
        connection.execute('CREATE TABLE IF NOT EXISTS task_parents (task_id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL)')
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

    def agent_list_tasks(_call: AppToolCallContext, args: QueryTasks) -> dict:
        # The host Space and this plugin's local partition are deliberately distinct.
        scope = _call.business
        if scope is not None and scope.get('partition') != 'local':
            raise ValueError('此示例只支持 local 数据分区')
        rows = list_tasks()["tasks"]
        if scope is not None:
            selected = scope.get('selection', [])
            rows = [row for row in rows if row['id'] in selected]
            if len(rows) != len(set(selected)):
                raise ValueError('选中的任务已删除，请返回页面重新选择')
        if args.done is not None:
            rows = [row for row in rows if row["done"] == args.done]
        return {"total": len(rows), "tasks": rows[:args.limit]}

    def agent_create_subtask(call: AppToolCallContext, args: CreateSubtask) -> dict:
        if call.business is not None:
            if call.business.get('partition') != 'local' or args.parent_id not in call.business.get('selection', []):
                raise PermissionError('父任务不在本次选择范围内')
        with closing(connect('local')) as db:
            if not db.execute('SELECT id FROM tasks WHERE id=?', (args.parent_id,)).fetchone():
                raise ValueError('父任务已删除')
            with db:
                cursor = db.execute('INSERT INTO tasks(title) VALUES(?)', (args.title.strip(),))
                db.execute('INSERT INTO task_parents VALUES(?,?)', (cursor.lastrowid, args.parent_id))
            return {'id': cursor.lastrowid, 'parent_id': args.parent_id, 'title': args.title.strip(), 'done': False}

    return AppContribution(router=router, tools=[AppTool(
        name="list_tasks",
        title="查询任务",
        description="查询任务管理样例中的任务及完成状态。",
        args_schema=QueryTasks,
        run=agent_list_tasks,
    ), AppTool(name='create_subtask', title='创建子任务', description='在指定父任务下创建一条子任务。',
               args_schema=CreateSubtask, run=agent_create_subtask, access='write')])
