"""
db/session.py — SQLAlchemy session factory
db/seed.py    — Seed the scrape_sources table with all 10 sources
"""

# ─── session.py ───────────────────────────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/scholarship_hub")

engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── seed.py ──────────────────────────────────────────────────────────────────
SOURCES_SEED = [
    {
        "name":         "DAAD — German Academic Exchange",
        "base_url":     "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/",
        "scraper_key":  "daad",
        "interval_hrs": 24,
        "notes":        "Major German scholarship funder. Scrape daily."
    },
    {
        "name":         "Chevening — UK Government",
        "base_url":     "https://www.chevening.org/scholarships/",
        "scraper_key":  "chevening",
        "interval_hrs": 48,
        "notes":        "Single flagship scholarship. Check every 2 days for deadline changes."
    },
    {
        "name":         "Erasmus+ — European Commission",
        "base_url":     "https://erasmus-plus.ec.europa.eu",
        "scraper_key":  "erasmus",
        "interval_hrs": 24,
        "notes":        "Official API available. Covers EU mobility grants."
    },
    {
        "name":         "Türkiye Bursları — Turkish Scholarships",
        "base_url":     "https://www.turkiyeburslari.gov.tr/en",
        "scraper_key":  "turkiye_burslari",
        "interval_hrs": 24,
        "notes":        "JS-rendered. Uses Playwright. Popular with Palestinian students."
    },
    {
        "name":         "ReliefWeb — Jobs & Opportunities",
        "base_url":     "https://api.reliefweb.int/v1/jobs",
        "scraper_key":  "reliefweb",
        "interval_hrs": 6,
        "notes":        "Open API. High volume. Run every 6h. Focus on humanitarian sector."
    },
    {
        "name":         "AMIDEAST",
        "base_url":     "https://www.amideast.org/our-work/find-a-scholarship",
        "scraper_key":  "amideast",
        "interval_hrs": 24,
        "notes":        "Key US-Arab educational exchange. Frequently has Palestine-specific programs."
    },
    {
        "name":         "Arab Fund for Economic and Social Development",
        "base_url":     "https://www.arabfund.org/en/human-resources-development/scholarships",
        "scraper_key":  "arab_fund",
        "interval_hrs": 48,
        "notes":        "Arab regional fund. Scholarships open once a year."
    },
    {
        "name":         "Fulbright — US Department of State",
        "base_url":     "https://foreign.fulbrightonline.org/about/foreign-fulbright",
        "scraper_key":  "fulbright",
        "interval_hrs": 48,
        "notes":        "Prestigious US scholarship. Monitor for Palestine-specific programs."
    },
    {
        "name":         "ANERA — American Near East Refugee Aid",
        "base_url":     "https://www.anera.org/programs/education/",
        "scraper_key":  "anera",
        "interval_hrs": 24,
        "notes":        "Directly serves Palestinian communities. High relevance."
    },
    {
        "name":         "OpenAlex — Research Grants",
        "base_url":     "https://api.openalex.org/funders",
        "scraper_key":  "openalex",
        "interval_hrs": 72,
        "notes":        "Open academic API. Good for research scholarships and grants."
    },
]


def seed_sources(db):
    from db.models import ScrapeSource
    for s in SOURCES_SEED:
        exists = db.query(ScrapeSource).filter(ScrapeSource.scraper_key == s["scraper_key"]).first()
        if not exists:
            db.add(ScrapeSource(**s))
    db.commit()
    print(f"Seeded {len(SOURCES_SEED)} scrape sources.")
