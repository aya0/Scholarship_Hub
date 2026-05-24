"""
scheduler/jobs.py
-----------------
APScheduler jobs that run scrapers on a schedule.
Each source can have its own interval (default 24h).
The scheduler also runs deadline monitoring to trigger notifications.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from datetime import datetime, timedelta

from db.session import get_db
from scraper.pipeline import ScrapePipeline
from db.models import Scholarship, Notification, User, Favorite, NotifChannel, ScholarshipStatus


# ─────────────────────────────────────────────
# Job definitions
# ─────────────────────────────────────────────

async def job_scrape_all():
    """Run all active scrapers. Fires daily at 03:00 UTC."""
    logger.info("[scheduler] Starting daily scrape job")
    db = next(get_db())
    pipeline = ScrapePipeline(db)
    stats = await pipeline.run_all()
    total_new = sum(s.get("new", 0) for s in stats.values())
    logger.info(f"[scheduler] Daily scrape complete — {total_new} new items in review queue")


async def job_scrape_single(scraper_key: str):
    """Run one specific scraper on demand or on its own schedule."""
    logger.info(f"[scheduler] Scraping single source: {scraper_key}")
    db = next(get_db())
    pipeline = ScrapePipeline(db)
    stats = await pipeline.run_source(scraper_key)
    logger.info(f"[scheduler] {scraper_key} — {stats}")


async def job_deadline_reminders():
    """
    Check for scholarships closing in 21, 7, and 1 days.
    Create a Notification record for each user who favorited the scholarship.
    Fires daily at 08:00 UTC.
    """
    logger.info("[scheduler] Running deadline reminder check")
    db = next(get_db())
    today = datetime.utcnow().date()
    reminder_windows = [1, 7, 21]   # days before deadline

    for days in reminder_windows:
        target_date = today + timedelta(days=days)
        closing_soon = (
            db.query(Scholarship)
            .filter(
                Scholarship.close_date == target_date,
                Scholarship.is_active == True,
                Scholarship.status == ScholarshipStatus.OPEN
            )
            .all()
        )
        for scholarship in closing_soon:
            # Find all users who favorited this scholarship
            favorites = (
                db.query(Favorite)
                .filter(Favorite.scholarship_id == scholarship.id)
                .all()
            )
            for fav in favorites:
                # Avoid duplicate notifications
                already_sent = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id        == fav.user_id,
                        Notification.scholarship_id == scholarship.id,
                        Notification.type           == f"deadline_{days}d",
                    )
                    .first()
                )
                if already_sent:
                    continue

                notif = Notification(
                    user_id        = fav.user_id,
                    scholarship_id = scholarship.id,
                    type           = f"deadline_{days}d",
                    channel        = NotifChannel.EMAIL,
                    message        = (
                        f"Reminder: '{scholarship.title}' closes in {days} day(s) "
                        f"({scholarship.close_date}). Don't miss it!"
                    ),
                    scheduled_at   = datetime.utcnow(),
                )
                db.add(notif)

    db.commit()
    logger.info("[scheduler] Deadline reminders queued")


async def job_close_expired_scholarships():
    """
    Mark scholarships whose close_date has passed as CLOSED.
    Fires daily at 00:05 UTC.
    """
    logger.info("[scheduler] Checking for expired scholarships")
    db = next(get_db())
    today = datetime.utcnow().date()
    from db.models import ScholarshipStatus
    expired = (
        db.query(Scholarship)
        .filter(
            Scholarship.close_date < today,
            Scholarship.status == ScholarshipStatus.OPEN,
        )
        .all()
    )
    for s in expired:
        s.status = ScholarshipStatus.CLOSED
        logger.info(f"[scheduler] Closed expired: {s.title}")
    db.commit()
    logger.info(f"[scheduler] Marked {len(expired)} scholarships as closed")


# ─────────────────────────────────────────────
# Scheduler setup
# ─────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Daily full scrape at 03:00 UTC
    scheduler.add_job(
        job_scrape_all,
        CronTrigger(hour=3, minute=0),
        id="scrape_all",
        name="Daily full scrape",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Deadline reminders at 08:00 UTC daily
    scheduler.add_job(
        job_deadline_reminders,
        CronTrigger(hour=8, minute=0),
        id="deadline_reminders",
        name="Deadline reminder notifications",
        replace_existing=True,
    )

    # Close expired scholarships at 00:05 UTC daily
    scheduler.add_job(
        job_close_expired_scholarships,
        CronTrigger(hour=0, minute=5),
        id="close_expired",
        name="Close expired scholarships",
        replace_existing=True,
    )

    # High-frequency sources: ReliefWeb every 6 hours
    scheduler.add_job(
        lambda: job_scrape_single("reliefweb"),
        IntervalTrigger(hours=6),
        id="scrape_reliefweb",
        name="ReliefWeb every 6h",
        replace_existing=True,
    )

    return scheduler
