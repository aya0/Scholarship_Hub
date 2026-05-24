"""
main.py
-------
FastAPI application entry point.
Starts the APScheduler on startup and mounts all routers.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from admin_api.routes import router as admin_router
from scheduler.jobs import create_scheduler


scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on startup, shut it down on exit."""
    logger.info("Starting scholarship pipeline scheduler...")
    scheduler.start()
    logger.info(f"Scheduler running — {len(scheduler.get_jobs())} jobs registered")
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(
    title="Palestinian Scholarship Hub — Pipeline API",
    description="Hybrid scraper + admin review pipeline for scholarship data",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(admin_router)


@app.get("/health")
def health():
    jobs = [
        {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
        for job in scheduler.get_jobs()
    ]
    return {"status": "ok", "scheduled_jobs": jobs}


@app.get("/")
def root():
    return {
        "service": "Scholarship Pipeline API",
        "docs":    "/docs",
        "health":  "/health",
        "queue":   "/admin/queue",
        "stats":   "/admin/stats",
    }
