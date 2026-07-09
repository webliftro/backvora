"""Campaign router request normalization tests."""

import pytest

from backend.models import Campaign, Contact, Domain, LinkPrice
from backend.routers.campaigns import (
    CampaignCreate,
    CampaignDomainExclusionCreate,
    CampaignUpdate,
    create_campaign,
    get_ready_domains,
    hide_ready_domain,
    update_campaign,
)


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


@pytest.mark.asyncio
async def test_ready_domain_exclusion_is_campaign_scoped(db):
    campaign = Campaign(id="camp-1", name="Campaign", target_site="camhours.com")
    other_campaign = Campaign(id="camp-2", name="Other", target_site="camhours.com")
    domain = Domain(
        id="dom-1",
        domain="adulttoplist.example",
        domain_niche="adult",
        category="adult toplist",
        email="owner@example.com",
    )
    db.add_all([
        campaign,
        other_campaign,
        domain,
        Contact(id="contact-1", domain_id=domain.id, email="owner@example.com", is_primary=True),
        LinkPrice(id="price-1", domain_id=domain.id, link_type="Guest Post", price=100),
    ])
    db.commit()

    before = await get_ready_domains(campaign.id, db=db)
    assert [item["id"] for item in before["items"]] == [domain.id]
    assert "topsite" in before["items"][0]["type_tags"]
    assert before["summary"]["all_domains"] == 1
    assert before["summary"]["available_domains"] == 1
    assert before["summary"]["with_contact"] == 1
    assert before["summary"]["with_price"] == 1
    assert before["summary"]["ready"] == 1
    assert before["summary"]["returned"] == 1

    await hide_ready_domain(
        campaign.id,
        CampaignDomainExclusionCreate(domain_id=domain.id, reason="not relevant"),
        db=db,
    )

    after = await get_ready_domains(campaign.id, db=db)
    other = await get_ready_domains(other_campaign.id, db=db)
    assert after["items"] == []
    assert after["summary"]["hidden_in_campaign"] == 1
    assert after["summary"]["ready"] == 0
    assert [item["id"] for item in other["items"]] == [domain.id]
