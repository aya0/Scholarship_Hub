"""
scraper/pipeline.py
-------------------
Orchestrates the full scrape → dedup → normalize → queue cycle.

Flow:
  1. Run scraper for a given source
  2. For each result, compute content_hash
  3. Skip if hash already exists in scrape_results (dedup)
  4. Call AI normalizer to clean the data
  5. Save to scrape_results with status=PENDING
  6. Notify admins of new items in queue
"""

import asyncio
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from db.models import ScrapeResult, ScrapeSource, ScrapeStatus
from scraper.scrapers import SCRAPER_REGISTRY, RawScholarship
from scraper.normalizer import AIScholarshipNormalizer


class ScrapePipeline:
    def __init__(self, db: Session):
        self.db         = db
        self.normalizer = AIScholarshipNormalizer()

    # ── Run a single source ──────────────────────────────────────────────

    async def run_source(self, scraper_key: str) -> dict:
        """
        Scrape one source end-to-end.
        Returns a summary dict: {found, new, skipped, errors}
        """
        if scraper_key not in SCRAPER_REGISTRY:
            raise ValueError(f"Unknown scraper key: {scraper_key}")

        scraper     = SCRAPER_REGISTRY[scraper_key]()
        stats       = {"found": 0, "new": 0, "skipped_dedup": 0, "errors": 0}
        source_rec  = self._get_source_record(scraper_key)

        logger.info(f"[pipeline] Starting source: {scraper_key}")

        try:
            raw_items: list[RawScholarship] = await scraper.scrape()
            stats["found"] = len(raw_items)

            for raw in raw_items:
                try:
                    await self._process_item(raw, stats)
                except Exception as e:
                    logger.error(f"[pipeline] Error processing item '{raw.title}': {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"[pipeline] Source {scraper_key} failed: {e}")
            stats["errors"] += 1

        # Update last_scraped timestamp
        if source_rec:
            source_rec.last_scraped = datetime.utcnow()
            source_rec.total_found += stats["found"]
            self.db.commit()

        logger.info(f"[pipeline] {scraper_key} done — {stats}")
        return stats

    # ── Run all active sources ───────────────────────────────────────────

    async def run_all(self) -> dict:
        """Run every active scraper sequentially."""
        all_stats = {}
        active_sources = (
            self.db.query(ScrapeSource)
            .filter(ScrapeSource.is_active == True)
            .all()
        )
        logger.info(f"[pipeline] Running {len(active_sources)} active sources")
        for source in active_sources:
            stats = await self.run_source(source.scraper_key)
            all_stats[source.scraper_key] = stats
            # Polite delay between sources
            await asyncio.sleep(3)
        return all_stats

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _process_item(self, raw: RawScholarship, stats: dict):
        content_hash = raw.content_hash()

        # Dedup check
        exists = (
            self.db.query(ScrapeResult)
            .filter(ScrapeResult.content_hash == content_hash)
            .first()
        )
        if exists:
            logger.debug(f"[pipeline] Duplicate skipped: {raw.title[:60]}")
            stats["skipped_dedup"] += 1
            return

        # Normalize via AI
        normalized = await self.normalizer.normalize(raw)

        # Persist to scrape_results
        record = ScrapeResult(
            source_name  = raw.source_name,
            source_url   = raw.source_url,
            raw_html     = raw.raw_html[:10000] if raw.raw_html else "",
            extracted    = raw.to_dict(),
            normalized   = normalized,
            status       = ScrapeStatus.PENDING,
            content_hash = content_hash,
        )
        self.db.add(record)
        self.db.commit()
        stats["new"] += 1
        logger.info(f"[pipeline] Queued for review: '{raw.title[:60]}' "
                    f"from {raw.source_name}")

    def _get_source_record(self, scraper_key: str) -> ScrapeSource | None:
        return (
            self.db.query(ScrapeSource)
            .filter(ScrapeSource.scraper_key == scraper_key)
            .first()
        )

    # ── Queue stats ──────────────────────────────────────────────────────

    def queue_summary(self) -> dict:
        """Return counts by status for the admin dashboard."""
        from sqlalchemy import func as sqlfunc
        rows = (
            self.db.query(ScrapeResult.status, sqlfunc.count())
            .group_by(ScrapeResult.status)
            .all()
        )
        return {str(status): count for status, count in rows}
