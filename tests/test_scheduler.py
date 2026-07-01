"""Tests for the APScheduler campaign scheduling service."""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from backend.models import Campaign
from backend.services import scheduler as sched_module


def campaign_jobs() -> list:
    """Get only campaign jobs (filter out system jobs like link_monitor)."""
    return [j for j in sched_module.get_scheduled_jobs() if j["id"].startswith("campaign_")]


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Reset scheduler state between tests."""
    sched_module._scheduler = None
    yield
    if sched_module._scheduler is not None:
        try:
            sched_module._scheduler.shutdown(wait=False)
        except Exception:
            pass
        sched_module._scheduler = None


@pytest.fixture
def auto_campaign(db):
    """An active auto campaign with scheduling enabled."""
    c = Campaign(
        id="auto-1",
        name="Auto Campaign",
        target_site="mysite.com",
        status="active",
        mode="auto",
        schedule_enabled=True,
        schedule_interval_hours=4,
    )
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def paused_campaign(db):
    """A paused campaign."""
    c = Campaign(
        id="paused-1",
        name="Paused Campaign",
        target_site="mysite.com",
        status="paused",
        mode="auto",
        schedule_enabled=True,
        schedule_interval_hours=6,
    )
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def manual_campaign(db):
    """A manual campaign."""
    c = Campaign(
        id="manual-1",
        name="Manual Campaign",
        target_site="mysite.com",
        status="active",
        mode="manual",
        schedule_enabled=False,
        schedule_interval_hours=6,
    )
    db.add(c)
    db.commit()
    return c


class TestSchedulerInit:
    @pytest.mark.asyncio
    async def test_init_starts_scheduler(self, db, auto_campaign):
        """Scheduler starts and loads active auto campaigns."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        assert sched_module._scheduler is not None
        assert sched_module._scheduler.running

        jobs = campaign_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "campaign_auto-1"

    @pytest.mark.asyncio
    async def test_paused_campaigns_not_scheduled(self, db, paused_campaign):
        """Paused campaigns don't get scheduled."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        jobs = campaign_jobs()
        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_manual_campaigns_not_scheduled(self, db, manual_campaign):
        """Manual campaigns don't get scheduled."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        jobs = campaign_jobs()
        assert len(jobs) == 0


class TestAddRemoveJobs:
    @pytest.mark.asyncio
    async def test_add_campaign_job(self, db):
        """Adding a campaign job works."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        sched_module.add_campaign_job("test-123", 8)
        jobs = sched_module.get_scheduled_jobs()
        job_ids = [j["id"] for j in jobs]
        assert "campaign_test-123" in job_ids

    @pytest.mark.asyncio
    async def test_remove_campaign_job(self, db, auto_campaign):
        """Removing a campaign job works."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        assert len(campaign_jobs()) == 1
        sched_module.remove_campaign_job("auto-1")
        assert len(campaign_jobs()) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_job(self, db):
        """Removing a non-existent job doesn't crash."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        sched_module.remove_campaign_job("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_add_updates_existing(self, db):
        """Adding a job with same campaign_id updates it."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        sched_module.add_campaign_job("test-1", 4)
        sched_module.add_campaign_job("test-1", 8)
        jobs = sched_module.get_scheduled_jobs()
        campaign_jobs = [j for j in jobs if j["id"] == "campaign_test-1"]
        assert len(campaign_jobs) == 1
        assert "8:00:00" in campaign_jobs[0]["trigger"]


class TestReloadJobs:
    @pytest.mark.asyncio
    async def test_reload_campaign_jobs(self, db, auto_campaign):
        """Reload all jobs from DB."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()
            # Add a stale job
            sched_module.add_campaign_job("stale-1", 2)
            assert len(campaign_jobs()) == 2

            await sched_module.reload_campaign_jobs()
            jobs = campaign_jobs()
            assert len(jobs) == 1
            assert jobs[0]["id"] == "campaign_auto-1"


class TestGetScheduledJobs:
    @pytest.mark.asyncio
    async def test_get_scheduled_jobs_returns_correct_info(self, db, auto_campaign):
        """get_scheduled_jobs returns correct info."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        jobs = campaign_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job["id"] == "campaign_auto-1"
        assert job["next_run_time"] is not None
        assert "trigger" in job

    def test_get_scheduled_jobs_no_scheduler(self):
        """Returns empty list when scheduler not initialized."""
        assert sched_module.get_scheduled_jobs() == []


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown(self, db):
        """Clean shutdown works."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        assert sched_module._scheduler is not None
        await sched_module.shutdown_scheduler()
        assert sched_module._scheduler is None


class TestJobExecution:
    @pytest.mark.asyncio
    async def test_job_handles_errors_gracefully(self, db):
        """Scheduler handles errors in job execution gracefully."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            with patch(
                "backend.services.campaign_autopilot.run_campaign_cycle",
                side_effect=Exception("Test error"),
            ):
                # Should not raise
                await sched_module._run_campaign_job("nonexistent-id")


class TestBudgetPauseIntegration:
    @pytest.mark.asyncio
    async def test_budget_exhaustion_removes_job(self, db, auto_campaign):
        """Budget exhaustion removes the scheduler job."""
        with patch.object(sched_module, "SessionLocal", return_value=db):
            await sched_module.init_scheduler()

        assert len(campaign_jobs()) == 1

        # Simulate budget exhaustion pausing the campaign
        auto_campaign.status = "paused"
        db.commit()
        sched_module.remove_campaign_job(auto_campaign.id)

        assert len(campaign_jobs()) == 0
