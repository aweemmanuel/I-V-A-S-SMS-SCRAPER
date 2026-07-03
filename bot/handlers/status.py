"""
📊 Status and 📜 History handlers.

Status shows the user's IVASMS dashboard summary for today + their
order counters. History shows the 10 most recent OTP retrievals.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .. import database as db
from .. import keyboards as kb
from .. import messages as m
from ..ivasms import IvasmsError
from ..otp_poller import active_session_count
from .common import (
    get_client,
    rate_limited,
    require_account,
    safe_answer,
    safe_edit,
)

logger = logging.getLogger(__name__)
router = Router(name="status")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "status")
@require_account
@rate_limited
async def cb_status(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(call, "⏳ <b>Fetching IVASMS stats...</b>")
    await safe_answer(call)

    client = await get_client(call.from_user.id)
    stats = None
    if client:
        try:
            stats = await client.get_sms_stats()
        except IvasmsError as e:
            logger.warning("Status fetch failed for user %s: %s", call.from_user.id, e)

    user_counts = {
        "completed": await db.count_orders_by_status(call.from_user.id, "completed"),
        "active": await db.count_orders_by_status(call.from_user.id, "active"),
        "cancelled": await db.count_orders_by_status(call.from_user.id, "cancelled"),
        "failed": await db.count_orders_by_status(call.from_user.id, "failed"),
    }

    # Also include global active polling count as a bonus line
    extra = f"\n🌐 <b>Bot-wide active polls:</b> <code>{active_session_count()}</code>\n"

    await safe_edit(
        call,
        m.status_msg(stats, user_counts) + extra,
        reply_markup=kb.back_to_main_kb(),
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "history")
async def cb_history(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    orders = await db.get_user_orders(call.from_user.id, limit=10)
    await safe_edit(call, m.history_msg(orders), reply_markup=kb.back_to_main_kb())
    await safe_answer(call)
