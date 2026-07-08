"""Authenticated operational AI agent API."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AgentActionAudit, AgentMessage, AgentSession, User
from ..services.agent_actions import ActionExecutionError, execute_registered_action, registry, require_known_action

router = APIRouter(dependencies=[Depends(get_current_user)])


class AgentCommandRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    action_name: str | None = None
    action_args: dict[str, Any] | None = None


class AgentActionRequest(BaseModel):
    session_id: str | None = None
    action_name: str
    action_args: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


def _sanitize(value: dict[str, Any]) -> dict[str, Any]:
    blocked = ("password", "token", "secret", "api_key", "authorization")
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if any(part in key.lower() for part in blocked):
            clean[key] = "[redacted]"
        elif isinstance(item, dict):
            clean[key] = _sanitize(item)
        elif isinstance(item, list):
            clean[key] = [_sanitize(v) if isinstance(v, dict) else v for v in item]
        else:
            clean[key] = item
    return clean


def _get_or_create_session(db: Session, user: User, session_id: str | None, title: str | None = None) -> AgentSession:
    if session_id:
        session = db.query(AgentSession).filter(
            AgentSession.id == session_id,
            AgentSession.user_id == user.id,
            AgentSession.deleted_at.is_(None),
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Agent session not found")
        return session
    session = AgentSession(user_id=user.id, title=title)
    db.add(session)
    db.flush()
    return session


def _message_payload(message: AgentMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "meta": message.meta or {},
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _audit_payload(audit: AgentActionAudit) -> dict[str, Any]:
    return {
        "id": audit.id,
        "session_id": audit.session_id,
        "action_name": audit.action_name,
        "permission": audit.permission,
        "requires_confirmation": audit.requires_confirmation,
        "status": audit.status,
        "input": _sanitize(audit.input_json or {}),
        "result": audit.result_json or {},
        "error": audit.error,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "confirmed_at": audit.confirmed_at.isoformat() if audit.confirmed_at else None,
    }


def _infer_action(message: str) -> tuple[str | None, dict[str, Any]]:
    """Small deterministic command parser used when no explicit action is sent.

    This keeps the server useful without making LLM output the security boundary.
    The UI can still call explicit actions, and a future LLM planner can only
    submit the same registered action names/args.
    """
    text = message.strip()
    lower = text.lower()
    if lower.startswith("search domains"):
        return "domain.search", {"query": text[len("search domains"):].strip() or None}
    if lower.startswith("find domains"):
        return "domain.search", {"query": text[len("find domains"):].strip() or None}
    if lower.startswith("show domain "):
        return "domain.detail", {"domain": text[len("show domain "):].strip().lower()}
    if lower.startswith("classify domain "):
        return "domain.classify_adult", {"domain": text[len("classify domain "):].strip().lower()}
    if lower.startswith("summarize campaign "):
        return "campaign.summary", {"query": text[len("summarize campaign "):].strip()}
    if lower.startswith("summarize order "):
        return "order.summary", {"id": text[len("summarize order "):].strip()}
    return None, {}


async def _plan_action_with_llm(message: str) -> tuple[str, dict[str, Any]]:
    api_key = settings.anthropic_api_key
    if not api_key:
        raise ActionExecutionError("Agent LLM is not configured. Set ANTHROPIC_API_KEY and AGENT_MODEL to enable free-form commands.")

    action_catalog = registry.list()
    prompt = (
        "You are BackVora's operational planner. Return ONLY compact JSON with keys "
        "`action_name` and `action_args`. Choose exactly one registered action from the catalog. "
        "Never invent actions. Never request shell/code/deploy/migration/file/env/secret access. "
        "If the user asks for a forbidden or unsupported operation, choose no action by returning "
        '{"action_name": null, "action_args": {}}.\n\n'
        f"Registered actions:\n{json.dumps(action_catalog, indent=2)}\n\n"
        f"User command:\n{message}"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.agent_model,
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if resp.status_code >= 400:
        raise ActionExecutionError(f"Agent planner failed: HTTP {resp.status_code}")
    payload = resp.json()
    text = "".join(
        part.get("text", "")
        for part in payload.get("content", [])
        if part.get("type") == "text"
    ).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ActionExecutionError("Agent planner returned invalid JSON") from exc
    action_name = parsed.get("action_name")
    action_args = parsed.get("action_args") or {}
    if not action_name:
        raise ActionExecutionError("That request is not supported by the registered BackVora actions.")
    if not isinstance(action_args, dict):
        raise ActionExecutionError("Agent planner returned invalid action_args")
    return action_name, action_args


def _persist_action_attempt(
    db: Session,
    session: AgentSession,
    user: User,
    action_name: str,
    permission: str,
    action_args: dict[str, Any],
    *,
    requires_confirmation: bool,
    status: Literal["pending", "executing", "success", "failed", "rejected", "cancelled"],
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> AgentActionAudit:
    audit = AgentActionAudit(
        session_id=session.id,
        user_id=user.id,
        action_name=action_name,
        permission=permission,
        requires_confirmation=requires_confirmation,
        status=status,
        input_json=action_args,
        result_json=result,
        error=error,
    )
    db.add(audit)
    db.flush()
    return audit


def _persist_action_result(
    db: Session,
    audit: AgentActionAudit,
    result: dict[str, Any],
) -> None:
    audit.status = "success"
    audit.result_json = result
    if audit.requires_confirmation:
        audit.confirmed_at = datetime.utcnow()


def _persist_action_failure(audit: AgentActionAudit, error: str) -> None:
    audit.status = "failed"
    audit.error = error


def _rollback_and_persist_action_failure(
    db: Session,
    audit_id: str,
    error: str,
) -> AgentActionAudit:
    db.rollback()
    audit = db.query(AgentActionAudit).filter(AgentActionAudit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=500, detail="Agent action audit row was lost during rollback")
    _persist_action_failure(audit, error)
    db.flush()
    return audit


@router.get("/actions")
async def list_agent_actions():
    return {"actions": registry.list()}


@router.get("/sessions")
async def list_agent_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = db.query(AgentSession).filter(
        AgentSession.user_id == user.id,
        AgentSession.deleted_at.is_(None),
    ).order_by(AgentSession.updated_at.desc()).limit(50).all()
    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_agent_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_or_create_session(db, user, session_id)
    messages = db.query(AgentMessage).filter(AgentMessage.session_id == session.id).order_by(AgentMessage.created_at.asc()).all()
    actions = db.query(AgentActionAudit).filter(AgentActionAudit.session_id == session.id).order_by(AgentActionAudit.created_at.desc()).all()
    return {
        "session": {"id": session.id, "title": session.title},
        "messages": [_message_payload(m) for m in messages],
        "actions": [_audit_payload(a) for a in actions],
    }


@router.post("/commands")
async def send_agent_command(
    req: AgentCommandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_or_create_session(db, user, req.session_id, title=req.message[:80])
    user_message = AgentMessage(session_id=session.id, user_id=user.id, role="user", content=req.message)
    db.add(user_message)

    action_name = req.action_name
    action_args = req.action_args or {}
    if not action_name:
        action_name, action_args = _infer_action(req.message)

    if not action_name:
        try:
            action_name, action_args = await _plan_action_with_llm(req.message)
        except ActionExecutionError as exc:
            content = (
                f"{exc} Try deterministic commands like `search domains porn`, "
                "`show domain example.com`, `classify domain example.com`, or use an explicit action."
            )
            assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=content)
            db.add(assistant)
            db.commit()
            return {"session_id": session.id, "message": _message_payload(assistant), "action": None}

    return await execute_action(AgentActionRequest(
        session_id=session.id,
        action_name=action_name,
        action_args=action_args,
    ), db=db, user=user)


@router.post("/actions")
async def execute_action(
    req: AgentActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_or_create_session(db, user, req.session_id, title=req.action_name)
    try:
        action = require_known_action(req.action_name)
    except HTTPException as exc:
        audit = _persist_action_attempt(
            db, session, user, req.action_name, "unknown", _sanitize(req.action_args),
            requires_confirmation=False, status="rejected", error=str(exc.detail),
        )
        assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=str(exc.detail), meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}

    try:
        parsed = action.validate_args(req.action_args)
        validated_args = parsed.model_dump(exclude_none=True)
    except ActionExecutionError as exc:
        audit = _persist_action_attempt(
            db, session, user, action.name, action.permission, _sanitize(req.action_args),
            requires_confirmation=action.requires_confirmation, status="failed", error=str(exc),
        )
        assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=str(exc), meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}

    if action.requires_confirmation and not req.confirm:
        audit = _persist_action_attempt(
            db, session, user, action.name, action.permission, validated_args,
            requires_confirmation=True, status="pending",
        )
        content = f"`{action.name}` requires confirmation before execution."
        assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=content, meta={"pending_action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}

    audit = _persist_action_attempt(
        db, session, user, action.name, action.permission, validated_args,
        requires_confirmation=action.requires_confirmation, status="executing",
    )
    audit_id = audit.id
    db.commit()
    try:
        audit = db.query(AgentActionAudit).filter(AgentActionAudit.id == audit_id).one()
        _action, result = await execute_registered_action(db, user, req.action_name, validated_args)
        _persist_action_result(db, audit, result.model_dump())
        assistant = AgentMessage(
            session_id=session.id,
            user_id=user.id,
            role="assistant",
            content=result.message,
            meta={"action_id": audit.id, "result": result.data},
        )
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}
    except ActionExecutionError as exc:
        audit = _rollback_and_persist_action_failure(db, audit_id, str(exc))
        assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=str(exc), meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}
    except Exception as exc:
        audit = _rollback_and_persist_action_failure(db, audit_id, f"Unexpected agent action error: {exc}")
        assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=audit.error or "Unexpected agent action error", meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": session.id, "message": _message_payload(assistant), "action": _audit_payload(audit)}


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    claimed = db.query(AgentActionAudit).filter(
        AgentActionAudit.id == action_id,
        AgentActionAudit.user_id == user.id,
        AgentActionAudit.status == "pending",
    ).update({"status": "executing"}, synchronize_session=False)
    db.commit()
    if claimed != 1:
        raise HTTPException(status_code=404, detail="Pending action not found")
    audit = db.query(AgentActionAudit).filter(
        AgentActionAudit.id == action_id,
        AgentActionAudit.user_id == user.id,
    ).first()
    if not audit:
        raise HTTPException(status_code=500, detail="Claimed action not found")
    audit_id = audit.id
    try:
        action, result = await execute_registered_action(db, user, audit.action_name, audit.input_json or {})
        _persist_action_result(db, audit, result.model_dump())
        assistant = AgentMessage(
            session_id=audit.session_id,
            user_id=user.id,
            role="assistant",
            content=result.message,
            meta={"action_id": audit.id, "result": result.data},
        )
        db.add(assistant)
        db.commit()
        return {"session_id": audit.session_id, "message": _message_payload(assistant), "action": _audit_payload(audit)}
    except ActionExecutionError as exc:
        audit = _rollback_and_persist_action_failure(db, audit_id, str(exc))
        assistant = AgentMessage(session_id=audit.session_id, user_id=user.id, role="assistant", content=str(exc), meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": audit.session_id, "message": _message_payload(assistant), "action": _audit_payload(audit)}
    except Exception as exc:
        audit = _rollback_and_persist_action_failure(db, audit_id, f"Unexpected agent action error: {exc}")
        assistant = AgentMessage(session_id=audit.session_id, user_id=user.id, role="assistant", content=audit.error or "Unexpected agent action error", meta={"action_id": audit.id})
        db.add(assistant)
        db.commit()
        return {"session_id": audit.session_id, "message": _message_payload(assistant), "action": _audit_payload(audit)}


@router.post("/actions/{action_id}/cancel")
async def cancel_action(
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cancelled = db.query(AgentActionAudit).filter(
        AgentActionAudit.id == action_id,
        AgentActionAudit.user_id == user.id,
        AgentActionAudit.status == "pending",
    ).update({"status": "cancelled"}, synchronize_session=False)
    db.commit()
    if cancelled != 1:
        raise HTTPException(status_code=404, detail="Pending action not found")
    audit = db.query(AgentActionAudit).filter(
        AgentActionAudit.id == action_id,
        AgentActionAudit.user_id == user.id,
    ).first()
    if not audit:
        raise HTTPException(status_code=500, detail="Cancelled action not found")
    return {"success": True, "action": _audit_payload(audit)}
