"""SQLite example; each request closes its own connection."""
import sqlite3
from contextlib import closing
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.industry_apps.sdk import AppContribution


class NewRecord(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def database(context):
    return context.workspace_data_dir('local') / 'records.db'


def register(context):
    file = database(context)
    with closing(sqlite3.connect(file)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, title TEXT NOT NULL)')
        db.commit()
    router = APIRouter()

    @router.get('/records')
    def records():
        with closing(sqlite3.connect(file)) as db:
            return {'records': [{'id': row[0], 'title': row[1]} for row in db.execute('SELECT id, title FROM records ORDER BY id DESC')]}

    @router.post('/records')
    def create(body: NewRecord):
        if not body.title.strip():
            raise HTTPException(422, '请输入内容')
        with closing(sqlite3.connect(file)) as db:
            cursor = db.execute('INSERT INTO records(title) VALUES (?)', (body.title.strip(),))
            db.commit()
            return {'id': cursor.lastrowid, 'title': body.title.strip()}

    return AppContribution(router=router)


def check(context):
    with closing(sqlite3.connect(f'file:{database(context).as_posix()}?mode=ro', uri=True)) as db:
        db.execute('SELECT id, title FROM records LIMIT 1').fetchall()
