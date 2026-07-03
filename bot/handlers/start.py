"""
/start handler + main menu + account-setup wizard.

This is the entry point. Every interaction is driven by inline buttons
(callback queries), not slash commands (apart from the initial /start).
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, Document

from .. import database as db
from .. import ivasms
from .. import keyboards as kb
from .. import messages as m
from ..config import settings, is_admin
from .common import (
    AuthFlow,
    get_client,
    safe_answer,
    safe_edit,
)

logger = logging.getLogger(__name__)
router = Router(name="start")


# ---------------------------------------------------------------------------
# /start — entry point
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    await db.upsert_user(
        telegram_user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    user = await db.get_user(user_id)
    has_creds = bool(user and (user.get("ivasms_email") or user.get("ivasms_cookies_json")))
    await message.answer(
        m.welcome_msg(message.from_user.first_name or "there", has_creds),
        reply_markup=kb.main_menu_kb(),
    )


# ---------------------------------------------------------------------------
# "main" callback — return to main menu (clears FSM state)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(call.from_user.id)
    has_creds = bool(user and (user.get("ivasms_email") or user.get("ivasms_cookies_json")))
    await safe_edit(
        call,
        m.welcome_msg(call.from_user.first_name or "there", has_creds),
        reply_markup=kb.main_menu_kb(),
    )
    await safe_answer(call)


# ---------------------------------------------------------------------------
# "noop" callback — for disabled buttons
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await safe_answer(call)


# ---------------------------------------------------------------------------
# Account menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "account")
async def cb_account(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(call.from_user.id)
    if not user:
        # Shouldn't happen — but be defensive
        await db.upsert_user(
            telegram_user_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name,
        )
        user = await db.get_user(call.from_user.id)

    has_creds = bool(user.get("ivasms_email") or user.get("ivasms_cookies_json"))
    await safe_edit(call, m.account_info_msg(user), reply_markup=kb.account_kb(has_creds))
    await safe_answer(call)


# ---------------------------------------------------------------------------
# Auth wizard — pick method
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("auth:"))
async def cb_auth(call: CallbackQuery, state: FSMContext) -> None:
    action = call.data.split(":", 1)[1]

    if action in ("new", "reconnect"):
        await state.set_state(AuthFlow.waiting_for_method)
        await safe_edit(call, m.auth_method_msg(), reply_markup=kb.auth_method_kb())
        await safe_answer(call)
        return

    if action == "email":
        # Only valid while picking auth method
        await state.set_state(AuthFlow.waiting_for_email)
        await safe_edit(call, m.ask_email_msg(), reply_markup=kb.cancel_kb())
        await safe_answer(call)
        return

    if action == "cookies":
        await state.set_state(AuthFlow.waiting_for_cookies)
        await safe_edit(call, m.ask_cookies_msg(), reply_markup=kb.cancel_kb())
        await safe_answer(call)
        return

    if action == "remove":
        await db.delete_user_credentials(call.from_user.id)
        await safe_edit(
            call,
            m.credentials_removed_msg(),
            reply_markup=kb.account_kb(has_credentials=False),
        )
        await safe_answer(call)
        return

    if action == "test":
        await _test_connection(call)
        return

    # Unknown auth action — bounce back to account menu
    await cb_account(call, state)


# ---------------------------------------------------------------------------
# Email input
# ---------------------------------------------------------------------------

@router.message(AuthFlow.waiting_for_email)
async def on_email(message: Message, state: FSMContext) -> None:
    # Strip invisible Unicode chars (Telegram loves to inject U+200B, U+00A0, tabs)
    _INVISIBLE = "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u00a0"
    email = (message.text or "").translate({ord(c): "" for c in _INVISIBLE}).strip()
    if "@" not in email or "." not in email:
        await message.answer(
            "⚠️ That doesn't look like a valid email. Try again, or tap ❌ Cancel.",
            reply_markup=kb.cancel_kb(),
        )
        return
    await state.update_data(email=email)
    await state.set_state(AuthFlow.waiting_for_password)
    await message.answer(m.ask_password_msg(email), reply_markup=kb.cancel_kb())
    # Hide the user's email from the chat history (best-effort)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(AuthFlow.waiting_for_password)
async def on_password(message: Message, state: FSMContext) -> None:
    _INVISIBLE = "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u00a0"
    password = (message.text or "").translate({ord(c): "" for c in _INVISIBLE}).strip()
    if not password:
        await message.answer(
            "⚠️ Password can't be empty. Try again, or tap ❌ Cancel.",
            reply_markup=kb.cancel_kb(),
        )
        return
    data = await state.get_data()
    email = data.get("email", "")
    await state.clear()

    # Save credentials first
    await db.set_user_credentials(
        message.from_user.id,
        auth_method="email",
        email=email,
        password=password,
    )

    # Try logging in
    status_msg = await message.answer("⏳ <b>Testing IVASMS login...</b>")
    client = ivasms.client_from_user(await db.get_user(message.from_user.id))
    ok, reason = await client.test_auth()

    # Hide the password message immediately
    try:
        await message.delete()
    except Exception:
        pass

    if ok:
        await status_msg.edit_text(
            m.auth_success_msg("email"),
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await status_msg.edit_text(
            m.auth_failed_msg(reason),
            reply_markup=kb.account_kb(has_credentials=True),
        )


# ---------------------------------------------------------------------------
# Cookies input
# ---------------------------------------------------------------------------

@router.message(AuthFlow.waiting_for_cookies)
async def on_cookies(message: Message, state: FSMContext) -> None:
    # Telegram often injects zero-width spaces (U+200B, U+200E, U+200F),
    # non-breaking spaces (U+00A0), and tabs at the start of pasted text.
    # Strip ALL Unicode whitespace + invisible chars, not just ASCII spaces.
    raw = message.text or ""
    # Remove zero-width and bidi control chars that Telegram loves to insert
    _INVISIBLE = "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u00a0"
    raw = raw.translate({ord(c): "" for c in _INVISIBLE})
    raw = raw.strip()
    # Also strip Markdown code fences if user wrapped the JSON in ```
    if raw.startswith("```"):
        raw = raw.strip("`").strip()

    # Validate by actually trying to parse JSON (more robust than prefix check)
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        await message.answer(
            "⚠️ <b>That isn't valid JSON.</b>\n"
            f"<code>{e}</code>\n\n"
            "💡 <b>Tip:</b> If Telegram mangled your paste, try this instead:\n"
            "1. Open a plain text editor (Notepad / TextEdit)\n"
            "2. Paste the cookies there\n"
            "3. Select All → Copy\n"
            "4. Paste here\n\n"
            "Or send the JSON as a <b>file attachment</b> (paperclip → Document).",
            reply_markup=kb.cancel_kb(),
        )
        return

    # Re-serialize compactly so we don't store Telegram's whitespace noise
    raw = _json.dumps(parsed)

    await state.clear()
    await db.set_user_credentials(
        message.from_user.id,
        auth_method="cookies",
        cookies_json=raw,
    )

    status_msg = await message.answer("⏳ <b>Testing IVASMS cookies...</b>")
    try:
        await message.delete()  # hide the cookies payload from chat
    except Exception:
        pass

    client = ivasms.client_from_user(await db.get_user(message.from_user.id))
    ok, reason = await client.test_auth()
    if ok:
        await status_msg.edit_text(
            m.auth_success_msg("cookies"),
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await status_msg.edit_text(
            m.auth_failed_msg(reason),
            reply_markup=kb.account_kb(has_credentials=True),
        )


# ---------------------------------------------------------------------------
# Cancel input (during wizard)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cancel_input")
async def cb_cancel_input(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb_main(call, state)


# ---------------------------------------------------------------------------
# Test connection (from account menu)
# ---------------------------------------------------------------------------

async def _test_connection(call: CallbackQuery) -> None:
    await safe_edit(call, "⏳ <b>Testing IVASMS connection...</b>")
    client = await get_client(call.from_user.id)
    if not client:
        await safe_edit(
            call,
            m.not_linked_msg(),
            reply_markup=kb.account_kb(has_credentials=False),
        )
        return
    ok, reason = await client.test_auth()
    user = await db.get_user(call.from_user.id)
    if ok:
        await safe_edit(
            call,
            "✅ <b>Connection OK!</b>\n" + m.account_info_msg(user),
            reply_markup=kb.account_kb(has_credentials=True),
        )
    else:
        await safe_edit(
            call,
            m.auth_failed_msg(reason),
            reply_markup=kb.account_kb(has_credentials=True),
        )
    await safe_answer(call)
