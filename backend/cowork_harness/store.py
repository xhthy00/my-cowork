"""Durable execution records and replay. Checkpoints remain owned by LangGraph."""
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone


class RunStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, request TEXT NOT NULL,
              thread_id TEXT NOT NULL, status TEXT NOT NULL, pending TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY (run_id, seq));
            CREATE TABLE IF NOT EXISTS epochs (
              session_id TEXT NOT NULL, profile TEXT NOT NULL, thread_id TEXT NOT NULL,
              PRIMARY KEY (session_id, profile));
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS event_calls ON events(run_id, json_extract(payload, '$.type'), json_extract(payload, '$.call_id'))")
        # An in-flight model/tool cannot safely be replayed after a crash.
        for row in self.db.execute("SELECT id, thread_id FROM runs WHERE status IN ('running', 'queued')").fetchall():
            self.event(row["id"], {"type": "graph.end", "status": "error",
                       "error": "执行进程中断；工具副作用需对账后再重试"})
            self.update(row["id"], "interrupted")
            self.db.execute('DELETE FROM epochs WHERE thread_id=?', (row['thread_id'],))
        self.db.commit()

    def create(self, request: dict, profile: str) -> tuple[dict, bool]:
        encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        row = self.get(request["task_id"])
        if row:
            if row["fingerprint"] != fingerprint:
                raise ValueError("同一 task_id 不能用于不同请求")
            return row, False
        epoch = self.db.execute('SELECT thread_id FROM epochs WHERE session_id=? AND profile=?',
                                (request['session_id'], profile)).fetchone()
        thread_id = epoch[0] if epoch else uuid.uuid4().hex
        self.db.execute("INSERT OR IGNORE INTO epochs VALUES (?, ?, ?)",
                        (request["session_id"], profile, thread_id))
        self.db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, 'queued', NULL, ?)",
                        (request["task_id"], fingerprint, encoded, thread_id, time.time()))
        self.db.commit()
        return self.get(request["task_id"]), True

    def get(self, run_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["request"] = json.loads(result["request"])
        result["pending"] = json.loads(result["pending"]) if result["pending"] else None
        return result

    def update(self, run_id: str, status: str, pending=None):
        self.db.execute("UPDATE runs SET status=?, pending=? WHERE id=?",
                        (status, json.dumps(pending) if pending else None, run_id))
        self.db.commit()

    def event(self, run_id: str, event: dict) -> dict:
        seq = self.db.execute("SELECT COALESCE(MAX(seq), 0)+1 FROM events WHERE run_id=?",
                              (run_id,)).fetchone()[0]
        row = self.get(run_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        content = event.get('payload') or {key: value for key, value in event.items() if key != 'type'}
        payload = {**event, "payload": {**content, "task_id": run_id, "session_id": row["request"]["session_id"], "timestamp": timestamp}, "protocol_version": 1, "task_id": run_id,
                   "run_id": run_id, "session_id": row["request"]["session_id"],
                   "seq": seq, "event_id": f"{run_id}:{seq}", "timestamp": timestamp}
        self.db.execute("INSERT INTO events VALUES (?, ?, ?)",
                        (run_id, seq, json.dumps(payload, ensure_ascii=False, default=str)))
        self.db.commit()
        return payload

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT payload FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after))]

    def has_tool_start(self, run_id, call_id):
        return self.db.execute("SELECT 1 FROM events WHERE run_id=? AND json_extract(payload, '$.type')='tool.start' AND json_extract(payload, '$.call_id')=? LIMIT 1",
                               (run_id, call_id)).fetchone() is not None

    def close(self):
        self.db.close()

    def discard_epoch(self, thread_id):
        self.db.execute('DELETE FROM epochs WHERE thread_id=?', (thread_id,))
        self.db.commit()
