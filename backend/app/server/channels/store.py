"""SQLite persistence for channel plugins, pairings, users, and settings."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


PAIRING_TTL_MS = 10 * 60 * 1000


class ChannelStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channel_plugins (
              plugin_id TEXT PRIMARY KEY,
              type TEXT NOT NULL,
              name TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0,
              connected INTEGER NOT NULL DEFAULT 0,
              has_token INTEGER NOT NULL DEFAULT 0,
              status TEXT,
              last_connected INTEGER,
              config TEXT,
              updated_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS channel_pairings (
              code TEXT PRIMARY KEY,
              platform_user_id TEXT NOT NULL,
              platform_type TEXT NOT NULL,
              display_name TEXT,
              chat_id TEXT,
              requested_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS channel_users (
              id TEXT PRIMARY KEY,
              platform_user_id TEXT NOT NULL,
              platform_type TEXT NOT NULL,
              display_name TEXT,
              chat_id TEXT,
              authorized_at INTEGER NOT NULL,
              last_active INTEGER,
              UNIQUE(platform_type, platform_user_id)
            );
            CREATE TABLE IF NOT EXISTS channel_sessions (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              platform_type TEXT NOT NULL,
              chat_id TEXT,
              conversation_id TEXT,
              task_id TEXT,
              created_at INTEGER NOT NULL,
              last_activity INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS channel_settings (
              platform TEXT PRIMARY KEY,
              assistant_id TEXT,
              enabled_skill_ids TEXT,
              default_model_id TEXT,
              default_model_use TEXT
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_plugin(
        self,
        plugin_id: str,
        *,
        type: str,
        name: str,
        enabled: int | None = None,
        connected: int | None = None,
        has_token: int | None = None,
        status: str | None = None,
        last_connected: int | None = None,
    ) -> None:
        now = int(time.time() * 1000)
        row = self._conn.execute(
            "SELECT plugin_id FROM channel_plugins WHERE plugin_id = ?",
            (plugin_id,),
        ).fetchone()
        if row is None:
            self._conn.execute(
                """
                INSERT INTO channel_plugins(
                  plugin_id, type, name, enabled, connected, has_token, status,
                  last_connected, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    plugin_id,
                    type,
                    name,
                    enabled or 0,
                    connected or 0,
                    has_token or 0,
                    status,
                    last_connected,
                    now,
                ),
            )
        else:
            fields: list[str] = ["updated_at = ?"]
            vals: list[Any] = [now]
            for col, val in (
                ("enabled", enabled),
                ("connected", connected),
                ("has_token", has_token),
                ("status", status),
                ("last_connected", last_connected),
                ("type", type),
                ("name", name),
            ):
                if val is not None:
                    fields.append(f"{col} = ?")
                    vals.append(val)
            vals.append(plugin_id)
            self._conn.execute(
                f"UPDATE channel_plugins SET {', '.join(fields)} WHERE plugin_id = ?",
                vals,
            )
        self._conn.commit()

    def get_plugin(self, plugin_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM channel_plugins WHERE plugin_id = ?",
            (plugin_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_plugins(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM channel_plugins").fetchall()
        return [dict(r) for r in rows]

    def create_pairing(
        self,
        *,
        platform_user_id: str,
        platform_type: str,
        display_name: str = "",
        chat_id: str = "",
    ) -> dict[str, Any]:
        now = int(time.time() * 1000)
        self._conn.execute(
            "DELETE FROM channel_pairings WHERE platform_type = ? AND platform_user_id = ?",
            (platform_type, platform_user_id),
        )
        rec = {
            "code": uuid.uuid4().hex[:8].upper(),
            "platform_user_id": platform_user_id,
            "platform_type": platform_type,
            "display_name": display_name,
            "chat_id": chat_id,
            "requested_at": now,
            "expires_at": now + PAIRING_TTL_MS,
        }
        self._conn.execute(
            """
            INSERT INTO channel_pairings(
              code, platform_user_id, platform_type, display_name, chat_id,
              requested_at, expires_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                rec["code"],
                rec["platform_user_id"],
                rec["platform_type"],
                rec["display_name"],
                rec["chat_id"],
                rec["requested_at"],
                rec["expires_at"],
            ),
        )
        self._conn.commit()
        return rec

    def get_pairing(self, code: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM channel_pairings WHERE code = ?",
            (code,),
        ).fetchone()
        return dict(row) if row else None

    def list_pairings(self, platform_type: str | None = None) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        self._conn.execute("DELETE FROM channel_pairings WHERE expires_at < ?", (now,))
        self._conn.commit()
        if platform_type:
            rows = self._conn.execute(
                "SELECT * FROM channel_pairings WHERE platform_type = ? ORDER BY requested_at DESC",
                (platform_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM channel_pairings ORDER BY requested_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_pairing(self, code: str) -> None:
        self._conn.execute("DELETE FROM channel_pairings WHERE code = ?", (code,))
        self._conn.commit()

    def get_user(self, platform_type: str, platform_user_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM channel_users WHERE platform_type = ? AND platform_user_id = ?",
            (platform_type, platform_user_id),
        ).fetchone()
        return dict(row) if row else None

    def list_users(self, platform_type: str | None = None) -> list[dict[str, Any]]:
        if platform_type:
            rows = self._conn.execute(
                "SELECT * FROM channel_users WHERE platform_type = ? ORDER BY authorized_at DESC",
                (platform_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM channel_users ORDER BY authorized_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def authorize_user(
        self,
        *,
        platform_user_id: str,
        platform_type: str,
        display_name: str = "",
        chat_id: str = "",
    ) -> dict[str, Any]:
        now = int(time.time() * 1000)
        existing = self.get_user(platform_type, platform_user_id)
        if existing:
            self._conn.execute(
                """
                UPDATE channel_users SET display_name = ?, chat_id = ?, last_active = ?
                WHERE id = ?
                """,
                (display_name or existing.get("display_name"), chat_id, now, existing["id"]),
            )
            self._conn.commit()
            return {**existing, "display_name": display_name or existing.get("display_name"), "chat_id": chat_id, "last_active": now}
        rec = {
            "id": uuid.uuid4().hex,
            "platform_user_id": platform_user_id,
            "platform_type": platform_type,
            "display_name": display_name,
            "chat_id": chat_id,
            "authorized_at": now,
            "last_active": now,
        }
        self._conn.execute(
            """
            INSERT INTO channel_users(
              id, platform_user_id, platform_type, display_name, chat_id,
              authorized_at, last_active
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                rec["id"],
                rec["platform_user_id"],
                rec["platform_type"],
                rec["display_name"],
                rec["chat_id"],
                rec["authorized_at"],
                rec["last_active"],
            ),
        )
        self._conn.commit()
        return rec

    def touch_user(self, platform_type: str, platform_user_id: str, chat_id: str = "") -> None:
        now = int(time.time() * 1000)
        if chat_id:
            self._conn.execute(
                """
                UPDATE channel_users SET last_active = ?, chat_id = ?
                WHERE platform_type = ? AND platform_user_id = ?
                """,
                (now, chat_id, platform_type, platform_user_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE channel_users SET last_active = ?
                WHERE platform_type = ? AND platform_user_id = ?
                """,
                (now, platform_type, platform_user_id),
            )
        self._conn.commit()

    def revoke_user(self, user_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM channel_users WHERE id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_settings(self, platform: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM channel_settings WHERE platform = ?",
            (platform,),
        ).fetchone()
        if not row:
            return {
                "platform": platform,
                "assistant": None,
                "default_model": None,
            }
        assistant = None
        if row["assistant_id"]:
            assistant = {"assistant_id": row["assistant_id"]}
        default_model = None
        if row["default_model_id"] and row["default_model_use"]:
            default_model = {
                "id": row["default_model_id"],
                "use_model": row["default_model_use"],
            }
        return {
            "platform": platform,
            "assistant": assistant,
            "default_model": default_model,
            "enabled_skill_ids": json.loads(row["enabled_skill_ids"] or "[]"),
        }

    def set_assistant(self, platform: str, assistant_id: str) -> None:
        self._conn.execute(
            """
            INSERT INTO channel_settings(platform, assistant_id)
            VALUES (?, ?)
            ON CONFLICT(platform) DO UPDATE SET assistant_id = excluded.assistant_id
            """,
            (platform, assistant_id),
        )
        self._conn.commit()

    def set_default_model(self, platform: str, model_id: str, use_model: str) -> None:
        self._conn.execute(
            """
            INSERT INTO channel_settings(platform, default_model_id, default_model_use)
            VALUES (?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
              default_model_id = excluded.default_model_id,
              default_model_use = excluded.default_model_use
            """,
            (platform, model_id, use_model),
        )
        self._conn.commit()
