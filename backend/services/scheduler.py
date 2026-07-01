"""
APScheduler service for campaign auto-cycle scheduling.
Uses AsyncIOScheduler (APScheduler 3.x) with FastAPI's event loop.
"""

import logging
from typing import List, Dict, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from ..database import SessionLocal
from ..models import Campaign

logger = logging.getLogger(__name__)

# Module-level scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the scheduler instance."""
    return _scheduler


async def _run_link_monitor():
    """
    Job function that re-verifies all live/paid links.
    Runs weekly, only checks orders not verified in the last 30 days.
    """
    db = SessionLocal()
    try:
        from .link_monitor import check_all_live_links
        logger.info("Scheduler: running link monitor check")
        result = await check_all_live_links(db)
        logger.info(
            f"Scheduler: link monitor done — checked {result['total_checked']}, "
            f"verified {result['verified']}, issues {result['issues']}, removed {result['removed']}"
        )
    except Exception as e:
        logger.error(f"Scheduler: error running link monitor: {e}", exc_info=True)
    finally:
        db.close()


async def _run_campaign_job(campaign_id: str):
    """
    Job function that runs a campaign cycle.
    Gets a fresh DB session, runs the cycle, handles errors gracefully.
    """
    db = SessionLocal()
    try:
        from .campaign_autopilot import run_campaign_cycle
        logger.info(f"Scheduler: running cycle for campaign {campaign_id}")
        result = await run_campaign_cycle(campaign_id, db)
        logger.info(f"Scheduler: campaign {campaign_id} cycle result: {result}")

        # If campaign was paused due to budget, remove its job
        if not result.get("success") and result.get("reason") == "Not eligible for new order":
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if campaign and (campaign.status != "active" or campaign.mode != "auto"):
                remove_campaign_job(campaign_id)
                logger.info(f"Scheduler: removed job for campaign {campaign_id} (no longer eligible)")
    except Exception as e:
        logger.error(f"Scheduler: error running campaign {campaign_id}: {e}", exc_info=True)
    finally:
        db.close()


async def init_scheduler():
    """Create scheduler, load jobs from DB, start it."""
    global _scheduler

    if _scheduler is not None:
        logger.warning("Scheduler already initialized")
        return

    _scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        job_defaults={
            "misfire_grace_time": 3600,
            "coalesce": True,
            "max_instances": 1,
        },
    )

    # Load active auto campaigns
    db = SessionLocal()
    try:
        campaigns = db.query(Campaign).filter(
            Campaign.mode == "auto",
            Campaign.schedule_enabled == True,
            Campaign.status == "active",
            Campaign.deleted_at.is_(None),
        ).all()

        for campaign in campaigns:
            interval = campaign.schedule_interval_hours or 6
            _scheduler.add_job(
                _run_campaign_job,
                trigger=IntervalTrigger(hours=interval),
                id=f"campaign_{campaign.id}",
                args=[campaign.id],
                replace_existing=True,
            )
            logger.info(f"Scheduler: loaded job for campaign '{campaign.name}' (every {interval}h)")

        logger.info(f"Scheduler: loaded {len(campaigns)} campaign jobs")
    except Exception as e:
        logger.error(f"Scheduler: error loading jobs: {e}", exc_info=True)
    finally:
        db.close()

    # Add link monitoring job — runs weekly on Sundays at 6 AM
    _scheduler.add_job(
        _run_link_monitor,
        trigger=CronTrigger(day_of_week="sun", hour=6, minute=0),
        id="link_monitor_weekly",
        replace_existing=True,
    )
    logger.info("Scheduler: added weekly link monitor job (Sundays 6 AM)")

    _scheduler.start()
    logger.info("Scheduler: started")


async def shutdown_scheduler():
    """Clean shutdown of the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: shut down")
        _scheduler = None


def add_campaign_job(campaign_id: str, interval_hours: int):
    """Add or update a job for a campaign."""
    if _scheduler is None:
        logger.warning("Scheduler not initialized, cannot add job")
        return

    job_id = f"campaign_{campaign_id}"

    # Remove existing job if present
    existing = _scheduler.get_job(job_id)
    if existing:
        _scheduler.remove_job(job_id)

    _scheduler.add_job(
        _run_campaign_job,
        trigger=IntervalTrigger(hours=interval_hours),
        id=job_id,
        args=[campaign_id],
    )
    logger.info(f"Scheduler: added/updated job {job_id} (every {interval_hours}h)")


def remove_campaign_job(campaign_id: str):
    """Remove a job for a campaign."""
    if _scheduler is None:
        return

    job_id = f"campaign_{campaign_id}"
    existing = _scheduler.get_job(job_id)
    if existing:
        _scheduler.remove_job(job_id)
        logger.info(f"Scheduler: removed job {job_id}")


async def reload_campaign_jobs():
    """Reload all jobs from DB."""
    if _scheduler is None:
        logger.warning("Scheduler not initialized")
        return

    # Remove all existing campaign jobs
    for job in _scheduler.get_jobs():
        if job.id.startswith("campaign_"):
            _scheduler.remove_job(job.id)

    # Reload from DB
    db = SessionLocal()
    try:
        campaigns = db.query(Campaign).filter(
            Campaign.mode == "auto",
            Campaign.schedule_enabled == True,
            Campaign.status == "active",
            Campaign.deleted_at.is_(None),
        ).all()

        for campaign in campaigns:
            interval = campaign.schedule_interval_hours or 6
            _scheduler.add_job(
                _run_campaign_job,
                trigger=IntervalTrigger(hours=interval),
                id=f"campaign_{campaign.id}",
                args=[campaign.id],
            )

        logger.info(f"Scheduler: reloaded {len(campaigns)} campaign jobs")
    except Exception as e:
        logger.error(f"Scheduler: error reloading jobs: {e}", exc_info=True)
    finally:
        db.close()


def get_scheduled_jobs() -> List[Dict[str, Any]]:
    """Return list of active jobs with next run time."""
    if _scheduler is None:
        return []

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
