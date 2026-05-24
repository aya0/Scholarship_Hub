"""
admin_api/routes.py
-------------------
FastAPI routes for the admin review queue.

Key principle: scraped items NEVER become live scholarships
until an admin explicitly calls POST /admin/review/{id}/approve.

Endpoints:
  GET  /admin/queue               — list pending scraped items
  GET  /admin/queue/{id}          — full detail of one item
  POST /admin/review/{id}/approve — approve → creates Scholarship record
  POST /admin/review/{id}/reject  — reject with reason
  POST /admin/review/{id}/duplicate — mark as duplicate of existing scholarship
  GET  /admin/stats               — queue counts + scraper health
  POST /admin/scrape/trigger      — manually trigger a scraper
  GET  /admin/scholarships        — list all live curated scholarships
  POST /admin/scholarships        — manually add a scholarship
  PUT  /admin/scholarships/{id}   — edit a live scholarship
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import (
    ScrapeResult, ScrapeStatus, Scholarship, ScholarshipStatus,
    ScholarshipType, ScrapeSource
)
from scraper.pipeline import ScrapePipeline
from python_slugify import slugify

router = APIRouter(prefix="/admin", tags=["admin"])


# ─────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────

class ApprovePayload(BaseModel):
    """Admin can edit normalized fields before approving."""
    title:             str
    type:              ScholarshipType
    country:           Optional[str]    = None
    funder:            Optional[str]    = None
    description:       Optional[str]    = None
    eligibility:       Optional[str]    = None
    application_steps: Optional[str]    = None
    open_date:         Optional[date]   = None
    close_date:        Optional[date]   = None
    degree_levels:     Optional[list]   = None
    fields:            Optional[list]   = None
    language_req:      Optional[str]    = None
    min_gpa:           Optional[float]  = None
    funding_amount:    Optional[str]    = None
    application_url:   Optional[str]    = None
    source_url:        Optional[str]    = None
    acceptance_rate:   Optional[float]  = None

class RejectPayload(BaseModel):
    reason: str = Field(..., min_length=3)

class DuplicatePayload(BaseModel):
    existing_scholarship_id: str

class ManualScholarshipPayload(ApprovePayload):
    """For manually adding a scholarship (no scrape record)."""
    pass

class TriggerScrapePayload(BaseModel):
    scraper_key: str


# ─────────────────────────────────────────────
# Review queue
# ─────────────────────────────────────────────

@router.get("/queue")
def list_queue(
    status: ScrapeStatus = ScrapeStatus.PENDING,
    source: Optional[str] = None,
    limit:  int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List scraped items waiting for admin review."""
    q = db.query(ScrapeResult).filter(ScrapeResult.status == status)
    if source:
        q = q.filter(ScrapeResult.source_name == source)
    total  = q.count()
    items  = q.order_by(ScrapeResult.scraped_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id":          str(item.id),
                "source":      item.source_name,
                "url":         item.source_url,
                "title":       item.normalized.get("title", "(no title)") if item.normalized else "",
                "country":     item.normalized.get("country") if item.normalized else "",
                "type":        item.normalized.get("type") if item.normalized else "",
                "close_date":  item.normalized.get("close_date") if item.normalized else "",
                "confidence":  item.normalized.get("confidence", 0) if item.normalized else 0,
                "scraped_at":  item.scraped_at.isoformat() if item.scraped_at else "",
                "status":      item.status,
            }
            for item in items
        ]
    }


@router.get("/queue/{item_id}")
def get_queue_item(item_id: str, db: Session = Depends(get_db)):
    """Full detail of a single scraped item, including raw HTML."""
    item = db.query(ScrapeResult).filter(ScrapeResult.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "id":          str(item.id),
        "source_name": item.source_name,
        "source_url":  item.source_url,
        "extracted":   item.extracted,
        "normalized":  item.normalized,
        "status":      item.status,
        "scraped_at":  item.scraped_at.isoformat() if item.scraped_at else "",
        "raw_html_preview": (item.raw_html or "")[:500],
    }


# ─────────────────────────────────────────────
# Approve → publish as live scholarship
# ─────────────────────────────────────────────

@router.post("/review/{item_id}/approve")
def approve_item(
    item_id: str,
    payload: ApprovePayload,
    db: Session = Depends(get_db)
):
    """
    Admin reviews, edits if needed, and approves.
    Creates a Scholarship record and marks the scrape_result as approved.
    This is the ONLY path from scrape_result → live scholarship.
    """
    item = db.query(ScrapeResult).filter(ScrapeResult.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.status != ScrapeStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Item is already {item.status}")

    # Build the slug
    base_slug = slugify(payload.title)
    slug = base_slug
    counter = 1
    while db.query(Scholarship).filter(Scholarship.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Create live scholarship
    scholarship = Scholarship(
        title             = payload.title,
        slug              = slug,
        type              = payload.type,
        country           = payload.country,
        funder            = payload.funder,
        description       = payload.description,
        eligibility       = payload.eligibility,
        application_steps = payload.application_steps,
        open_date         = payload.open_date,
        close_date        = payload.close_date,
        degree_levels     = payload.degree_levels or [],
        fields            = payload.fields or [],
        language_req      = payload.language_req,
        min_gpa           = payload.min_gpa,
        funding_amount    = payload.funding_amount,
        application_url   = payload.application_url,
        source_url        = payload.source_url or item.source_url,
        acceptance_rate   = payload.acceptance_rate,
        status            = ScholarshipStatus.OPEN,
        is_active         = True,
    )
    db.add(scholarship)
    db.flush()   # get scholarship.id before commit

    # Mark scrape record as approved and link it
    item.status        = ScrapeStatus.APPROVED
    item.reviewed_at   = datetime.utcnow()
    item.scholarship_id = str(scholarship.id)

    db.commit()
    return {
        "message":        "Scholarship approved and published",
        "scholarship_id": str(scholarship.id),
        "slug":           slug,
    }


# ─────────────────────────────────────────────
# Reject
# ─────────────────────────────────────────────

@router.post("/review/{item_id}/reject")
def reject_item(
    item_id: str,
    payload: RejectPayload,
    db: Session = Depends(get_db)
):
    item = db.query(ScrapeResult).filter(ScrapeResult.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status      = ScrapeStatus.REJECTED
    item.admin_notes = payload.reason
    item.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Item rejected", "reason": payload.reason}


# ─────────────────────────────────────────────
# Mark as duplicate
# ─────────────────────────────────────────────

@router.post("/review/{item_id}/duplicate")
def mark_duplicate(
    item_id: str,
    payload: DuplicatePayload,
    db: Session = Depends(get_db)
):
    item = db.query(ScrapeResult).filter(ScrapeResult.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status       = ScrapeStatus.DUPLICATE
    item.duplicate_of = payload.existing_scholarship_id
    item.reviewed_at  = datetime.utcnow()
    db.commit()
    return {"message": "Marked as duplicate"}


# ─────────────────────────────────────────────
# Admin stats dashboard
# ─────────────────────────────────────────────

@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)):
    """Queue counts, source health, and live scholarship totals."""
    from sqlalchemy import func

    queue_counts = dict(
        db.query(ScrapeResult.status, func.count())
        .group_by(ScrapeResult.status)
        .all()
    )
    sources = db.query(ScrapeSource).all()
    live_total = db.query(Scholarship).filter(Scholarship.is_active == True).count()

    return {
        "queue": {
            "pending":   queue_counts.get(ScrapeStatus.PENDING, 0),
            "approved":  queue_counts.get(ScrapeStatus.APPROVED, 0),
            "rejected":  queue_counts.get(ScrapeStatus.REJECTED, 0),
            "duplicate": queue_counts.get(ScrapeStatus.DUPLICATE, 0),
        },
        "live_scholarships": live_total,
        "sources": [
            {
                "name":          s.name,
                "scraper_key":   s.scraper_key,
                "is_active":     s.is_active,
                "last_scraped":  s.last_scraped.isoformat() if s.last_scraped else None,
                "total_found":   s.total_found,
                "total_approved": s.total_approved,
            }
            for s in sources
        ],
    }


# ─────────────────────────────────────────────
# Manual trigger a scraper
# ─────────────────────────────────────────────

@router.post("/scrape/trigger")
async def trigger_scrape(
    payload: TriggerScrapePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger a scraper immediately (runs in background)."""
    async def run():
        pipeline = ScrapePipeline(db)
        await pipeline.run_source(payload.scraper_key)

    background_tasks.add_task(run)
    return {"message": f"Scraper '{payload.scraper_key}' triggered in background"}


# ─────────────────────────────────────────────
# Manual scholarship management (no scrape)
# ─────────────────────────────────────────────

@router.get("/scholarships")
def list_scholarships(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    q = db.query(Scholarship).filter(Scholarship.is_active == True)
    if status:
        q = q.filter(Scholarship.status == status)
    total = q.count()
    items = q.order_by(Scholarship.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id":         str(s.id),
                "title":      s.title,
                "slug":       s.slug,
                "type":       s.type,
                "country":    s.country,
                "funder":     s.funder,
                "close_date": str(s.close_date) if s.close_date else None,
                "status":     s.status,
            }
            for s in items
        ]
    }


@router.post("/scholarships", status_code=201)
def create_scholarship_manual(
    payload: ManualScholarshipPayload,
    db: Session = Depends(get_db)
):
    """Manually add a scholarship without going through the scrape queue."""
    base_slug = slugify(payload.title)
    slug = base_slug
    counter = 1
    while db.query(Scholarship).filter(Scholarship.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    scholarship = Scholarship(
        title             = payload.title,
        slug              = slug,
        type              = payload.type,
        country           = payload.country,
        funder            = payload.funder,
        description       = payload.description,
        eligibility       = payload.eligibility,
        application_steps = payload.application_steps,
        open_date         = payload.open_date,
        close_date        = payload.close_date,
        degree_levels     = payload.degree_levels or [],
        fields            = payload.fields or [],
        language_req      = payload.language_req,
        min_gpa           = payload.min_gpa,
        funding_amount    = payload.funding_amount,
        application_url   = payload.application_url,
        source_url        = payload.source_url,
        acceptance_rate   = payload.acceptance_rate,
        status            = ScholarshipStatus.OPEN,
        is_active         = True,
    )
    db.add(scholarship)
    db.commit()
    return {"message": "Scholarship created", "id": str(scholarship.id), "slug": slug}


@router.put("/scholarships/{scholarship_id}")
def update_scholarship(
    scholarship_id: str,
    payload: ManualScholarshipPayload,
    db: Session = Depends(get_db)
):
    s = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    for field_name, value in payload.model_dump(exclude_none=True).items():
        setattr(s, field_name, value)
    db.commit()
    return {"message": "Scholarship updated", "id": scholarship_id}
