"""Operational agent registry and audit tests."""

import asyncio
from datetime import datetime, timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.models import (
    AgentActionAudit,
    AgentMessage,
    AgentSession,
    AnchorText,
    Campaign,
    CampaignTarget,
    Contact,
    Domain,
    LinkPrice,
    Order,
    TargetSite,
    TargetURL,
    User,
)
import backend.routers.agent as agent_router
from backend.routers.agent import (
    AgentCommandRequest,
    AgentActionRequest,
    _parse_planner_json,
    send_agent_command,
    execute_action,
    confirm_action,
    cancel_action,
    delete_agent_session,
    list_agent_sessions,
    get_agent_session,
)
from backend.services.agent_actions import (
    ActionRegistry,
    AgentAction,
    ActionResult,
    execute_registered_action,
    registry,
)


def make_user(db):
    user = User(id="user-1", email="r@example.com", password_hash="x", is_active=True)
    db.add(user)
    db.commit()
    return user


def test_registry_rejects_forbidden_action_names():
    local = ActionRegistry()

    class Args(BaseModel):
        pass

    def handler(_db, _user, _args):
        return ActionResult(message="ok")

    with pytest.raises(ValueError):
        local.register(AgentAction("shell.exec", "bad", "high_risk", Args, handler))


def test_planner_json_parser_accepts_fenced_or_prefaced_json():
    fenced = """```json
{"action_name":"campaign.create","action_args":{"target_site":"example.com"}}
```"""
    prefaced = (
        "Here is the action:\n"
        '{"action_name":"domain.search","action_args":{"query":"porn"}}'
    )

    assert _parse_planner_json(fenced)["action_name"] == "campaign.create"
    assert _parse_planner_json(prefaced) == {
        "action_name": "domain.search",
        "action_args": {"query": "porn"},
    }


def make_target_site(db):
    site = TargetSite(
        id="site-1",
        domain="camhours.com",
        name="CamHours",
        brand_variations="Cam Hours,CAMHOURS",
    )
    url = TargetURL(
        id="target-url-1",
        site_id=site.id,
        url="https://camhours.com/girls",
        description="Live cam girls category",
        priority=10,
    )
    anchor = AnchorText(
        id="anchor-1",
        target_url_id=url.id,
        text="CamHours",
        anchor_type="brand",
    )
    db.add_all([site, url, anchor])
    db.commit()
    return site


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(db):
    user = make_user(db)

    with pytest.raises(Exception) as exc:
        await execute_registered_action(db, user, "git.deploy", {})

    assert "Unknown action" in str(exc.value)


@pytest.mark.asyncio
async def test_planned_campaign_create_resolves_known_target_site(db, monkeypatch):
    user = make_user(db)
    site = make_target_site(db)

    async def fake_plan(message, db):
        return "campaign.create", {
            "name": "CamHours Adult Directories",
            "filter_niche_tags": "adult,directory",
        }

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    result = await send_agent_command(AgentCommandRequest(
        message="Create a new Camhours linkbuilding campaign with only links from adult directories",
    ), db=db, user=user)

    campaign = db.query(Campaign).filter(Campaign.name == "CamHours Adult Directories").one()
    assert result["action"]["status"] == "success"
    assert campaign.target_site == "camhours.com"
    assert campaign.target_site_id == site.id
    assert campaign.filter_niche_tags == "adult,directory"


@pytest.mark.asyncio
async def test_agent_sessions_are_saved_and_loadable(db, monkeypatch):
    user = make_user(db)

    async def fake_plan(_message, _db):
        return agent_router.AgentPlan(None, {}, "Saved response")

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    first = await send_agent_command(AgentCommandRequest(
        message="Talk through a CamHours campaign",
    ), db=db, user=user)
    second = await send_agent_command(AgentCommandRequest(
        message="Continue in the same conversation",
        session_id=first["session_id"],
    ), db=db, user=user)

    sessions = await list_agent_sessions(db=db, user=user)
    loaded = await get_agent_session(first["session_id"], db=db, user=user)

    assert second["session_id"] == first["session_id"]
    assert sessions["items"][0]["id"] == first["session_id"]
    assert sessions["items"][0]["title"] == "Talk through a CamHours campaign"
    assert [m["role"] for m in loaded["messages"]] == ["user", "assistant", "user", "assistant"]
    assert loaded["messages"][1]["content"] == "Saved response"


@pytest.mark.asyncio
async def test_new_agent_session_creates_separate_conversation(db, monkeypatch):
    user = make_user(db)

    async def fake_plan(_message, _db):
        return agent_router.AgentPlan(None, {}, "New response")

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    first = await send_agent_command(AgentCommandRequest(message="First conversation"), db=db, user=user)
    second = await send_agent_command(AgentCommandRequest(message="Second conversation"), db=db, user=user)

    sessions = await list_agent_sessions(db=db, user=user)

    assert first["session_id"] != second["session_id"]
    assert {item["id"] for item in sessions["items"]} == {first["session_id"], second["session_id"]}


@pytest.mark.asyncio
async def test_continued_agent_session_moves_to_top(db, monkeypatch):
    user = make_user(db)

    async def fake_plan(_message, _db):
        return agent_router.AgentPlan(None, {}, "Saved response")

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    first = await send_agent_command(AgentCommandRequest(message="First conversation"), db=db, user=user)
    second = await send_agent_command(AgentCommandRequest(message="Second conversation"), db=db, user=user)

    old = datetime.utcnow() - timedelta(days=2)
    newer = datetime.utcnow() - timedelta(days=1)
    db.query(AgentSession).filter(AgentSession.id == first["session_id"]).update({"updated_at": old})
    db.query(AgentSession).filter(AgentSession.id == second["session_id"]).update({"updated_at": newer})
    db.commit()

    await send_agent_command(AgentCommandRequest(
        message="Continue the first conversation",
        session_id=first["session_id"],
    ), db=db, user=user)

    sessions = await list_agent_sessions(db=db, user=user)

    assert sessions["items"][0]["id"] == first["session_id"]


@pytest.mark.asyncio
async def test_delete_agent_session_soft_deletes_owned_conversation(db, monkeypatch):
    user = make_user(db)

    async def fake_plan(_message, _db):
        return agent_router.AgentPlan(None, {}, "Saved response")

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    result = await send_agent_command(AgentCommandRequest(message="Temporary conversation"), db=db, user=user)
    audit = AgentActionAudit(
        id="audit-delete-1",
        session_id=result["session_id"],
        user_id=user.id,
        action_name="campaign.update",
        permission="mutate",
        requires_confirmation=True,
        status="pending",
    )
    successful_audit = AgentActionAudit(
        id="audit-delete-2",
        session_id=result["session_id"],
        user_id=user.id,
        action_name="domain.search",
        permission="read",
        requires_confirmation=False,
        status="success",
        result_json={"ok": True},
    )
    db.add_all([audit, successful_audit])
    db.commit()

    deleted = await delete_agent_session(result["session_id"], db=db, user=user)
    sessions = await list_agent_sessions(db=db, user=user)

    session = db.query(AgentSession).filter(AgentSession.id == result["session_id"]).one()
    messages = db.query(AgentMessage).filter(AgentMessage.session_id == result["session_id"]).all()
    db.refresh(audit)
    db.refresh(successful_audit)
    assert deleted == {"success": True, "id": result["session_id"]}
    assert sessions["items"] == []
    assert session.deleted_at is not None
    assert all(message.deleted_at is not None for message in messages)
    assert audit.deleted_at is not None
    assert audit.status == "cancelled"
    assert audit.error == "conversation deleted"
    assert successful_audit.deleted_at is not None
    assert successful_audit.status == "success"
    assert successful_audit.error is None


@pytest.mark.asyncio
async def test_delete_agent_session_is_user_scoped(db):
    owner = make_user(db)
    other = User(id="user-2", email="other@example.com", password_hash="x", is_active=True)
    session = AgentSession(id="session-1", user_id=owner.id, title="Private")
    db.add_all([other, session])
    db.commit()

    with pytest.raises(Exception) as exc:
        await delete_agent_session(session.id, db=db, user=other)

    assert "404" in str(exc.value)
    db.refresh(session)
    assert session.deleted_at is None


@pytest.mark.asyncio
async def test_target_site_enrichment_does_not_substring_match_short_alias(db, monkeypatch):
    user = make_user(db)
    db.add(TargetSite(id="site-hub", domain="hub.com", name="Hub"))
    db.commit()

    async def fake_plan(message, db):
        return "campaign.create", {
            "name": "Wrongly Matched Campaign",
            "filter_niche_tags": "adult,directory",
        }

    monkeypatch.setattr(agent_router, "_plan_action_with_llm", fake_plan)

    result = await send_agent_command(AgentCommandRequest(
        message="Create a pornhub campaign from adult directories",
    ), db=db, user=user)

    assert result["action"]["status"] == "failed"
    assert "target_site or target_site_id is required" in result["action"]["error"]
    assert db.query(Campaign).filter(Campaign.name == "Wrongly Matched Campaign").count() == 0


@pytest.mark.asyncio
async def test_claude_cli_planner_json_can_return_chat_response(db, monkeypatch):
    user = make_user(db)

    async def fake_run_claude_cli(prompt):
        assert "Return ONLY compact JSON" in prompt
        assert "`response`, `action_name`, and `action_args`" in prompt
        assert "Never request shell/code/deploy/migration/file/env/secret access" in prompt
        return '{"response":"I can discuss the campaign first.","action_name":null,"action_args":{}}'

    monkeypatch.setattr(agent_router, "_run_claude_cli", fake_run_claude_cli)

    result = await send_agent_command(AgentCommandRequest(
        message="Can we talk through the adult directory campaign first?",
    ), db=db, user=user)

    assert result["action"] is None
    assert result["message"]["role"] == "assistant"
    assert result["message"]["content"] == "I can discuss the campaign first."


@pytest.mark.asyncio
async def test_claude_cli_planner_json_can_return_action(db, monkeypatch):
    user = make_user(db)
    make_target_site(db)

    async def fake_run_claude_cli(_prompt):
        return (
            '{"response":"I will create a researched campaign.",'
            '"action_name":"campaign.create_from_research",'
            '"action_args":{"target_site_query":"CamHours","name":"CamHours Adult Directories",'
            '"filter_niche_tags":"adult,directory"}}'
        )

    monkeypatch.setattr(agent_router, "_run_claude_cli", fake_run_claude_cli)

    result = await send_agent_command(AgentCommandRequest(
        message="Create a new Camhours linkbuilding campaign with only links from adult directories",
    ), db=db, user=user)

    campaign = db.query(Campaign).filter(Campaign.name == "CamHours Adult Directories").one()
    assert result["action"]["status"] == "success"
    assert campaign.target_site == "camhours.com"
    assert campaign.filter_niche_tags == "adult,directory"


@pytest.mark.asyncio
async def test_campaign_update_action_persists_adult_directory_filters(db):
    user = make_user(db)
    campaign = Campaign(
        id="16056a2a-bc31-4f07-b8a0-8e08d5fe060e",
        name="Existing CamHours Campaign",
        target_site="camhours.com",
        filter_niche_tags="adult",
    )
    db.add(campaign)
    db.commit()

    action, result = await execute_registered_action(db, user, "campaign.update", {
        "campaign_id": campaign.id,
        "filter_niche_tags": "adult,directory",
    })

    db.refresh(campaign)
    assert action.permission == "mutate"
    assert campaign.filter_niche_tags == "adult,directory"
    assert result.data["campaign"]["filter_niche_tags"] == "adult,directory"


@pytest.mark.asyncio
async def test_campaign_update_action_normalizes_status_values(db):
    user = make_user(db)
    campaign = Campaign(
        id="16056a2a-bc31-4f07-b8a0-8e08d5fe060e",
        name="Existing CamHours Campaign",
        target_site="camhours.com",
        status="active",
    )
    db.add(campaign)
    db.commit()

    _action, result = await execute_registered_action(db, user, "campaign.update", {
        "campaign_id": campaign.id,
        "status": "Paused",
    })

    db.refresh(campaign)
    assert campaign.status == "paused"
    assert result.data["campaign"]["status"] == "paused"


@pytest.mark.asyncio
async def test_campaign_create_action_normalizes_status_values(db):
    user = make_user(db)

    _action, result = await execute_registered_action(db, user, "campaign.create", {
        "name": "Paused Campaign",
        "target_site": "camhours.com",
        "status": "Paused",
    })

    campaign = db.query(Campaign).filter(Campaign.id == result.data["campaign"]["id"]).one()
    assert campaign.status == "paused"


@pytest.mark.asyncio
async def test_campaign_update_action_invalid_status_is_readable(db):
    user = make_user(db)
    campaign = Campaign(
        id="16056a2a-bc31-4f07-b8a0-8e08d5fe060e",
        name="Existing CamHours Campaign",
        target_site="camhours.com",
        status="active",
    )
    db.add(campaign)
    db.commit()

    result = await execute_action(AgentActionRequest(
        action_name="campaign.update",
        action_args={"campaign_id": campaign.id, "status": "sleeping"},
    ), db=db, user=user)

    assert result["action"]["status"] == "failed"
    assert "status" in result["action"]["error"]
    assert "[object Object]" not in result["action"]["error"]


@pytest.mark.asyncio
async def test_planner_can_update_existing_campaign_filters(db, monkeypatch):
    user = make_user(db)
    campaign = Campaign(
        id="16056a2a-bc31-4f07-b8a0-8e08d5fe060e",
        name="Existing CamHours Campaign",
        target_site="camhours.com",
    )
    db.add(campaign)
    db.commit()

    async def fake_run_claude_cli(prompt):
        assert "campaign.update" in prompt
        return (
            '{"response":"I will restrict that campaign to adult directory/topsite domains.",'
            '"action_name":"campaign.update",'
            '"action_args":{"campaign_id":"16056a2a-bc31-4f07-b8a0-8e08d5fe060e",'
            '"filter_niche_tags":"adult,directory"}}'
        )

    monkeypatch.setattr(agent_router, "_run_claude_cli", fake_run_claude_cli)

    result = await send_agent_command(AgentCommandRequest(
        message=(
            "edit campaign 16056a2a-bc31-4f07-b8a0-8e08d5fe060e "
            "so that it includes only adult directories / topsites"
        ),
    ), db=db, user=user)

    db.refresh(campaign)
    assert result["action"]["status"] == "success"
    assert result["action"]["action_name"] == "campaign.update"
    assert campaign.filter_niche_tags == "adult,directory"


@pytest.mark.asyncio
async def test_campaign_create_from_research_adds_target_urls(db):
    user = make_user(db)
    site = make_target_site(db)
    adult_directory = Domain(
        id="adult-dir-1",
        domain="adultdirectory.example",
        is_adult=True,
        domain_niche="adult",
        category="adult toplist",
        tags="adult,toplist",
        organic_traffic=1000,
    )
    adult_content_site = Domain(
        id="adult-site-1",
        domain="adultcontent.example",
        is_adult=True,
        domain_niche="adult",
        category="adult tube site",
        tags="adult",
        organic_traffic=10000,
    )
    non_adult_directory = Domain(
        id="business-dir-1",
        domain="businessdirectory.example",
        category="business directory",
        tags="directory",
        organic_traffic=5000,
    )
    db.add_all([adult_directory, adult_content_site, non_adult_directory])
    db.commit()

    _action, result = await execute_registered_action(db, user, "campaign.create_from_research", {
        "target_site_query": "CamHours",
        "name": "CamHours Adult Directories",
        "filter_niche_tags": "adult,directory",
        "limit_target_urls": 3,
    })

    campaign = db.query(Campaign).filter(Campaign.id == result.data["campaign"]["id"]).one()
    target = db.query(CampaignTarget).filter(CampaignTarget.campaign_id == campaign.id).one()
    assert campaign.target_site == "camhours.com"
    assert campaign.target_site_id == site.id
    assert campaign.filter_niche_tags == "adult,directory"
    assert target.url == "https://camhours.com/girls"
    candidate_domains = [domain["domain"] for domain in result.data["candidate_domains"]]
    assert candidate_domains == ["adultdirectory.example"]


@pytest.mark.asyncio
async def test_domain_update_handler_persists_safe_fields(db, sample_domain):
    user = make_user(db)

    action, result = await execute_registered_action(db, user, "domain.update", {
        "domain": sample_domain.domain,
        "notes": "Qualified by agent",
        "category": "adult directory",
        "tags": "adult,directory",
    })

    db.refresh(sample_domain)
    assert action.permission == "mutate"
    assert result.data["domain"]["notes"] == "Qualified by agent"
    assert sample_domain.category == "adult directory"
    assert sample_domain.tags == "adult,directory"


@pytest.mark.asyncio
async def test_contact_and_link_price_actions_upsert(db, sample_domain):
    user = make_user(db)

    await execute_registered_action(db, user, "contact.upsert", {
        "domain": sample_domain.domain,
        "email": "editor@example.com",
        "name": "Editor",
        "is_primary": True,
    })
    await execute_registered_action(db, user, "link_price.upsert", {
        "domain": sample_domain.domain,
        "link_type": "Guest Post",
        "price": 125,
        "currency": "USD",
        "is_permanent": True,
    })

    contact = db.query(Contact).filter(Contact.email == "editor@example.com").one()
    price = db.query(LinkPrice).filter(LinkPrice.domain_id == sample_domain.id).one()
    assert contact.name == "Editor"
    assert contact.is_primary is True
    assert price.link_type == "Guest Post"
    assert price.price == 125
    assert price.duration_months is None


@pytest.mark.asyncio
async def test_campaign_and_order_actions_create_operational_records(db, sample_domain):
    user = make_user(db)

    _campaign_action, campaign_result = await execute_registered_action(db, user, "campaign.create", {
        "name": "Agent Campaign",
        "target_site": "camhours.com",
        "budget": 500,
    })
    campaign_id = campaign_result.data["campaign"]["id"]

    _target_action, target_result = await execute_registered_action(db, user, "campaign.target.create", {
        "campaign_id": campaign_id,
        "url": "https://camhours.com/girls",
        "brand_name": "CamHours",
    })

    _order_action, order_result = await execute_registered_action(db, user, "order.create", {
        "campaign_id": campaign_id,
        "domain": sample_domain.domain,
        "link_type": "Guest Post",
        "price": 150,
        "target_url": "https://camhours.com/girls",
        "anchor_text": "CamHours",
    })

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).one()
    target = db.query(CampaignTarget).filter(CampaignTarget.id == target_result.data["target"]["id"]).one()
    order = db.query(Order).filter(Order.id == order_result.data["order"]["id"]).one()
    assert campaign.target_site == "camhours.com"
    assert target.brand_name == "CamHours"
    assert order.domain_id == sample_domain.id
    assert order.price == 150
    assert campaign.spent == 150


def test_registry_exposes_required_full_operator_actions():
    names = {action["name"] for action in registry.list()}
    assert {
        "campaign.create",
        "campaign.target.create",
        "order.create",
        "order.link.create",
        "contact.grab",
        "publisher_rules.grab",
        "order.generate_article",
        "order.approve_article",
        "order.send",
        "order.verify_live",
        "order.mark_payment_sent",
        "order.confirm_payment",
        "contact_form.submit",
    }.issubset(names)

    action_by_name = {action["name"]: action for action in registry.list()}
    assert action_by_name["order.send"]["requires_confirmation"] is True
    assert action_by_name["contact_form.submit"]["requires_confirmation"] is True


def test_audit_tables_persist_action_attempt(db):
    user = make_user(db)
    session = AgentSession(user_id=user.id, title="test")
    db.add(session)
    db.flush()
    audit = AgentActionAudit(
        session_id=session.id,
        user_id=user.id,
        action_name="domain.search",
        permission="read",
        status="success",
        input_json={"query": "porn"},
        result_json={"message": "ok"},
    )
    db.add(audit)
    db.commit()

    stored = db.query(AgentActionAudit).filter(AgentActionAudit.id == audit.id).one()
    assert stored.session_id == session.id
    assert stored.input_json["query"] == "porn"


@pytest.mark.asyncio
async def test_confirmation_required_action_pends_confirms_once_and_scopes_user(db, sample_order, monkeypatch):
    user = make_user(db)

    async def fake_generate_article(order_id, _db, skip_images=False):
        assert order_id == sample_order.id
        assert skip_images is False
        return {"success": True, "order_id": order_id}

    monkeypatch.setattr("backend.services.article_writer.generate_article", fake_generate_article)

    pending = await execute_action(AgentActionRequest(
        action_name="order.generate_article",
        action_args={"order_id": sample_order.id},
    ), db=db, user=user)

    action = pending["action"]
    assert action["status"] == "pending"
    assert action["requires_confirmation"] is True

    other = User(id="user-2", email="other@example.com", password_hash="x", is_active=True)
    db.add(other)
    db.commit()
    with pytest.raises(Exception):
        await confirm_action(action["id"], db=db, user=other)

    confirmed = await confirm_action(action["id"], db=db, user=user)
    assert confirmed["action"]["status"] == "success"
    assert confirmed["action"]["confirmed_at"] is not None

    with pytest.raises(Exception):
        await confirm_action(action["id"], db=db, user=user)


@pytest.mark.asyncio
async def test_high_risk_false_success_result_is_failed_and_rolled_back(db, sample_order, monkeypatch):
    user = make_user(db)
    original_content = sample_order.article_content

    async def fake_approval(_order_id, approved, modified, db):
        assert approved is True
        return {"success": False, "reason": "publisher rejected"}

    monkeypatch.setattr("backend.services.campaign_autopilot.handle_article_approval", fake_approval)

    pending = await execute_action(AgentActionRequest(
        action_name="order.approve_article",
        action_args={"order_id": sample_order.id, "article_content": "new content"},
    ), db=db, user=user)

    confirmed = await confirm_action(pending["action"]["id"], db=db, user=user)
    db.refresh(sample_order)

    assert confirmed["action"]["status"] == "failed"
    assert "publisher rejected" in confirmed["action"]["error"]
    assert sample_order.article_content == original_content


@pytest.mark.asyncio
async def test_confirm_claim_blocks_double_execution(db, sample_order, monkeypatch):
    user = make_user(db)
    pending = await execute_action(AgentActionRequest(
        action_name="order.generate_article",
        action_args={"order_id": sample_order.id},
    ), db=db, user=user)
    action_id = pending["action"]["id"]

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_generate_article(order_id, _db, skip_images=False):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"success": True, "order_id": order_id}

    monkeypatch.setattr("backend.services.article_writer.generate_article", fake_generate_article)

    SessionLocal = sessionmaker(bind=db.get_bind())
    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        first = asyncio.create_task(confirm_action(action_id, db=db1, user=user))
        await started.wait()

        with pytest.raises(Exception):
            await confirm_action(action_id, db=db2, user=user)

        release.set()
        confirmed = await first
    finally:
        db1.close()
        db2.close()

    assert calls == 1
    assert confirmed["action"]["status"] == "success"


@pytest.mark.asyncio
async def test_direct_confirm_execution_is_not_claimable_while_running(db, sample_order, monkeypatch):
    user = make_user(db)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_generate_article(order_id, _db, skip_images=False):
        started.set()
        await release.wait()
        return {"success": True, "order_id": order_id}

    monkeypatch.setattr("backend.services.article_writer.generate_article", fake_generate_article)

    SessionLocal = sessionmaker(bind=db.get_bind())
    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        running = asyncio.create_task(execute_action(AgentActionRequest(
            action_name="order.generate_article",
            action_args={"order_id": sample_order.id},
            confirm=True,
        ), db=db1, user=user))
        await started.wait()

        audit = db2.query(AgentActionAudit).filter(
            AgentActionAudit.action_name == "order.generate_article",
        ).one()
        assert audit.status == "executing"

        with pytest.raises(Exception):
            await confirm_action(audit.id, db=db2, user=user)
        with pytest.raises(Exception):
            await cancel_action(audit.id, db=db2, user=user)

        release.set()
        result = await running
    finally:
        db1.close()
        db2.close()

    assert result["action"]["status"] == "success"


@pytest.mark.asyncio
async def test_cancel_pending_action(db):
    user = make_user(db)

    pending = await execute_action(AgentActionRequest(
        action_name="order.generate_article",
        action_args={"order_id": "order-2"},
    ), db=db, user=user)
    cancelled = await cancel_action(pending["action"]["id"], db=db, user=user)

    assert cancelled["action"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_unknown_action_is_audited_as_rejected(db):
    user = make_user(db)

    result = await execute_action(AgentActionRequest(
        action_name="shell.exec",
        action_args={"command": "whoami"},
    ), db=db, user=user)

    assert result["action"]["status"] == "rejected"
    audit = db.query(AgentActionAudit).filter(AgentActionAudit.id == result["action"]["id"]).one()
    assert audit.status == "rejected"
    assert audit.action_name == "shell.exec"


@pytest.mark.asyncio
async def test_invalid_action_args_are_audited_as_failed(db, sample_domain):
    user = make_user(db)

    result = await execute_action(AgentActionRequest(
        action_name="domain.search",
        action_args={"status": "not-a-status"},
    ), db=db, user=user)

    assert result["action"]["status"] == "failed"
    audit = db.query(AgentActionAudit).filter(AgentActionAudit.id == result["action"]["id"]).one()
    assert "Invalid status" in (audit.error or "")
