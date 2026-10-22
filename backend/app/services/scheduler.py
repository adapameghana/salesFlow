"""Background loop that runs the payment-reminder round every REMINDER_CHECK_MINUTES.

A Postgres advisory lock makes sure only one round runs at a time, even if the backend is
started more than once or a manager clicks "Run now" while the loop is busy.
"""
import asyncio
import logging

from sqlalchemy import text

from ..config import get_settings
from ..database import SessionLocal, engine
from ..models import User
from .reminder_service import run_reminder_cycle

log = logging.getLogger(__name__)

LOCK_KEY = 74_210_001  # arbitrary, unique to the reminder round


def run_locked_cycle(user_id: int | None = None) -> dict | None:
    """Run one reminder round. Returns None if another round holds the lock."""
    with engine.connect() as conn:
        locked = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        conn.commit()  # the lock is session-level; don't sit in an open transaction
        if not locked:
            return None
        try:
            with SessionLocal() as db:
                user = db.get(User, user_id) if user_id else None
                return run_reminder_cycle(db, user=user)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            conn.commit()


async def reminder_loop() -> None:
    minutes = max(1, get_settings().reminder_check_minutes)
    log.info("Payment reminder scheduler started (every %s min)", minutes)
    while True:
        try:
            result = await asyncio.to_thread(run_locked_cycle)
            if result and result["started"]:
                log.info("Payment reminders: %s", result["message"])
        except Exception:  # keep the loop alive; the next round retries
            log.exception("Payment reminder round failed")
        await asyncio.sleep(minutes * 60)
