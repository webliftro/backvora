"""Authenticated operational AI agent API."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import re
from typing import Any, Literal, NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AgentActionAudit, AgentMessage, AgentSession, AnchorText, TargetSite, TargetURL, User
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


class AgentPlan(NamedTuple):
    action_name: str | None
    action_args: dict[str, Any]
    response: str | None = None


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


def _planner_action_catalog() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in registry.list():
        action = registry.get(item["name"])
        actions.append({
            **item,
            "args_schema": action.args_model.model_json_schema(),
        })
    return actions


def _normalize_site_query(value: str) -> str:
    text = value.strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.split("/", 1)[0].strip()


def _target_site_aliases(site: TargetSite) -> set[str]:
    domain = _normalize_site_query(site.domain)
    aliases = {
        site.name.lower(),
        domain,
        domain.split(".", 1)[0],
    }
    aliases.update(v.strip().lower() for v in (site.brand_variations or "").split(",") if v.strip())
    return aliases


def _alias_matches_text(alias: str, text: str) -> bool:
    normalized = alias.strip().lower()
    if not normalized:
        return False
    if "." not in normalized and " " not in normalized and len(normalized) < 4:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None


def _find_target_site(db: Session, message: str, explicit_query: str | None = None) -> TargetSite | None:
    query = _normalize_site_query(explicit_query or message)
    sites = db.query(TargetSite).filter(TargetSite.deleted_at.is_(None)).order_by(TargetSite.name.asc()).all()
    if explicit_query:
        for site in sites:
            aliases = _target_site_aliases(site)
            if query in aliases or any(query == _normalize_site_query(alias) for alias in aliases):
                return site
    lower_message = message.lower()
    matches = [
        site
        for site in sites
        if any(_alias_matches_text(alias, lower_message) for alias in _target_site_aliases(site))
    ]
    return matches[0] if len(matches) == 1 else None


def _planner_target_site_catalog(db: Session) -> list[dict[str, Any]]:
    sites = db.query(TargetSite).filter(TargetSite.deleted_at.is_(None)).order_by(TargetSite.name.asc()).limit(25).all()
    catalog: list[dict[str, Any]] = []
    for site in sites:
        urls = db.query(TargetURL).filter(
            TargetURL.site_id == site.id,
            TargetURL.deleted_at.is_(None),
        ).order_by(TargetURL.priority.desc()).limit(8).all()
        catalog.append({
            "id": site.id,
            "name": site.name,
            "domain": site.domain,
            "brand_variations": site.brand_variations,
            "urls": [
                {
                    "id": url.id,
                    "url": url.url,
                    "description": url.description,
                    "priority": url.priority,
                    "anchors": [
                        {"text": anchor.text, "anchor_type": anchor.anchor_type}
                        for anchor in db.query(AnchorText).filter(
                            AnchorText.target_url_id == url.id,
                            AnchorText.deleted_at.is_(None),
                        ).order_by(AnchorText.times_used.asc()).limit(5).all()
                    ],
                }
                for url in urls
            ],
        })
    return catalog


def _enrich_planned_action_args(
    db: Session,
    message: str,
    action_name: str,
    action_args: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(action_args)
    if action_name == "campaign.create":
        if not enriched.get("target_site") and not enriched.get("target_site_id"):
            site = _find_target_site(db, message)
            if site:
                enriched["target_site"] = site.domain
                enriched["target_site_id"] = site.id
        return enriched
    if action_name in {"campaign.research", "campaign.create_from_research"}:
        if not enriched.get("target_site_query"):
            site = _find_target_site(db, message)
            if site:
                enriched["target_site_query"] = site.name
    return enriched


def _parse_planner_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            fenced = "\n".join(lines[1:-1]).strip()
            try:
                parsed = json.loads(fenced)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    start = stripped.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(stripped)):
            char = stripped[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start:index + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
        start = stripped.find("{", start + 1)

    raise ActionExecutionError("Agent planner returned invalid JSON")


def _build_planner_prompt(message: str, db: Session) -> str:
    action_catalog = _planner_action_catalog()
    target_site_catalog = _planner_target_site_catalog(db)
    return (
        "You are BackVora's operational agent. Return ONLY compact JSON with keys "
        "`response`, `action_name`, and `action_args`. You may chat freely in `response` "
        "when no action is needed, when you need clarification, or when you are explaining "
        "what you are about to do. Choose at most one registered action from the catalog. "
        "Never invent actions. Never request shell/code/deploy/migration/file/env/secret access. "
        "If the user asks for code changes, deployment, migrations, filesystem access, secrets, "
        "or infrastructure work, set `action_name` to null and briefly explain the boundary in "
        "`response`. Do not wrap the JSON in Markdown fences.\n\n"
        "When the user names a known target brand or site, use the matching target site from context. "
        "For broad requests to create a researched campaign, prefer `campaign.create_from_research` over "
        "`campaign.create` so the campaign is tied to the known target site and target URLs. "
        "In BackVora, adult directories means adult toplist/aggregator/directory domains, "
        "not general adult content sites. For campaign requests limited to adult directories, "
        "set `filter_niche_tags` to `adult,directory`; the backend treats those as required "
        "concepts. Only set `mode` to `auto` when the user explicitly asks for automation.\n\n"
        f"Known target sites:\n{json.dumps(target_site_catalog, indent=2)}\n\n"
        f"Registered actions:\n{json.dumps(action_catalog, indent=2)}\n\n"
        f"User command:\n{message}"
    )


async def _run_claude_cli(prompt: str) -> str:
    cli_path = settings.agent_claude_cli_path
    if not cli_path:
        raise ActionExecutionError("Agent Claude CLI is not configured. Set AGENT_CLAUDE_CLI_PATH.")

    env = {
        "HOME": os.environ.get("HOME", "/home/slither"),
        "PATH": os.environ.get("PATH", "/home/slither/.local/bin:/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
    }
    proc = await asyncio.create_subprocess_exec(
        cli_path,
        "-p",
        "--model",
        settings.agent_model,
        "--permission-mode",
        "dontAsk",
        "--tools",
        "",
        "--safe-mode",
        "--no-session-persistence",
        "--output-format",
        "text",
        cwd=settings.agent_claude_cli_cwd or None,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=settings.agent_claude_cli_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise ActionExecutionError("Agent planner timed out") from exc

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise ActionExecutionError(f"Agent planner failed via Claude CLI: {err or f'exit {proc.returncode}'}")
    return stdout.decode("utf-8", errors="replace").strip()


async def _plan_action_with_llm(message: str, db: Session) -> AgentPlan:
    text = await _run_claude_cli(_build_planner_prompt(message, db))
    parsed = _parse_planner_json(text)
    action_name = parsed.get("action_name")
    action_args = parsed.get("action_args") or {}
    if not isinstance(action_args, dict):
        raise ActionExecutionError("Agent planner returned invalid action_args")
    response = parsed.get("response")
    if response is not None and not isinstance(response, str):
        raise ActionExecutionError("Agent planner returned invalid response")
    if not action_name:
        return AgentPlan(None, {}, response or "I can help with BackVora operations, but I need a clearer operational request.")
    action_args = _enrich_planned_action_args(db, message, action_name, action_args)
    return AgentPlan(str(action_name), action_args, response)


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
            plan = await _plan_action_with_llm(req.message, db)
        except ActionExecutionError as exc:
            content = (
                f"{exc} Try deterministic commands like `search domains porn`, "
                "`show domain example.com`, `classify domain example.com`, or use an explicit action."
            )
            assistant = AgentMessage(session_id=session.id, user_id=user.id, role="assistant", content=content)
            db.add(assistant)
            db.commit()
            return {"session_id": session.id, "message": _message_payload(assistant), "action": None}
        if isinstance(plan, tuple) and not isinstance(plan, AgentPlan):
            action_name, action_args = plan
            response = None
        else:
            action_name, action_args, response = plan
        if not action_name:
            assistant = AgentMessage(
                session_id=session.id,
                user_id=user.id,
                role="assistant",
                content=response or "I can help with BackVora operations, but I need a clearer request.",
            )
            db.add(assistant)
            db.commit()
            return {"session_id": session.id, "message": _message_payload(assistant), "action": None}

    action_args = _enrich_planned_action_args(db, req.message, action_name, action_args)
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
