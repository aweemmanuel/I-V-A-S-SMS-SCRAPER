"""
Shared handler utilities: FSM states, rate limiter, decorator that ensures
a user has linked their IVASMS account, and helper for building an
IvasmsClient from the current user.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from functools import wraps
from typing import Awaitable, Callable, Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, Update

from .. import database as db
from .. import messages as m
from .. import keyboards as kb
from ..config import settings
from ..ivasms import IvasmsClient, client_from_user


# ---------------------------------------------------------------------------
# FSM states for the account-setup wizard
# ---------------------------------------------------------------------------

class AuthFlow(StatesGroup):
    waiting_for_method = State()
    waiting_for_email = State()
    waiting_for_password = State()
    waiting_for_cookies = State()


class NumberFlow(StatesGroup):
    picking_range = State()
    picking_number = State()


class OtpFlow(StatesGroup):
    polling = State()


# ---------------------------------------------------------------------------
# Per-user cooldown (rate limiter)
# ---------------------------------------------------------------------------

_last_request_at: dict[int, float] = defaultdict(float)


def cooldown_remaining(user_id: int) -> int:
    """Return seconds left until the user can make another IVASMS request."""
    elapsed = time.time() - _last_request_at[user_id]
    remaining = settings.user_cooldown_seconds - elapsed
    return max(0, int(remaining))


def mark_request(user_id: int) -> None:
    _last_request_at[user_id] = time.time()


def rate_limited(handler: Callable[..., Awaitable[Any]]):
    """
    Decorator: enforces per-user cooldown. If too soon, send a friendly
    cooldown message instead of calling the handler.
    """

    @wraps(handler)
    async def wrapper(event, *args, **kwargs):  # noqa: ANN001
        # event can be CallbackQuery or Message
        user_id = _extract_user_id(event)
        remaining = cooldown_remaining(user_id)
        if remaining > 0:
            bot = _extract_bot(event)
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer(f"⏳ Wait {remaining}s", show_alert=False)
                await bot.send_message(user_id, m.cooldown_msg(remaining))
            except Exception:
                pass
            return
        mark_request(user_id)
        return await handler(event, *args, **kwargs)

    return wrapper


def _extract_user_id(event) -> int:
    if isinstance(event, CallbackQuery):
        return event.from_user.id
    if isinstance(event, Message):
        return event.from_user.id
    if isinstance(event, Update):
        return event.message.from_user.id if event.message else 0
    return 0


def _extract_bot(event) -> Bot:
    if isinstance(event, CallbackQuery):
        return event.bot or event.message.bot
    if isinstance(event, Message):
        return event.bot
    raise ValueError("Cannot extract bot from event")


# ---------------------------------------------------------------------------
# Decorator: require linked IVASMS account
# ---------------------------------------------------------------------------

def require_account(handler: Callable[..., Awaitable[Any]]):
    """
    Decorator: if the user has no IVASMS credentials linked, send them to
    the account-setup flow instead of running the handler.
    """

    @wraps(handler)
    async def wrapper(event, *args, **kwargs):  # noqa: ANN001
        user_id = _extract_user_id(event)
        user = await db.get_user(user_id)
        if not user or not _has_credentials(user):
            bot = _extract_bot(event)
            await bot.send_message(
                user_id,
                m.not_linked_msg(),
                reply_markup=kb.account_kb(has_credentials=False),
            )
            return
        return await handler(event, *args, **kwargs)

    return wrapper


def _has_credentials(user: dict) -> bool:
    method = (user.get("auth_method") or "email").lower()
    if method == "cookies":
        return bool(user.get("ivasms_cookies_json"))
    return bool(user.get("ivasms_email")) and bool(user.get("ivasms_password"))


async def get_client(user_id: int) -> IvasmsClient | None:
    """Build a fresh IvasmsClient for the user (or None if not linked)."""
    user = await db.get_user(user_id)
    if not user or not _has_credentials(user):
        return None
    return client_from_user(user)


# ---------------------------------------------------------------------------
# Convenience: refresh a callback's message
# ---------------------------------------------------------------------------

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None) -> None:
    """Edit a callback message; ignore 'message not modified' errors."""
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:  # noqa: BLE001
        # If edit fails (e.g. message too old), fall back to sending a new one.
        try:
            await call.message.answer(text, reply_markup=reply_markup)
        except Exception:
            pass


async def safe_answer(call: CallbackQuery, text: str = "", *, show_alert: bool = False) -> None:
    try:
        await call.answer(text, show_alert=show_alert)
    except Exception:
        pass
