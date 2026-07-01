"""
Link Builder - FastAPI Application Entry Point
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse

from typing import Optional
from pydantic import BaseModel

from .config import settings
from .database import init_db
from .models import Order, Campaign

# Import routers
from .routers import domains, contacts, outreach, backlinks, import_export, link_prices, auth, inbox, campaigns, target_sites, orders
from .auth import get_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    init_db()
    from .services.scheduler import init_scheduler, shutdown_scheduler
    await init_scheduler()
    print(f"🚀 {settings.app_name} started in {settings.app_env} mode")
    yield
    # Shutdown
    await shutdown_scheduler()
    print(f"👋 {settings.app_name} shutting down")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Link building outreach tool for SEO",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# Templates
templates = Jinja2Templates(directory="frontend/templates")

# Include API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(domains.router, prefix="/api/v1/domains", tags=["Domains"], dependencies=[Depends(get_current_user)])
app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["Contacts"], dependencies=[Depends(get_current_user)])
app.include_router(backlinks.router, prefix="/api/v1/backlinks", tags=["Backlinks"], dependencies=[Depends(get_current_user)])
app.include_router(outreach.router, prefix="/api/v1/outreach", tags=["Outreach"], dependencies=[Depends(get_current_user)])
app.include_router(import_export.router, prefix="/api/v1/import", tags=["Import/Export"], dependencies=[Depends(get_current_user)])
app.include_router(link_prices.router, prefix="/api/v1/link-prices", tags=["Link Prices"], dependencies=[Depends(get_current_user)])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["Inbox"], dependencies=[Depends(get_current_user)])
app.include_router(campaigns.router, prefix="/api/v1/campaigns", tags=["Campaigns"], dependencies=[Depends(get_current_user)])
app.include_router(target_sites.router, prefix="/api/v1/target-sites", tags=["Target Sites"], dependencies=[Depends(get_current_user)])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"], dependencies=[Depends(get_current_user)])


# ============ Frontend Routes (Jinja2 - disabled, using React SPA) ============
# Old Jinja2 template routes kept for reference but disabled.
# React SPA catch-all below handles all frontend routing.


# ============ Internal/Automation Endpoints (no auth) ============

from .database import get_db
from sqlalchemy.orm import Session

@app.post("/api/v1/internal/domains/batch-analyze")
async def internal_batch_analyze(
    limit: int = 10,
    max_age_days: int = 7,
    db: Session = Depends(get_db),
):
    """Batch analyze domains - no auth, for cron/automation use."""
    from .routers.domains import batch_analyze_domains
    return await batch_analyze_domains(limit=limit, max_age_days=max_age_days, db=db)


class GenerateArticleRequest(BaseModel):
    nofollow_target: Optional[bool] = None
    nofollow_resources: Optional[bool] = None
    skip_resource_links: Optional[bool] = None
    max_words: Optional[int] = None
    resource_links_count: Optional[int] = None
    brand_mentions_scope: Optional[str] = None
    brand_mentions_brands: Optional[str] = None
    brand_mentions_in_title: Optional[bool] = None
    brand_mentions_body_count: Optional[int] = None

@app.post("/api/v1/internal/orders/{order_id}/generate-article")
async def internal_generate_article(
    order_id: str,
    body: Optional[GenerateArticleRequest] = None,
    db: Session = Depends(get_db),
):
    """Generate article for an order - no auth, for internal/automation use."""
    from .services.article_writer import generate_article
    from .models import Order as _Order
    try:
        # Update nofollow settings on the order if provided
        if body:
            order = db.query(_Order).filter(_Order.id == order_id).first()
            if order:
                if body.nofollow_target is not None:
                    order.nofollow_target = body.nofollow_target
                if body.nofollow_resources is not None:
                    order.nofollow_resources = body.nofollow_resources
                if body.skip_resource_links is not None:
                    order.skip_resource_links = body.skip_resource_links
                if body.max_words is not None:
                    order.max_words = body.max_words
                if body.resource_links_count is not None:
                    order.resource_links_count = body.resource_links_count
                if body.brand_mentions_scope is not None:
                    order.brand_mentions_scope = body.brand_mentions_scope
                if body.brand_mentions_brands is not None:
                    order.brand_mentions_brands = body.brand_mentions_brands
                if body.brand_mentions_in_title is not None:
                    order.brand_mentions_in_title = body.brand_mentions_in_title
                if body.brand_mentions_body_count is not None:
                    order.brand_mentions_body_count = body.brand_mentions_body_count
                db.commit()
        result = await generate_article(order_id, db)
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/internal/orders/{order_id}/send")
async def internal_send_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    """Send order to publisher - no auth, for internal/automation use."""
    from .services.order_sender import send_order
    try:
        result = await send_order(order_id, db)
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/internal/orders/{order_id}/verify-live")
async def internal_verify_live(
    order_id: str,
    url: str,
    db: Session = Depends(get_db),
):
    """Verify a submitted live URL for an order - checks domain + backlink presence."""
    from .services.link_monitor import verify_live_url
    try:
        result = await verify_live_url(order_id, url, db, auto_update_status=True)
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/internal/orders/{order_id}/mark-payment-sent")
async def internal_mark_payment_sent(order_id: str, db: Session = Depends(get_db)):
    """Mark payment as sent for an order - no auth."""
    from .routers.orders import mark_payment_sent
    return await mark_payment_sent(order_id, db=db)


@app.post("/api/v1/internal/orders/{order_id}/confirm-payment")
async def internal_confirm_payment(order_id: str, db: Session = Depends(get_db)):
    """Confirm payment for an order - no auth."""
    from .routers.orders import confirm_payment
    return await confirm_payment(order_id, db=db)


@app.post("/api/v1/internal/orders/{order_id}/approve")
async def internal_approve_order(order_id: str, db: Session = Depends(get_db)):
    """Approve article - no auth, for Slack click-through."""
    from .services.campaign_autopilot import handle_article_approval
    return await handle_article_approval(order_id, approved=True, modified=False, db=db)


@app.post("/api/v1/internal/orders/{order_id}/reject")
async def internal_reject_order(order_id: str, db: Session = Depends(get_db)):
    """Reject article - no auth, for Slack click-through."""
    from .services.campaign_autopilot import handle_article_approval
    return await handle_article_approval(order_id, approved=False, modified=False, db=db)


@app.post("/api/v1/internal/campaigns/{campaign_id}/run-cycle")
async def internal_run_cycle(campaign_id: str, db: Session = Depends(get_db)):
    """Run one autopilot cycle - no auth."""
    from .services.campaign_autopilot import run_campaign_cycle
    return await run_campaign_cycle(campaign_id, db)


@app.post("/api/v1/internal/campaigns/run-all-auto")
async def internal_run_all_auto(db: Session = Depends(get_db)):
    """Check all auto campaigns - no auth."""
    from .services.campaign_autopilot import run_campaign_cycle
    campaigns = db.query(Campaign).filter(
        Campaign.mode == "auto",
        Campaign.status == "active",
        Campaign.schedule_enabled == True,
        Campaign.deleted_at.is_(None),
    ).all()
    results = []
    for c in campaigns:
        result = await run_campaign_cycle(c.id, db)
        results.append({"campaign_id": c.id, "name": c.name, **result})
    return {"campaigns_checked": len(campaigns), "results": results}


@app.post("/api/v1/internal/campaigns/auto-check")
async def internal_auto_check(db: Session = Depends(get_db)):
    """Cron-friendly auto-check for all auto campaigns."""
    from .services.campaign_autopilot import run_campaign_cycle
    campaigns = db.query(Campaign).filter(
        Campaign.mode == "auto",
        Campaign.status == "active",
        Campaign.schedule_enabled == True,
        Campaign.deleted_at.is_(None),
    ).all()
    results = []
    for c in campaigns:
        try:
            result = await run_campaign_cycle(c.id, db)
            results.append({"campaign_id": c.id, "name": c.name, **result})
        except Exception as e:
            results.append({"campaign_id": c.id, "name": c.name, "error": str(e)})
    return {"campaigns_checked": len(campaigns), "results": results}


@app.get("/api/v1/internal/scheduler/status")
async def internal_scheduler_status():
    """Get scheduler status - no auth."""
    from .services.scheduler import get_scheduler, get_scheduled_jobs
    scheduler = get_scheduler()
    return {
        "running": scheduler is not None and scheduler.running if scheduler else False,
        "jobs": get_scheduled_jobs(),
    }


@app.post("/api/v1/internal/scheduler/reload")
async def internal_scheduler_reload():
    """Force reload all scheduler jobs from DB - no auth."""
    from .services.scheduler import reload_campaign_jobs
    await reload_campaign_jobs()
    from .services.scheduler import get_scheduled_jobs
    return {"reloaded": True, "jobs": get_scheduled_jobs()}


@app.post("/api/v1/internal/orders/check-links")
async def internal_check_links(db: Session = Depends(get_db)):
    """Monthly health check - no auth, for cron/automation."""
    from .services.link_monitor import check_all_live_links
    return await check_all_live_links(db)


@app.post("/api/v1/internal/campaigns/{campaign_id}/process-drafts")
async def internal_process_drafts(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Process all draft orders in a campaign: generate articles and send to publishers."""
    from .services.article_writer import generate_article
    from .services.order_sender import send_order
    
    # Get all draft orders for this campaign
    orders = db.query(Order).filter(
        Order.campaign_id == campaign_id,
        Order.status == "draft"
    ).all()
    
    results = {
        "total": len(orders),
        "articles_generated": 0,
        "emails_sent": 0,
        "errors": []
    }
    
    for order in orders:
        try:
            # Generate article
            await generate_article(order.id, db)
            results["articles_generated"] += 1
            
            # Send to publisher
            await send_order(order.id, db)
            results["emails_sent"] += 1
            
        except Exception as e:
            results["errors"].append({
                "order_id": order.id,
                "domain": order.domain.domain if order.domain else "unknown",
                "error": str(e)
            })
    
    return results


# ============ Image Serving (public, no auth) ============

from pathlib import Path as PathlibPath

@app.get("/api/v1/images/{order_id}/{filename}")
async def serve_image(order_id: str, filename: str):
    """Serve generated article images - public endpoint, no auth required."""
    image_path = PathlibPath(f"data/images/{order_id}/{filename}")
    
    if not image_path.exists() or not image_path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Security: ensure path is within data/images
    try:
        image_path.resolve().relative_to(PathlibPath("data/images").resolve())
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    
    # No-cache headers to prevent stale images after regeneration
    import os
    mtime = str(int(os.path.getmtime(image_path)))
    return FileResponse(
        str(image_path),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": mtime,
        },
    )


# ============ Health Check ============

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "app": settings.app_name}


# ============ React Frontend (SPA) ============

REACT_DIST = Path(__file__).resolve().parent.parent / "frontend-react" / "dist"

if REACT_DIST.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST / "assets")), name="react-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_react(request: Request, full_path: str):
        """Catch-all: serve React SPA index.html for client-side routing."""
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return HTMLResponse(status_code=404, content="Not found")
        # Serve static files if they exist
        file_path = REACT_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html for SPA routing
        return FileResponse(str(REACT_DIST / "index.html"))
