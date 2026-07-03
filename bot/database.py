"""
Async SQLite database layer.

Tables:
  - users:   one row per Telegram user, stores their IVASMS credentials
  - orders:  one row per OTP request (active/completed/cancelled)
  - stats:   simple key/value counters for the status panel
"""
from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

from .config import settings

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_user_id    INTEGER PRIMARY KEY,
    username            TEXT,
    first_name          TEXT,
    ivasms_email        TEXT,
    ivasms_password     TEXT,
    ivasms_cookies_json TEXT,
    auth_method         TEXT DEFAULT 'email',   -- 'email' | 'cookies'
    created_at          INTEGER NOT NULL,
    last_active_at      INTEGER NOT NULL,
    total_requests      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id    INTEGER NOT NULL,
    phone_range         TEXT,
    phone_number        TEXT,
    otp_message         TEXT,
    status              TEXT DEFAULT 'active',   -- 'active' | 'completed' | 'cancelled' | 'failed'
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    FOREIGN KEY (telegram_user_id) REFERENCES users(telegram_user_id)
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS stats (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


async def init_db() -> None:
    """Create tables / indexes if they don't exist. Safe to call on every startup."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def upsert_user(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> None:
    """Insert a new user or update last-active timestamp."""
    now = int(time.time())
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_user_id, username, first_name, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username       = excluded.username,
                first_name     = excluded.first_name,
                last_active_at = excluded.last_active_at
            """,
            (telegram_user_id, username, first_name, now, now),
        )
        await db.commit()


async def set_user_credentials(
    telegram_user_id: int,
    *,
    auth_method: str,
    email: str | None = None,
    password: str | None = None,
    cookies_json: str | None = None,
) -> None:
    """Persist a user's IVASMS credentials."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            UPDATE users SET
                ivasms_email        = ?,
                ivasms_password     = ?,
                ivasms_cookies_json = ?,
                auth_method         = ?
            WHERE telegram_user_id = ?
            """,
            (email, password, cookies_json, auth_method, telegram_user_id),
        )
        await db.commit()


async def get_user(telegram_user_id: int) -> dict[str, Any] | None:
    """Fetch a user row as a dict, or None if not found."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_user_credentials(telegram_user_id: int) -> None:
    """Wipe a user's stored IVASMS credentials."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            UPDATE users SET
                ivasms_email = NULL,
                ivasms_password = NULL,
                ivasms_cookies_json = NULL,
                auth_method = 'email'
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        )
        await db.commit()


async def increment_user_requests(telegram_user_id: int) -> None:
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "UPDATE users SET total_requests = total_requests + 1 WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

async def create_order(
    telegram_user_id: int,
    phone_range: str | None,
    phone_number: str | None,
) -> int:
    """Create a new order row and return its id."""
    now = int(time.time())
    async with aiosqlite.connect(settings.database_path) as db:
        cur = await db.execute(
            """
            INSERT INTO orders (telegram_user_id, phone_range, phone_number, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (telegram_user_id, phone_range, phone_number, now, now),
        )
        await db.commit()
        return cur.lastrowid or 0


async def update_order_otp(order_id: int, otp_message: str, status: str = "completed") -> None:
    now = int(time.time())
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "UPDATE orders SET otp_message = ?, status = ?, updated_at = ? WHERE id = ?",
            (otp_message, status, now, order_id),
        )
        await db.commit()


async def set_order_status(order_id: int, status: str) -> None:
    now = int(time.time())
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, order_id),
        )
        await db.commit()


async def get_order(order_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_orders(telegram_user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE telegram_user_id = ? ORDER BY created_at DESC LIMIT ?",
            (telegram_user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_orders_by_status(telegram_user_id: int, status: str) -> int:
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM orders WHERE telegram_user_id = ? AND status = ?",
            (telegram_user_id, status),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Stats (key/value)
# ---------------------------------------------------------------------------

async def stat_increment(key: str, amount: int = 1) -> None:
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            INSERT INTO stats (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT)
            """,
            (key, str(amount), amount),
        )
        await db.commit()


async def stat_get(key: str, default: str = "0") -> str:
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute("SELECT value FROM stats WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def stat_set(key: str, value: Any) -> None:
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "INSERT INTO stats (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await db.commit()


async def get_all_stats() -> dict[str, str]:
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute("SELECT key, value FROM stats") as cur:
            rows = await cur.fetchall()
            return {k: v for k, v in rows}
