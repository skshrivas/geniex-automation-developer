"""
Campaign lifecycle management and result aggregation.

Campaigns group related scraping jobs and track aggregate outcomes.
The campaign success_rate() reflects job completion count; price_coverage()
reflects actual data yield from completed jobs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .models import Campaign, CampaignStatus, Job, JobStatus, ParseResult

logger = logging.getLogger(__name__)


class CampaignManager:
    """
    Manages campaign creation, status tracking, and result reporting.
    """

    def __init__(self) -> None:
        self._campaigns: dict = {}

    def register(self, campaign: Campaign) -> None:
        self._campaigns[campaign.id] = campaign
        logger.info(
            "campaign registered: %s (%d urls)",
            campaign.id, len(campaign.target_urls),
        )

    def get(self, campaign_id: str) -> Optional[Campaign]:
        return self._campaigns.get(campaign_id)

    def get_pending(self) -> List[Campaign]:
        return [
            c for c in self._campaigns.values()
            if c.status == CampaignStatus.PENDING
        ]

    def finalize(self, campaign: Campaign) -> None:
        """
        Mark a campaign complete or failed based on job outcomes.
        Called by the worker after processing all jobs.
        """
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.EXHAUSTED}
        if not all(j.status in terminal for j in campaign.jobs):
            logger.warning(
                "finalize() called on campaign %s with non-terminal jobs",
                campaign.id,
            )
            return

        rate = campaign.success_rate()
        coverage = campaign.price_coverage()
        campaign.completed_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "campaign %s finalized: success_rate=%.0f%% price_coverage=%.0f%%",
            campaign.id, rate * 100, coverage * 100,
        )

    def summary(self, campaign_id: str) -> dict:
        """Return a status summary suitable for operator dashboards."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"error": "campaign not found"}

        jobs_by_status: dict = {}
        for job in campaign.jobs:
            s = job.status.value
            jobs_by_status[s] = jobs_by_status.get(s, 0) + 1

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": campaign.status.value,
            "total_jobs": len(campaign.jobs),
            "jobs_by_status": jobs_by_status,
            "success_rate": round(campaign.success_rate() * 100, 1),
            "price_coverage": round(campaign.price_coverage() * 100, 1),
            "completed_at": campaign.completed_at,
        }
