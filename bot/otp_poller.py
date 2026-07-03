"""
Background OTP auto-poll.

When a user starts "Get OTP" on a phone number, we spawn an asyncio task
that polls IVASMS every N seconds for M minutes. The moment a new SMS
arrives, we push it to the user's chat and stop polling.

Active polls are tracked in-memory (one per user). The user can stop early
via the ⏹️ Stop button.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from .config import settings
from .database import create_order, update_order_otp, set_order_status
from .ivasms import IvasmsClient, OtpMessage, extract_otp
from . import messages as m
from . import keyboards as kb

logger = logging.getLogger(__name__)


@dataclass
class PollSession:
    """Tracks one user's active polling session."""

    user_id: int
    phone_number: str
    phone_range: str
    client: IvasmsClient
    bot: Bot
    task: asyncio.Task | None = None
    order_id: int = 0
    last_seen_message: str | None = None
    started_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def __post_init__(self) -> None:
        if not self.order_id:
            # We need to await create_order, but dataclass init is sync —
            # so we set order_id later from start_poll().
            pass


# In-memory registry: user_id -> PollSession
_active_sessions: dict[int, PollSession] = {}


def get_active_session(user_id: int) -> PollSession | None:
    return _active_sessions.get(user_id)


def has_active_session(user_id: int) -> bool:
    return user_id in _active_sessions and _active_sessions[user_id].task is not None


async def start_poll(
    *,
    bot: Bot,
    user_id: int,
    phone_number: str,
    phone_range: str,
    client: IvasmsClient,
    notify_message_id: int | None = None,
) -> PollSession:
    """
    Start polling IVASMS for new SMS on `phone_number`.

    A new PollSession is registered. If the user already has one, it is
    cancelled first (one active poll per user).
    """
    # Cancel any existing session
    await stop_poll(user_id, reason="replaced by new request")

    order_id = await create_order(user_id, phone_range=phone_range, phone_number=phone_number)

    session = PollSession(
        user_id=user_id,
        phone_number=phone_number,
        phone_range=phone_range,
        client=client,
        bot=bot,
        order_id=order_id,
    )

    # Try to fetch the latest existing SMS once at startup —
    # if there's one already, deliver it immediately and keep polling for *new* ones.
    try:
        existing = await client.get_otp_message(phone_number, phone_range)
        if existing and existing.message:
            session.last_seen_message = existing.message
            await _deliver_otp(session, existing, is_new=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("Initial OTP fetch for %s failed: %s", phone_number, e)

    session.task = asyncio.create_task(_poll_loop(session))
    _active_sessions[user_id] = session
    return session


async def _poll_loop(session: PollSession) -> None:
    """The actual polling loop. Runs until timeout, success, or cancellation."""
    interval = settings.otp_poll_interval_seconds
    timeout = settings.otp_poll_timeout_seconds
    elapsed = 0

    try:
        while elapsed < timeout:
            try:
                otp = await session.client.get_otp_message(
                    session.phone_number, session.phone_range
                )
                if otp and otp.message and otp.message != session.last_seen_message:
                    session.last_seen_message = otp.message
                    await _deliver_otp(session, otp, is_new=True)
                    # Don't return — keep polling in case more SMS arrive.
            except Exception as e:  # noqa: BLE001
                logger.warning("Poll error for %s: %s", session.phone_number, e)

            await asyncio.sleep(interval)
            elapsed += interval

        # Timeout
        await _end_session(session, status="cancelled", reason="timeout")
        try:
            await session.bot.send_message(
                session.user_id,
                m.otp_poll_timeout_msg(session.phone_number),
                reply_markup=kb.back_to_main_kb(),
            )
        except Exception:
            pass

    except asyncio.CancelledError:
        await _end_session(session, status="cancelled", reason="cancelled by user")
        raise


async def _deliver_otp(session: PollSession, otp: OtpMessage, *, is_new: bool) -> None:
    """Push the OTP message to the user's chat and update the DB row."""
    try:
        await update_order_otp(session.order_id, otp.message, status="completed")
    except Exception:
        pass

    text = ("🆕 <b>New SMS arrived!</b>\n" if is_new else "") + m.otp_received_msg(otp)
    try:
        await session.bot.send_message(
            session.user_id,
            text,
            reply_markup=kb.otp_poll_kb(active=True),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to deliver OTP to user %s: %s", session.user_id, e)


async def _end_session(session: PollSession, *, status: str, reason: str) -> None:
    """Mark the order row and remove the session from the registry."""
    try:
        await set_order_status(session.order_id, status)
    except Exception:
        pass
    _active_sessions.pop(session.user_id, None)


async def stop_poll(user_id: int, *, reason: str = "stopped by user") -> bool:
    """Cancel a user's active polling session. Returns True if one was running."""
    session = _active_sessions.get(user_id)
    if not session or not session.task:
        _active_sessions.pop(user_id, None)
        return False

    session.task.cancel()
    try:
        await session.task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass

    await _end_session(session, status="cancelled", reason=reason)
    return True


async def check_once(user_id: int) -> bool:
    """Trigger an immediate poll check (used by the '🔄 Check Now' button)."""
    session = _active_sessions.get(user_id)
    if not session:
        return False
    try:
        otp = await session.client.get_otp_message(session.phone_number, session.phone_range)
        if otp and otp.message and otp.message != session.last_seen_message:
            session.last_seen_message = otp.message
            await _deliver_otp(session, otp, is_new=True)
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Manual check error for %s: %s", session.phone_number, e)
    return False


def active_session_count() -> int:
    return len(_active_sessions)
