"""
"Get OTP" flow:

  Path A — from main menu, no number picked yet:
    1. User taps 💬 Get OTP
    2. If a polling session is already active → show its status
    3. Otherwise → bounce to 📱 Get Number to pick a number first

  Path B — from number picker:
    cb_pick_number() in numbers.py calls start_otp_for_number()
    1. Start a background poll task
    2. Push OTP to chat the moment it arrives
    3. User can stop early or let it time out
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .. import keyboards as kb
from .. import messages as m
from ..ivasms import IvasmsError
from ..otp_poller import (
    get_active_session,
    has_active_session,
    start_poll,
    stop_poll,
    check_once,
)
from .common import (
    OtpFlow,
    get_client,
    rate_limited,
    require_account,
    safe_answer,
    safe_edit,
)

logger = logging.getLogger(__name__)
router = Router(name="otp")


# ---------------------------------------------------------------------------
# Entry from main menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "get_otp")
@require_account
async def cb_get_otp(call: CallbackQuery, state: FSMContext) -> None:
    """If a poll is active, show its status; otherwise bounce to Get Number."""
    session = get_active_session(call.from_user.id)
    if session:
        await safe_edit(
            call,
            (
                f"⏳ <b>Already polling for OTP</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📱 Number: <code>{session.phone_number}</code>\n"
                f"🌍 Range: <code>{session.phone_range}</code>\n"
                f"🔄 Auto-checking every {call.bot and '10s' or '10s'}...\n\n"
                f"You'll be notified here the moment an SMS arrives."
            ),
            reply_markup=kb.otp_poll_kb(active=True),
        )
        await safe_answer(call)
        return

    # No active session → redirect to Get Number
    await safe_edit(
        call,
        "💬 <b>Get OTP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Pick a phone number first — I'll start auto-polling it for new SMS.",
        reply_markup=kb.InlineKeyboardMarkup(
            inline_keyboard=[
                [kb.InlineKeyboardButton(text="📱 Pick a Number", callback_data="get_number")],
                [kb.InlineKeyboardButton(text="⬅️ Main Menu", callback_data="main")],
            ]
        ),
    )
    await safe_answer(call)


# ---------------------------------------------------------------------------
# Start polling for a specific number (called from numbers.py)
# ---------------------------------------------------------------------------

@rate_limited
async def start_otp_for_number(call: CallbackQuery, phone_number: str, phone_range: str) -> None:
    """Kick off an auto-poll session for a specific number.

    Called directly from numbers.py — not a handler itself.
    """
    client = await get_client(call.from_user.id)
    if not client:
        await safe_edit(call, m.not_linked_msg(), reply_markup=kb.account_kb(False))
        return

    await safe_edit(call, m.otp_loading_msg(phone_number))
    await safe_answer(call)

    # Start the background poller
    session = await start_poll(
        bot=call.bot,
        user_id=call.from_user.id,
        phone_number=phone_number,
        phone_range=phone_range,
        client=client,
    )

    # If no SMS was delivered immediately (i.e. session.last_seen_message is None),
    # show the "polling started" message.
    if session.last_seen_message is None:
        await safe_edit(
            call,
            m.otp_not_yet_msg(phone_number),
            reply_markup=kb.otp_poll_kb(active=True),
        )


# ---------------------------------------------------------------------------
# Manual "Check Now" button
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "otp_check_now")
@rate_limited
async def cb_otp_check_now(call: CallbackQuery) -> None:
    found = await check_once(call.from_user.id)
    if not found:
        session = get_active_session(call.from_user.id)
        if session:
            await safe_answer(call, "⏳ Still no new SMS — keep waiting.")
        else:
            await safe_answer(call, "No active polling session.")
    else:
        await safe_answer(call, "🆕 New SMS delivered above ↑")


# ---------------------------------------------------------------------------
# Stop polling
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "otp_stop")
async def cb_otp_stop(call: CallbackQuery) -> None:
    stopped = await stop_poll(call.from_user.id)
    if stopped:
        await safe_edit(
            call,
            m.otp_poll_stopped_msg("stopped by user"),
            reply_markup=kb.back_to_main_kb(),
        )
    else:
        await safe_edit(
            call,
            m.nothing_to_cancel_msg(),
            reply_markup=kb.back_to_main_kb(),
        )
    await safe_answer(call)


# ---------------------------------------------------------------------------
# Cancel button (main menu) — alias for stop_poll
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery) -> None:
    stopped = await stop_poll(call.from_user.id)
    if stopped:
        await safe_edit(call, m.cancelled_msg(), reply_markup=kb.back_to_main_kb())
    else:
        await safe_edit(call, m.nothing_to_cancel_msg(), reply_markup=kb.back_to_main_kb())
    await safe_answer(call)
