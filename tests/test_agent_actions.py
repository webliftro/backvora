"""Operational agent registry and audit tests."""

import asyncio

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.models import AgentActionAudit, AgentSession, Campaign, CampaignTarget, Contact, Domain, LinkPrice, Order, User
from backend.routers.agent import AgentActionRequest, execute_action, confirm_action, cancel_action
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


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(db):
    user = make_user(db)

    with pytest.raises(Exception) as exc:
        await execute_registered_action(db, user, "git.deploy", {})

    assert "Unknown action" in str(exc.value)


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
