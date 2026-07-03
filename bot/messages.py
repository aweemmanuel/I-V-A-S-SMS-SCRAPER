"""
Pretty-formatted HTML message templates for Telegram.

All messages use HTML parse_mode (aiogram default) and include:
  - emoji icons for visual scanning
  - <code> blocks for OTP codes and phone numbers (tap-to-copy on mobile)
  - clean section separators
"""
from __future__ import annotations

from datetime import datetime

from .ivasms import SmsStats, PhoneNumberInfo, OtpMessage, extract_otp


# ---------------------------------------------------------------------------
# Country flag helper — converts a phone range like "+1" or "+91" to flag(s)
# ---------------------------------------------------------------------------

_CC_TO_FLAG = {
    "1": "🇺🇸", "7": "🇷🇺", "20": "🇪🇬", "27": "🇿🇦", "30": "🇬🇷", "31": "🇳🇱",
    "33": "🇫🇷", "34": "🇪🇸", "39": "🇮🇹", "44": "🇬🇧", "49": "🇩🇪", "51": "🇵🇪",
    "52": "🇲🇽", "54": "🇦🇷", "55": "🇧🇷", "56": "🇨🇱", "60": "🇲🇾", "61": "🇦🇺",
    "62": "🇮🇩", "63": "🇵🇭", "65": "🇸🇬", "66": "🇹🇭", "81": "🇯🇵", "82": "🇰🇷",
    "84": "🇻🇳", "86": "🇨🇳", "90": "🇹🇷", "91": "🇮🇳", "92": "🇵🇰", "93": "🇦🇫",
    "94": "🇱🇰", "95": "🇲🇲", "98": "🇮🇷", "212": "🇲🇦", "234": "🇳🇬", "351": "🇵🇹",
    "352": "🇱🇺", "353": "🇮🇪", "354": "🇮🇸", "358": "🇫🇮", "359": "🇧🇬", "370": "🇱🇹",
    "371": "🇱🇻", "372": "🇪🇪", "374": "🇦🇲", "375": "🇧🇾", "380": "🇺🇦", "381": "🇷🇸",
    "385": "🇭🇷", "386": "🇸🇮", "420": "🇨🇿", "421": "🇸🇰", "880": "🇧🇩", "962": "🇯🇴",
    "963": "🇸🇾", "964": "🇮🇶", "965": "🇰🇼", "966": "🇸🇦", "971": "🇦🇪", "972": "🇮🇱",
    "977": "🇳🇵", "994": "🇦🇿", "995": "🇬🇪", "998": "🇺🇿",
}


def flag_for_range(phone_range: str) -> str:
    """Convert a phone range like '+1' or '+91' to a flag emoji (or 🔢 if unknown)."""
    digits = phone_range.lstrip("+").strip()
    # Try longest match first (3 → 2 → 1 digit)
    for length in (3, 2, 1):
        if digits[:length] in _CC_TO_FLAG:
            return _CC_TO_FLAG[digits[:length]]
    return "🔢"


# ---------------------------------------------------------------------------
# Welcome / main menu
# ---------------------------------------------------------------------------

def welcome_msg(first_name: str, has_credentials: bool) -> str:
    """Main menu welcome card."""
    status_line = (
        "🟢 <b>IVASMS account connected</b>" if has_credentials
        else "🔴 <b>No IVASMS account linked yet — tap 🔑 Account to add one</b>"
    )
    return (
        f"👋 <b>Welcome, {first_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>IVASMS OTP Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_line}\n\n"
        f"📋 <b>What I can do:</b>\n"
        f"📱 <b>Get Number</b> — fetch your rented phone numbers\n"
        f"💬 <b>Get OTP</b> — poll for the latest SMS / OTP code\n"
        f"❌ <b>Cancel</b> — stop an active polling session\n"
        f"📊 <b>Status</b> — show today's IVASMS statistics\n"
        f"🔑 <b>Account</b> — manage your IVASMS credentials\n"
        f"📜 <b>History</b> — view your recent OTP retrievals\n\n"
        f"Tap a button below to get started 👇"
    )


# ---------------------------------------------------------------------------
# Account / auth
# ---------------------------------------------------------------------------

def auth_method_msg() -> str:
    return (
        "🔑 <b>Link your IVASMS account</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Choose how you want to authenticate:\n\n"
        "📧 <b>Email + Password</b>\n"
        "Use your IVASMS.com login credentials.\n\n"
        "🍪 <b>Cookies JSON</b>\n"
        "Use exported browser cookies (works around 2FA / reCAPTCHA).\n\n"
        "Pick an option below 👇"
    )


def ask_email_msg() -> str:
    return (
        "📧 <b>Email setup</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send me your <b>IVASMS.com email address</b> as a plain message.\n\n"
        "💡 Your password will be asked next. Tap ❌ Cancel below to abort."
    )


def ask_password_msg(email: str) -> str:
    return (
        f"🔑 <b>Password for</b> <code>{email}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send me your <b>IVASMS.com password</b> as a plain message.\n\n"
        "🔒 The password is stored locally in the bot's SQLite DB and only used to "
        "log in to IVASMS — it is never logged or shared.\n\n"
        "💡 Tip: after sending, delete the message from your chat for extra safety.\n\n"
        "Tap ❌ Cancel to abort."
    )


def ask_cookies_msg() -> str:
    return (
        "🍪 <b>Cookies setup</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send me your <b>IVASMS cookies as JSON</b>.\n\n"
        "📝 <b>How to get cookies:</b>\n"
        "1. Log in to <code>ivasms.com</code> in Chrome/Firefox\n"
        "2. Install the <b>Cookie-Editor</b> extension\n"
        "3. Open it on ivasms.com → <b>Export → JSON</b>\n"
        "4. Paste the JSON here\n\n"
        "Tap ❌ Cancel to abort."
    )


def auth_success_msg(method: str) -> str:
    icon = "📧" if method == "email" else "🍪"
    return (
        f"✅ <b>IVASMS account linked!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon} Auth method: <code>{method}</code>\n"
        f"🟢 Connection verified — you can now fetch numbers and OTPs.\n\n"
        f"Tap 📱 Get Number on the main menu to start."
    )


def auth_failed_msg(reason: str) -> str:
    return (
        f"❌ <b>Authentication failed</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{reason}</code>\n\n"
        f"💡 <b>Common fixes:</b>\n"
        f"• Double-check email / password spelling\n"
        f"• If IVASMS shows a reCAPTCHA on login, use 🍪 cookies auth instead\n"
        f"• Make sure your cookies haven't expired\n\n"
        f"Tap 🔑 Account to try again."
    )


def account_info_msg(user: dict) -> str:
    method = (user.get("auth_method") or "email").lower()
    icon = "📧" if method == "email" else "🍪"
    if method == "email":
        cred = user.get("ivasms_email") or "<i>not set</i>"
        cred_line = f"📧 Email: <code>{cred}</code>"
    else:
        has = bool(user.get("ivasms_cookies_json"))
        cred_line = f"🍪 Cookies: {'✅ set' if has else '❌ not set'}"

    return (
        f"🔑 <b>Your IVASMS Account</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Telegram ID: <code>{user['telegram_user_id']}</code>\n"
        f"{cred_line}\n"
        f"🔐 Method: <code>{method}</code>\n"
        f"📊 Total requests: <code>{user.get('total_requests', 0)}</code>\n"
        f"📅 Joined: <code>{datetime.fromtimestamp(user.get('created_at', 0)).strftime('%Y-%m-%d %H:%M')}</code>\n\n"
        f"What would you like to do?"
    )


def credentials_removed_msg() -> str:
    return (
        "🗑️ <b>Credentials removed</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Your IVASMS email/password/cookies have been wiped from this bot.\n"
        "Tap 🔑 Account to add them again."
    )


# ---------------------------------------------------------------------------
# Number fetching
# ---------------------------------------------------------------------------

def loading_ranges_msg() -> str:
    return "⏳ <b>Fetching your phone ranges from IVASMS...</b>\nThis usually takes 2-4 seconds."


def ranges_msg(stats: SmsStats) -> str:
    lines = [
        "📱 <b>Your Phone Ranges (today)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total SMS: <b>{stats.count_sms}</b>  |  💰 Paid: <b>{stats.paid_sms}</b>  |  ⚠️ Unpaid: <b>{stats.unpaid_sms}</b>",
        f"💵 Revenue: <code>${stats.revenue}</code>",
        "",
        "<b>Pick a range to view its numbers:</b>",
    ]
    if stats.ranges:
        for r in stats.ranges:
            flag = flag_for_range(r["country_number"])
            lines.append(f"{flag} <code>{r['country_number']}</code> — {r['count']} SMS, ${r['revenue']}")
    else:
        lines.append("<i>No SMS received today on any of your ranges.</i>")
    return "\n".join(lines)


def loading_numbers_msg(phone_range: str) -> str:
    flag = flag_for_range(phone_range)
    return f"⏳ <b>Fetching numbers for {flag} <code>{phone_range}</code>...</b>"


def numbers_msg(phone_range: str, numbers: list[PhoneNumberInfo]) -> str:
    flag = flag_for_range(phone_range)
    lines = [
        f"📱 <b>Numbers in {flag} <code>{phone_range}</code></b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Found <b>{len(numbers)}</b> number(s) that received SMS today.\n",
        "<b>Tap a number to fetch its latest OTP:</b>",
    ]
    return "\n".join(lines)


def no_numbers_msg(phone_range: str) -> str:
    flag = flag_for_range(phone_range)
    return (
        f"📭 <b>No SMS yet for {flag} <code>{phone_range}</code></b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"No phone numbers in this range have received an SMS today.\n"
        f"🔄 Try again later, or pick a different range."
    )


# ---------------------------------------------------------------------------
# OTP fetching + polling
# ---------------------------------------------------------------------------

def otp_loading_msg(phone_number: str) -> str:
    return (
        f"💬 <b>Fetching latest OTP for</b> <code>{phone_number}</code>\n"
        f"⏳ Polling IVASMS..."
    )


def otp_not_yet_msg(phone_number: str) -> str:
    return (
        f"⏳ <b>No SMS yet for</b> <code>{phone_number}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Auto-polling started — I'll notify you the moment an SMS arrives.\n"
        f"⏱️ Polling for the next 5 minutes (every 10s)."
    )


def otp_received_msg(otp: OtpMessage) -> str:
    code = extract_otp(otp.message) or "(could not auto-extract)"
    flag = flag_for_range(otp.range)
    return (
        f"✅ <b>OTP Received!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 <b>Code:</b> <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{flag} <b>Range:</b> <code>{otp.range}</code>\n"
        f"📱 <b>Number:</b> <code>{otp.phone_number}</code>\n"
        f"⏰ <b>Received:</b> <code>{otp.fetched_at}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📨 <b>Full message:</b>\n<code>{otp.message}</code>\n\n"
        f"💡 Tap the code to copy it."
    )


def otp_poll_stopped_msg(reason: str = "stopped by user") -> str:
    return (
        f"⏹️ <b>Polling stopped</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Reason: <code>{reason}</code>\n"
        f"Tap 💬 Get OTP on the main menu to start a new session."
    )


def otp_poll_timeout_msg(phone_number: str) -> str:
    return (
        f"⏱️ <b>Polling timed out</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"No SMS arrived for <code>{phone_number}</code> within the polling window.\n"
        f"Tap 💬 Get OTP to try again."
    )


# ---------------------------------------------------------------------------
# Status panel
# ---------------------------------------------------------------------------

def status_msg(stats: SmsStats | None, user_counts: dict[str, int]) -> str:
    if stats:
        stats_block = (
            f"📊 <b>IVASMS Today</b>\n"
            f"  Total SMS: <code>{stats.count_sms}</code>\n"
            f"  Paid: <code>{stats.paid_sms}</code>  |  Unpaid: <code>{stats.unpaid_sms}</code>\n"
            f"  Revenue: <code>${stats.revenue}</code>\n"
            f"  Active ranges: <code>{len(stats.ranges)}</code>\n"
        )
    else:
        stats_block = "📊 <b>IVASMS Today</b>: <i>unavailable (could not fetch)</i>\n"

    return (
        f"📊 <b>Bot Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{stats_block}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📜 <b>Your activity</b>\n"
        f"  ✅ Completed: <code>{user_counts.get('completed', 0)}</code>\n"
        f"  ⏳ Active: <code>{user_counts.get('active', 0)}</code>\n"
        f"  ❌ Cancelled: <code>{user_counts.get('cancelled', 0)}</code>\n"
        f"  ⚠️ Failed: <code>{user_counts.get('failed', 0)}</code>\n"
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def history_msg(orders: list[dict]) -> str:
    if not orders:
        return (
            "📜 <b>History</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No OTP retrievals yet. Tap 📱 Get Number to start.</i>"
        )
    lines = [
        "📜 <b>Recent OTP Retrievals</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for o in orders[:10]:
        ts = datetime.fromtimestamp(o.get("created_at", 0)).strftime("%Y-%m-%d %H:%M")
        status_icon = {
            "completed": "✅",
            "active": "⏳",
            "cancelled": "❌",
            "failed": "⚠️",
        }.get(o.get("status"), "•")
        otp_preview = (o.get("otp_message") or "")[:80]
        if otp_preview:
            otp_preview = otp_preview.replace("\n", " ")
        lines.append(
            f"{status_icon} <code>{ts}</code> | <code>{o.get('phone_number', '?')}</code>\n"
            f"   {otp_preview or '<i>no SMS</i>'}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cancel / errors
# ---------------------------------------------------------------------------

def nothing_to_cancel_msg() -> str:
    return (
        "ℹ️ <b>Nothing to cancel</b>\n"
        "You have no active OTP polling session right now."
    )


def cancelled_msg() -> str:
    return "✅ Active polling session cancelled."


def error_msg(reason: str) -> str:
    return (
        f"⚠️ <b>Error</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{reason}</code>\n\n"
        f"If this keeps happening, tap 🔑 Account → 🧪 Test Connection."
    )


def not_linked_msg() -> str:
    return (
        "🔑 <b>No IVASMS account linked</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "You need to link your IVASMS account first.\n\n"
        "Tap the button below to set it up."
    )


def cooldown_msg(seconds_left: int) -> str:
    return (
        f"⏳ <b>Slow down!</b>\n"
        f"Please wait <code>{seconds_left}s</code> before your next request.\n"
        f"This protects your IVASMS account from rate-limit bans."
    )


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

def cancelled_input_msg() -> str:
    return "❌ Input cancelled. Back to main menu."


def unknown_action_msg() -> str:
    return "🤔 Unknown action. Returning to main menu."
