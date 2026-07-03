"""
IVASMS.com async client.

IVASMS.com has no public API — every reference implementation uses web scraping.
This module wraps that scraping logic in an async-friendly interface and supports
both authentication methods observed in the reference repos:

  1. email + password  (used by 4 of 5 reference repos)
  2. cookies JSON      (used by Arslan-MD/IvaSms-api)

Discovered IVASMS endpoints (Laravel app, CSRF-protected):

  GET  /portal/sms/received                      — landing page (extract CSRF token)
  POST /portal/sms/received/getsms               — SMS statistics by date range
  POST /portal/sms/received/getsms/number        — phone numbers in a range
  POST /portal/sms/received/getsms/number/sms    — actual OTP message text for a number

All HTTP calls are executed in a thread executor so the aiogram event loop
is never blocked.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import cloudscraper
from bs4 import BeautifulSoup

from .config import settings


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SmsStats:
    count_sms: str
    paid_sms: str
    unpaid_sms: str
    revenue: str
    ranges: list[dict[str, str]]  # one entry per phone range (country)


@dataclass
class PhoneNumberInfo:
    phone_number: str
    count: str
    paid: str
    unpaid: str
    revenue: str
    id_number: str  # internal IVASMS id used to fetch the SMS body


@dataclass
class OtpMessage:
    range: str
    phone_number: str
    message: str
    fetched_at: str


class IvasmsError(Exception):
    """Base error for IVASMS client failures."""


class IvasmsAuthError(IvasmsError):
    """Raised when login fails or session has expired."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class IvasmsClient:
    """One instance per user. Holds its own cloudscraper session."""

    BASE_URL = "https://www.ivasms.com"
    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/117.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    def __init__(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        cookies_json: str | None = None,
    ) -> None:
        self.email = email
        self.password = password
        self.cookies_json = cookies_json
        self.scraper = cloudscraper.create_scraper()
        self.scraper.headers.update(self.BROWSER_HEADERS)
        self.csrf_token: str | None = None
        self.logged_in = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decompress(self, response) -> str:
        """Decode a possibly gzip/brotli-encoded response body to text."""
        try:
            return response.text
        except Exception:
            return response.content.decode("utf-8", errors="replace")

    async def _run(self, fn, *args, **kwargs):
        """Run a blocking cloudscraper call in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Log in to IVASMS using whichever credential method was supplied."""
        if self.cookies_json:
            await self._login_with_cookies()
        elif self.email and self.password:
            await self._login_with_password()
        else:
            raise IvasmsAuthError(
                "No IVASMS credentials configured. Set email/password or cookies."
            )

    async def _login_with_cookies(self) -> None:
        try:
            cookies_raw = json.loads(self.cookies_json)
        except json.JSONDecodeError as e:
            raise IvasmsAuthError(f"Invalid cookies JSON: {e}") from e

        # cookies_json can be either a dict {name: value} or a list of {name, value}
        if isinstance(cookies_raw, dict):
            cookies = cookies_raw
        elif isinstance(cookies_raw, list):
            cookies = {c["name"]: c["value"] for c in cookies_raw if "name" in c and "value" in c}
        else:
            raise IvasmsAuthError("cookies JSON must be a dict or a list")

        for name, value in cookies.items():
            self.scraper.cookies.set(name, value, domain="www.ivasms.com")

        await self._fetch_csrf_from_portal()

    async def _login_with_password(self) -> None:
        """Email + password login flow. Mirrors the reference scraper.py logic."""
        # Step 1: GET /login to pick up CSRF token + session cookie
        login_page = await self._run(
            self.scraper.get, f"{self.BASE_URL}/login", timeout=15
        )
        if login_page.status_code != 200:
            raise IvasmsAuthError(
                f"Could not load IVASMS login page (HTTP {login_page.status_code})"
            )

        soup = BeautifulSoup(self._decompress(login_page), "html.parser")
        csrf_input = soup.find("input", {"name": "_token"})
        login_csrf = csrf_input.get("value") if csrf_input else None

        login_data = {"email": self.email, "password": self.password}
        if login_csrf:
            login_data["_token"] = login_csrf

        # Step 2: POST /login with credentials
        login_resp = await self._run(
            self.scraper.post, f"{self.BASE_URL}/login", data=login_data, timeout=15
        )
        final_url = str(login_resp.url).lower()
        body = self._decompress(login_resp)
        ok = (
            "dashboard" in final_url
            or "portal" in final_url
            or "logout" in body.lower()
        )
        if not ok:
            raise IvasmsAuthError(
                "IVASMS login failed — check your email/password (or use cookies auth instead)."
            )

        # Step 3: fetch CSRF token from the portal page so we can call AJAX endpoints
        await self._fetch_csrf_from_portal()

    async def _fetch_csrf_from_portal(self) -> None:
        """GET /portal/sms/received and extract the CSRF token from the HTML."""
        resp = await self._run(
            self.scraper.get, f"{self.BASE_URL}/portal/sms/received", timeout=15
        )
        if resp.status_code != 200:
            raise IvasmsAuthError(
                f"Could not load IVASMS portal (HTTP {resp.status_code}). "
                "Your cookies may have expired."
            )
        soup = BeautifulSoup(self._decompress(resp), "html.parser")
        csrf_input = soup.find("input", {"name": "_token"})
        if not csrf_input or not csrf_input.get("value"):
            raise IvasmsAuthError(
                "Logged in but no CSRF token found on portal page — session may be invalid."
            )
        self.csrf_token = csrf_input["value"]
        self.logged_in = True

    async def _ensure_logged_in(self) -> None:
        if not self.logged_in:
            await self.login()

    def _ajax_headers(self) -> dict[str, str]:
        return {
            "Accept": "text/html, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/portal/sms/received",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_sms_stats(self, from_date: str = "", to_date: str = "") -> SmsStats:
        """
        Fetch SMS statistics for a date range.

        Dates are DD/MM/YYYY (Laravel-style). Empty string = today.
        Returns aggregated counts plus a list of phone ranges (countries).
        """
        async with self._lock:
            await self._ensure_logged_in()
            if not from_date:
                from_date = datetime.now().strftime("%d/%m/%Y")

            payload = {"from": from_date, "to": to_date, "_token": self.csrf_token}
            resp = await self._run(
                self.scraper.post,
                f"{self.BASE_URL}/portal/sms/received/getsms",
                data=payload,
                headers=self._ajax_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                raise IvasmsError(f"getsms failed (HTTP {resp.status_code})")

            soup = BeautifulSoup(self._decompress(resp), "html.parser")

            def _txt(selector: str) -> str:
                el = soup.select_one(selector)
                return el.get_text(strip=True) if el else "0"

            count_sms = _txt("#CountSMS")
            paid_sms = _txt("#PaidSMS")
            unpaid_sms = _txt("#UnpaidSMS")
            revenue_el = soup.select_one("#RevenueSMS")
            revenue = (
                revenue_el.get_text(strip=True).replace("USD", "").strip()
                if revenue_el
                else "0"
            )

            ranges: list[dict[str, str]] = []
            for item in soup.select("div.item"):
                cols = item.select(".col-sm-4, .col-3")
                if len(cols) < 5:
                    continue
                try:
                    ranges.append(
                        {
                            "country_number": cols[0].get_text(strip=True),
                            "count": cols[1].get_text(strip=True),
                            "paid": cols[2].get_text(strip=True),
                            "unpaid": cols[3].get_text(strip=True),
                            "revenue": cols[4].get_text(strip=True),
                        }
                    )
                except Exception:
                    continue

            return SmsStats(
                count_sms=count_sms,
                paid_sms=paid_sms,
                unpaid_sms=unpaid_sms,
                revenue=revenue,
                ranges=ranges,
            )

    async def get_numbers_in_range(
        self, phone_range: str, from_date: str = "", to_date: str = ""
    ) -> list[PhoneNumberInfo]:
        """Fetch all phone numbers that received SMS within a given range/country."""
        async with self._lock:
            await self._ensure_logged_in()
            if not from_date:
                from_date = datetime.now().strftime("%d/%m/%Y")

            payload = {
                "_token": self.csrf_token,
                "start": from_date,
                "end": to_date,
                "range": phone_range,
            }
            resp = await self._run(
                self.scraper.post,
                f"{self.BASE_URL}/portal/sms/received/getsms/number",
                data=payload,
                headers=self._ajax_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                raise IvasmsError(f"getsms/number failed (HTTP {resp.status_code})")

            soup = BeautifulSoup(self._decompress(resp), "html.parser")
            numbers: list[PhoneNumberInfo] = []
            for card in soup.select("div.card.card-body"):
                cols = card.select(".col-sm-4, .col-3")
                if len(cols) < 5:
                    continue
                onclick = card.select_one(".col-sm-4").get("onclick", "") if card.select_one(".col-sm-4") else ""
                # onclick looks like: viewSms('range','number','id')
                id_number = ""
                m = re.findall(r"['\"]([^'\"]+)['\"]", onclick)
                if len(m) >= 3:
                    id_number = m[-1]

                numbers.append(
                    PhoneNumberInfo(
                        phone_number=cols[0].get_text(strip=True),
                        count=cols[1].get_text(strip=True),
                        paid=cols[2].get_text(strip=True),
                        unpaid=cols[3].get_text(strip=True),
                        revenue=cols[4].get_text(strip=True),
                        id_number=id_number,
                    )
                )
            return numbers

    async def get_otp_message(
        self,
        phone_number: str,
        phone_range: str,
        from_date: str = "",
        to_date: str = "",
    ) -> OtpMessage | None:
        """Fetch the latest SMS body for a specific phone number."""
        async with self._lock:
            await self._ensure_logged_in()
            if not from_date:
                from_date = datetime.now().strftime("%d/%m/%Y")

            payload = {
                "_token": self.csrf_token,
                "start": from_date,
                "end": to_date,
                "Number": phone_number,
                "Range": phone_range,
            }
            resp = await self._run(
                self.scraper.post,
                f"{self.BASE_URL}/portal/sms/received/getsms/number/sms",
                data=payload,
                headers=self._ajax_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                raise IvasmsError(f"getsms/number/sms failed (HTTP {resp.status_code})")

            soup = BeautifulSoup(self._decompress(resp), "html.parser")
            msg_el = soup.select_one(".col-9.col-sm-6 p") or soup.select_one("p")
            if not msg_el:
                return None
            return OtpMessage(
                range=phone_range,
                phone_number=phone_number,
                message=msg_el.get_text(strip=True),
                fetched_at=datetime.now().strftime("%H:%M:%S"),
            )

    async def test_auth(self) -> tuple[bool, str]:
        """Try to log in; return (success, message). Used by the API-key setup flow."""
        try:
            await self.login()
            return True, "IVASMS account connected successfully."
        except IvasmsAuthError as e:
            return False, str(e)
        except Exception as e:  # noqa: BLE001
            return False, f"Unexpected error: {e}"


# ---------------------------------------------------------------------------
# Factory — builds a client from a user row
# ---------------------------------------------------------------------------

def client_from_user(user: dict[str, Any]) -> IvasmsClient:
    """Build an IvasmsClient from a database `users` row."""
    auth_method = (user.get("auth_method") or "email").lower()
    if auth_method == "cookies":
        return IvasmsClient(cookies_json=user.get("ivasms_cookies_json") or "")
    return IvasmsClient(
        email=user.get("ivasms_email") or settings.ivasms_default_email,
        password=user.get("ivasms_password") or settings.ivasms_default_password,
    )


# ---------------------------------------------------------------------------
# OTP extraction helper
# ---------------------------------------------------------------------------

_OTP_REGEXES = [
    r"\b(\d{4,8})\b",                 # generic 4-8 digit code
    r"code\s*(?:is|:)\s*(\d{3,8})",   # "code is 123456" / "code: 123456"
    r"otp\s*(?:is|:)\s*(\d{3,8})",    # "otp is 123456"
    r"verification code[:\s]+(\d{3,8})",
    r"\b(\d{6})\b",                   # 6-digit (most common OTP length)
]


def extract_otp(text: str) -> str | None:
    """Try to pull an OTP code out of an SMS message body."""
    if not text:
        return None
    lower = text.lower()
    # Prefer explicit "code/otp is" patterns first
    for pattern in _OTP_REGEXES[1:4]:
        m = re.search(pattern, lower)
        if m:
            return m.group(1)
    # Fall back to any standalone 4-8 digit number
    for pattern in _OTP_REGEXES[0:1] + _OTP_REGEXES[4:]:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None
