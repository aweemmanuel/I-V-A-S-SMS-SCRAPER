"""
Bot entry point.

Starts two things in parallel:
  1. aiogram polling loop (Telegram bot)
  2. A tiny ASGI health-check HTTP server on $PORT (Railway needs an HTTP
     listener to consider the container "healthy")

Both run in the same asyncio event loop.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramUnauthorizedError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from . import database as db
from . import messages as m  # noqa: F401  (warm import)
from .config import settings
from .handlers import get_main_router
from .otp_poller import active_session_count

# Logging — loguru is installed; configure standard logging nicely.
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ivasms-bot")


# ---------------------------------------------------------------------------
# Health-check server
# ---------------------------------------------------------------------------

async def _health(request):
    """Railway calls this on a schedule. Returns 200 if the bot is alive."""
    return JSONResponse(
        {
            "status": "ok",
            "service": "ivasms-otp-bot",
            "active_polls": active_session_count(),
        }
    )


async def _root(request):
    return JSONResponse(
        {
            "name": "IVASMS OTP Telegram Bot",
            "status": "running",
            "endpoints": {"/health": "Railway health check"},
        }
    )


def _build_health_app() -> Starlette:
    routes = [
        Route("/", _root),
        Route("/health", _health),
    ]
    return Starlette(routes=routes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run_bot(bot: Bot, dp: Dispatcher) -> None:
    """Run aiogram polling until cancelled."""
    me = await bot.get_me()
    logger.info("🤖 Bot started: @%s (id=%s)", me.username, me.id)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def _run_health() -> None:
    """Run the uvicorn health server in-process."""
    app = _build_health_app()
    config = uvicorn.Config(
        app,
        host=settings.health_host,
        port=settings.health_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    if not settings.bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    # Init DB
    await db.init_db()
    await db.stat_set("booted_at", int(__import__("time").time()))
    logger.info("📦 SQLite initialized at %s", settings.database_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Verify token before starting
    try:
        await bot.get_me()
    except TelegramUnauthorizedError:
        logger.error("Invalid TELEGRAM_BOT_TOKEN. Get one from @BotFather.")
        sys.exit(1)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(get_main_router())

    # Run bot + health server concurrently
    await asyncio.gather(
        _run_bot(bot, dp),
        _run_health(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot shutting down...")
