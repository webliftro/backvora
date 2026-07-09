"""Campaign router request normalization tests."""

import pytest

from backend.models import Campaign
from backend.routers.campaigns import CampaignCreate, CampaignUpdate, create_campaign, update_campaign


@pytest.mark.asyncio
async def test_campaign_create_accepts_blank_schedule_interval_default(db):
    data = CampaignCreate.model_validate({
        "name": "Campaign",
        "target_site": "camhours.com",
        "status": "Paused",
        "schedule_interval_hours": "",
    })

    result = await create_campaign(data, db=db)

    campaign = db.query(Campaign).filter(Campaign.id == result["id"]).one()
    assert campaign.status == "paused"
    assert campaign.schedule_interval_hours == 6


@pytest.mark.asyncio
async def test_campaign_update_accepts_blank_optional_numeric_fields(db):
    campaign = Campaign(
        id="camp-1",
        name="Campaign",
        target_site="camhours.com",
        status="active",
        filter_traffic_min=1000,
        filter_dr_min=20,
        budget_total=500,
    )
    db.add(campaign)
    db.commit()

    data = CampaignUpdate.model_validate({
        "status": "Paused",
        "filter_traffic_min": "",
        "filter_traffic_max": "",
        "filter_dr_min": "",
        "filter_dr_max": "",
        "filter_price_min": "",
        "filter_price_max": "",
        "budget_total": "",
    })

    result = await update_campaign(campaign.id, data, db=db)

    db.refresh(campaign)
    assert result == {"success": True, "id": campaign.id}
    assert campaign.status == "paused"
    assert campaign.filter_traffic_min is None
    assert campaign.filter_dr_min is None
    assert campaign.budget_total is None
