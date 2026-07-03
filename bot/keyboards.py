"""
Inline keyboard builders.

The main menu is a 2-column grid (matches the "EMMY IVASMS BOT" screenshot style):
    [📱 Get Number] [💬 Get OTP]
    [❌ Cancel]     [📊 Status]
    [🔑 Account]    [📜 History]

All buttons are inline (callback) buttons — no slash commands required
beyond the initial /start.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from .ivasms import SmsStats, PhoneNumberInfo


# ---------------------------------------------------------------------------
# Callback-data helpers (kept short — Telegram limits cb_data to 64 bytes)
# ---------------------------------------------------------------------------

def cb(*parts: str) -> str:
    """Join callback-data parts with ':'."""
    return ":".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# Main menu — the 2-column grid
# ---------------------------------------------------------------------------

def main_menu_kb() -> InlineKeyboardMarkup:
    """
    2-column grid main menu.

    Layout (matches EMMY IVASMS BOT screenshot):
        Row 1: 📱 Get Number  |  💬 Get OTP
        Row 2: ❌ Cancel       |  📊 Status
        Row 3: 🔑 Account      |  📜 History
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Get Number", callback_data=cb("get_number")),
                InlineKeyboardButton(text="💬 Get OTP", callback_data=cb("get_otp")),
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data=cb("cancel")),
                InlineKeyboardButton(text="📊 Status", callback_data=cb("status")),
            ],
            [
                InlineKeyboardButton(text="🔑 Account", callback_data=cb("account")),
                InlineKeyboardButton(text="📜 History", callback_data=cb("history")),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Account setup
# ---------------------------------------------------------------------------

def auth_method_kb() -> InlineKeyboardMarkup:
    """Pick whether to use email/password or cookies JSON for IVASMS auth."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📧 Email + Password", callback_data=cb("auth", "email"))],
            [InlineKeyboardButton(text="🍪 Cookies JSON", callback_data=cb("auth", "cookies"))],
            [InlineKeyboardButton(text="⬅️ Back", callback_data=cb("main"))],
        ]
    )


def account_kb(has_credentials: bool) -> InlineKeyboardMarkup:
    """Account management menu."""
    buttons = []
    if has_credentials:
        buttons.append([InlineKeyboardButton(text="🔄 Reconnect", callback_data=cb("auth", "reconnect"))])
        buttons.append([InlineKeyboardButton(text="🧪 Test Connection", callback_data=cb("auth", "test"))])
        buttons.append([InlineKeyboardButton(text="🗑️ Remove Credentials", callback_data=cb("auth", "remove"))])
    else:
        buttons.append([InlineKeyboardButton(text="➕ Add IVASMS Account", callback_data=cb("auth", "new"))])
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Menu", callback_data=cb("main"))])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data=cb("cancel_input"))]]
    )


# ---------------------------------------------------------------------------
# Number / range pickers
# ---------------------------------------------------------------------------

def ranges_kb(stats: SmsStats) -> InlineKeyboardMarkup:
    """Paginated list of phone ranges (countries) returned by get_sms_stats."""
    rows: list[list[InlineKeyboardButton]] = []
    for r in stats.ranges:
        label = f"{r['country_number']}  ({r['count']} SMS)"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=cb("range", r["country_number"]))]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="(no ranges found for today)", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=cb("get_number"))])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=cb("main"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def numbers_kb(numbers: list[PhoneNumberInfo], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Paginated list of phone numbers in a range, each with a 'Get OTP' button."""
    rows: list[list[InlineKeyboardButton]] = []
    start = page * per_page
    end = start + per_page
    page_numbers = numbers[start:end]

    for n in page_numbers:
        label = f"{n.phone_number}  ({n.count} SMS)"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=cb("number", n.phone_number, n.id_number or "0"))]
        )

    if not page_numbers:
        rows.append([InlineKeyboardButton(text="(no numbers in this range)", callback_data="noop")])

    # Pagination controls
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=cb("npage", str(page - 1))))
    if end < len(numbers):
        nav.append(InlineKeyboardButton(text="➡️ Next", callback_data=cb("npage", str(page + 1))))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="⬅️ Back to Ranges", callback_data=cb("get_number"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# OTP polling controls
# ---------------------------------------------------------------------------

def otp_poll_kb(active: bool = True) -> InlineKeyboardMarkup:
    """Controls shown alongside an active OTP poll."""
    if active:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Check Now", callback_data=cb("otp_check_now"))],
                [InlineKeyboardButton(text="⏹️ Stop Polling", callback_data=cb("otp_stop"))],
                [InlineKeyboardButton(text="⬅️ Main Menu", callback_data=cb("main"))],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Start Polling", callback_data=cb("otp_start"))],
            [InlineKeyboardButton(text="⬅️ Main Menu", callback_data=cb("main"))],
        ]
    )


# ---------------------------------------------------------------------------
# Generic back button
# ---------------------------------------------------------------------------

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Main Menu", callback_data=cb("main"))]]
    )


def confirm_kb(yes_cb: str, no_cb: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=yes_cb),
                InlineKeyboardButton(text="❌ Cancel", callback_data=no_cb),
            ]
        ]
    )
