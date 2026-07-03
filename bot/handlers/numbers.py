"""
"Get Number" flow:
    1. User taps 📱 Get Number on main menu
    2. Bot fetches SMS stats (which contains the list of phone ranges)
    3. User taps a range
    4. Bot fetches numbers in that range
    5. User taps a number → hands off to the OTP handler
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .. import database as db
from .. import keyboards as kb
from .. import messages as m
from ..ivasms import IvasmsError, IvasmsAuthError
from .common import (
    NumberFlow,
    get_client,
    rate_limited,
    require_account,
    safe_answer,
    safe_edit,
)

logger = logging.getLogger(__name__)
router = Router(name="numbers")


# Cache of numbers-per-user-per-range so pagination doesn't re-fetch every time.
# Keyed by (user_id, phone_range). Cleared on menu return.
_numbers_cache: dict[tuple[int, str], list] = {}


# ---------------------------------------------------------------------------
# Step 1: fetch ranges
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "get_number")
@require_account
@rate_limited
async def cb_get_number(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NumberFlow.picking_range)
    await safe_edit(call, m.loading_ranges_msg())
    await safe_answer(call)

    client = await get_client(call.from_user.id)
    if not client:
        await safe_edit(call, m.not_linked_msg(), reply_markup=kb.account_kb(False))
        return

    try:
        stats = await client.get_sms_stats()
    except IvasmsAuthError as e:
        await safe_edit(call, m.error_msg(f"Auth error: {e}"), reply_markup=kb.back_to_main_kb())
        return
    except IvasmsError as e:
        await safe_edit(call, m.error_msg(str(e)), reply_markup=kb.back_to_main_kb())
        return

    # Stash stats in FSM so we don't re-fetch when the user picks a range
    await state.update_data(ranges=[r.__dict__ if hasattr(r, "__dict__") else r for r in stats.ranges])
    await safe_edit(call, m.ranges_msg(stats), reply_markup=kb.ranges_kb(stats))


# ---------------------------------------------------------------------------
# Step 2: user picked a range → fetch numbers
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("range:"))
@rate_limited
async def cb_pick_range(call: CallbackQuery, state: FSMContext) -> None:
    phone_range = call.data.split(":", 1)[1]
    await state.update_data(current_range=phone_range)
    await state.set_state(NumberFlow.picking_number)
    await safe_edit(call, m.loading_numbers_msg(phone_range))
    await safe_answer(call)

    client = await get_client(call.from_user.id)
    if not client:
        await safe_edit(call, m.not_linked_msg(), reply_markup=kb.account_kb(False))
        return

    try:
        numbers = await client.get_numbers_in_range(phone_range)
    except IvasmsError as e:
        await safe_edit(call, m.error_msg(str(e)), reply_markup=kb.back_to_main_kb())
        return

    if not numbers:
        await safe_edit(call, m.no_numbers_msg(phone_range), reply_markup=kb.back_to_main_kb())
        return

    # Cache for pagination
    _numbers_cache[(call.from_user.id, phone_range)] = numbers
    await safe_edit(call, m.numbers_msg(phone_range, numbers), reply_markup=kb.numbers_kb(numbers, page=0))


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("npage:"))
async def cb_npage(call: CallbackQuery, state: FSMContext) -> None:
    page = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    phone_range = data.get("current_range", "")
    numbers = _numbers_cache.get((call.from_user.id, phone_range), [])
    if not numbers:
        await safe_edit(call, "⚠️ Cache expired. Tap 📱 Get Number to start over.", reply_markup=kb.back_to_main_kb())
        return
    await safe_edit(call, m.numbers_msg(phone_range, numbers), reply_markup=kb.numbers_kb(numbers, page=page))
    await safe_answer(call)


# ---------------------------------------------------------------------------
# Step 3: user picked a number → hand off to OTP handler
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("number:"))
async def cb_pick_number(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":", 2)
    if len(parts) < 3:
        await safe_answer(call, "Invalid number selection.")
        return
    phone_number = parts[1]
    # parts[2] is the internal id_number — not strictly needed; we use number+range
    data = await state.get_data()
    phone_range = data.get("current_range", "")

    # Hand off to OTP flow by faking a callback to the OTP router.
    # Simpler: import and call the start function directly.
    from .otp import start_otp_for_number
    await start_otp_for_number(call, phone_number, phone_range)
