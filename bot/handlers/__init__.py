"""Handler registry — import all routers and expose them as a list."""
from __future__ import annotations

from aiogram import Router

from .start import router as start_router
from .numbers import router as numbers_router
from .otp import router as otp_router
from .status import router as status_router


def get_main_router() -> Router:
    """Build the main router with all sub-routers attached in order."""
    main = Router(name="root")
    # Order matters: more specific routers first.
    main.include_router(start_router)
    main.include_router(numbers_router)
    main.include_router(otp_router)
    main.include_router(status_router)
    return main


__all__ = ["get_main_router"]
