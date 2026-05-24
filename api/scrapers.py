"""
scraper/scrapers.py
-------------------
Each source gets its own class inheriting BaseScraper.
The scraper ONLY collects and normalises raw data.
It never writes to the scholarships table directly.
All output goes to scrape_results with status=PENDING.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from loguru import logger
from playwright.async_api import async_playwright


# ─────────────────────────────────────────────
# Data structure returned by every scraper
# ─────────────────────────────────────────────

@dataclass
class RawScholarship:
    source_name:       str
    source_url:        str
    title:             str
    description:       str               = ""
    eligibility:       str               = ""
    funder:            str               = ""
    country:           str               = ""
    scholarship_type:  str               = "study"
    open_date:         Optional[str]     = None   # ISO string or raw text
    close_date:        Optional[str]     = None
    application_url:   str               = ""
    degree_levels:     list              = field(default_factory=list)
    fields:            list              = field(default_factory=list)
    language_req:      str               = ""
    funding_amount:    str               = ""
    raw_html:          str               = ""

    def content_hash(self) -> str:
        """Dedup key: SHA256 of (title + source_url)."""
        blob = (self.title.strip().lower() + self.source_url.strip().lower()).encode()
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self):
        return asdict(self)


# ─────────────────────────────────────────────
# Base scraper
# ─────────────────────────────────────────────

class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""

    def __init__(self):
        self.ua = UserAgent()
        self.headers = {"User-Agent": self.ua.random}

    async def fetch_html(self, url: str) -> str:
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    async def fetch_js(self, url: str) -> str:
        """Use Playwright for JavaScript-rendered pages."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            await browser.close()
            return content

    @abstractmethod
    async def scrape(self) -> list[RawScholarship]:
        """Return a list of RawScholarship objects."""
        ...

    def log(self, msg: str):
        logger.info(f"[{self.name}] {msg}")


# ─────────────────────────────────────────────
# 1. DAAD (Germany)
# ─────────────────────────────────────────────

class DAADScraper(BaseScraper):
    name = "daad"
    base_url = "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting DAAD scrape...")
        # DAAD uses query params for filtering — target open scholarships
        url = f"{self.base_url}?status=1&target=2&subjectGrps=&daad=1&intention=1&q=palestine"
        try:
            html = await self.fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")
            listings = soup.select(".c-result-list__item")
            self.log(f"Found {len(listings)} listings")
            for item in listings:
                title_el = item.select_one(".c-result-list__item-title a")
                desc_el  = item.select_one(".c-result-list__item-teaser")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link  = "https://www2.daad.de" + title_el.get("href", "")
                desc  = desc_el.get_text(strip=True) if desc_el else ""
                results.append(RawScholarship(
                    source_name=self.name,
                    source_url=link,
                    title=title,
                    description=desc,
                    funder="DAAD",
                    country="Germany",
                    scholarship_type="study",
                    raw_html=str(item)
                ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 2. Chevening (UK)
# ─────────────────────────────────────────────

class CheveningScraper(BaseScraper):
    name = "chevening"
    base_url = "https://www.chevening.org/scholarships/"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting Chevening scrape...")
        try:
            html = await self.fetch_html(self.base_url)
            soup = BeautifulSoup(html, "html.parser")
            # Chevening is a single flagship scholarship — scrape the main page
            title_el = soup.select_one("h1")
            desc_el  = soup.select_one(".intro-text, .page-intro, p")
            close_el = soup.find(string=lambda t: t and "deadline" in t.lower())
            title = title_el.get_text(strip=True) if title_el else "Chevening Scholarship"
            desc  = desc_el.get_text(strip=True)  if desc_el  else ""
            results.append(RawScholarship(
                source_name=self.name,
                source_url=self.base_url,
                title=title,
                description=desc,
                funder="UK Foreign, Commonwealth & Development Office",
                country="United Kingdom",
                scholarship_type="study",
                degree_levels=["Master"],
                raw_html=str(soup.body)[:5000]
            ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 3. Erasmus+ (EU)
# ─────────────────────────────────────────────

class ErasmusScraper(BaseScraper):
    name = "erasmus"
    base_url = "https://erasmus-plus.ec.europa.eu/opportunities/opportunities-for-individuals/students"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting Erasmus+ scrape...")
        # Erasmus has an official API
        api_url = "https://api.erasmus-plus.eu/api/v1/opportunities?pageSize=20&targetGroup=student"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(api_url)
                data = r.json()
                items = data.get("results", data.get("items", []))
                self.log(f"Found {len(items)} items via API")
                for item in items:
                    results.append(RawScholarship(
                        source_name=self.name,
                        source_url=item.get("url", self.base_url),
                        title=item.get("title", "Erasmus+ Opportunity"),
                        description=item.get("summary", item.get("description", "")),
                        funder="European Commission",
                        country="European Union",
                        scholarship_type="study",
                        open_date=item.get("startDate"),
                        close_date=item.get("applicationDeadline", item.get("endDate")),
                        application_url=item.get("applicationUrl", ""),
                    ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 4. Turkish Scholarships (Türkiye Bursları)
# ─────────────────────────────────────────────

class TurkishScholarshipsScraper(BaseScraper):
    name = "turkiye_burslari"
    base_url = "https://www.turkiyeburslari.gov.tr/en"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting Türkiye Bursları scrape...")
        try:
            html = await self.fetch_js(self.base_url)   # JS-rendered
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(".program-card, .scholarship-item, article")
            self.log(f"Found {len(cards)} cards")
            for card in cards[:10]:
                title_el = card.select_one("h2, h3, .title")
                desc_el  = card.select_one("p, .desc")
                link_el  = card.select_one("a")
                if not title_el:
                    continue
                results.append(RawScholarship(
                    source_name=self.name,
                    source_url="https://www.turkiyeburslari.gov.tr" + (link_el.get("href","") if link_el else ""),
                    title=title_el.get_text(strip=True),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    funder="Republic of Turkey",
                    country="Turkey",
                    scholarship_type="study",
                    raw_html=str(card)
                ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 5. ReliefWeb (Jobs / Opportunities)
# ─────────────────────────────────────────────

class ReliefWebScraper(BaseScraper):
    name = "reliefweb"
    base_url = "https://api.reliefweb.int/v1/jobs"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting ReliefWeb API scrape...")
        params = {
            "appname": "scholarship-hub",
            "query[value]": "Palestine scholarship training",
            "query[operator]": "AND",
            "filter[field]": "country.name",
            "filter[value]": "occupied Palestinian territory",
            "limit": 20,
            "fields[include][]": ["title", "body", "url", "date", "source"]
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(self.base_url, params=params)
                data = r.json()
                items = data.get("data", [])
                self.log(f"Found {len(items)} items")
                for item in items:
                    f = item.get("fields", {})
                    results.append(RawScholarship(
                        source_name=self.name,
                        source_url=f.get("url", "https://reliefweb.int"),
                        title=f.get("title", ""),
                        description=f.get("body", "")[:2000],
                        funder=", ".join(s.get("name","") for s in f.get("source",[])),
                        country="Palestine",
                        scholarship_type="volunteer",
                        open_date=f.get("date",{}).get("created"),
                        close_date=f.get("date",{}).get("closing"),
                    ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 6. AMIDEAST
# ─────────────────────────────────────────────

class AMIDEASTScraper(BaseScraper):
    name = "amideast"
    base_url = "https://www.amideast.org/our-work/find-a-scholarship"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting AMIDEAST scrape...")
        try:
            html = await self.fetch_html(self.base_url)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(".views-row, .scholarship-item, article.node")
            self.log(f"Found {len(items)} items")
            for item in items:
                title_el = item.select_one("h3 a, h2 a, .field-title a")
                desc_el  = item.select_one(".field-body, p")
                if not title_el:
                    continue
                href = title_el.get("href", "")
                url  = ("https://www.amideast.org" + href) if href.startswith("/") else href
                results.append(RawScholarship(
                    source_name=self.name,
                    source_url=url,
                    title=title_el.get_text(strip=True),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    funder="AMIDEAST",
                    country="USA / Middle East",
                    scholarship_type="study",
                    raw_html=str(item)
                ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 7. Arab Fund for Economic and Social Development
# ─────────────────────────────────────────────

class ArabFundScraper(BaseScraper):
    name = "arab_fund"
    base_url = "https://www.arabfund.org/en/human-resources-development/scholarships"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting Arab Fund scrape...")
        try:
            html = await self.fetch_html(self.base_url)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select("article, .scholarship, .card, .item")
            self.log(f"Found {len(items)} items")
            for item in items:
                title_el = item.select_one("h2, h3, .title")
                desc_el  = item.select_one("p, .description")
                link_el  = item.select_one("a")
                if not title_el:
                    continue
                href = link_el.get("href","") if link_el else ""
                url  = ("https://www.arabfund.org" + href) if href.startswith("/") else href or self.base_url
                results.append(RawScholarship(
                    source_name=self.name,
                    source_url=url,
                    title=title_el.get_text(strip=True),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    funder="Arab Fund for Economic and Social Development",
                    country="Arab World",
                    scholarship_type="study",
                    raw_html=str(item)
                ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 8. Fulbright (US)
# ─────────────────────────────────────────────

class FulbrightScraper(BaseScraper):
    name = "fulbright"
    base_url = "https://foreign.fulbrightonline.org/about/foreign-fulbright"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting Fulbright scrape...")
        try:
            html = await self.fetch_html(self.base_url)
            soup = BeautifulSoup(html, "html.parser")
            desc_el = soup.select_one(".entry-content, .page-content, main p")
            deadline_el = soup.find(string=lambda t: t and "deadline" in t.lower())
            results.append(RawScholarship(
                source_name=self.name,
                source_url=self.base_url,
                title="Fulbright Foreign Student Program",
                description=desc_el.get_text(strip=True)[:2000] if desc_el else "",
                funder="U.S. Department of State",
                country="United States",
                scholarship_type="study",
                degree_levels=["Master", "PhD"],
                application_url="https://foreign.fulbrightonline.org",
            ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 9. ANERA (American Near East Refugee Aid)
# ─────────────────────────────────────────────

class ANERAScraper(BaseScraper):
    name = "anera"
    base_url = "https://www.anera.org/programs/education/"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting ANERA scrape...")
        try:
            html = await self.fetch_html(self.base_url)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select("article, .program-item, .post")
            self.log(f"Found {len(items)} items")
            for item in items[:5]:
                title_el = item.select_one("h2, h3")
                desc_el  = item.select_one("p")
                link_el  = item.select_one("a")
                if not title_el:
                    continue
                href = link_el.get("href","") if link_el else ""
                results.append(RawScholarship(
                    source_name=self.name,
                    source_url=href or self.base_url,
                    title=title_el.get_text(strip=True),
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    funder="ANERA",
                    country="Palestine",
                    scholarship_type="study",
                ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# 10. OpenAlex (research grants)
# ─────────────────────────────────────────────

class OpenAlexScraper(BaseScraper):
    name = "openalex"
    base_url = "https://api.openalex.org/funders"

    async def scrape(self) -> list[RawScholarship]:
        results = []
        self.log("Starting OpenAlex research funders scrape...")
        try:
            params = {
                "filter": "country_code:PS",
                "per-page": 20,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(self.base_url, params=params)
                data = r.json()
                items = data.get("results", [])
                self.log(f"Found {len(items)} funders")
                for item in items:
                    results.append(RawScholarship(
                        source_name=self.name,
                        source_url=item.get("homepage_url", "https://openalex.org"),
                        title=f"Research Grant — {item.get('display_name','')}",
                        description=item.get("description", ""),
                        funder=item.get("display_name",""),
                        country="Palestine",
                        scholarship_type="research",
                        funding_amount=str(item.get("grants_count","")) + " grants on record",
                    ))
        except Exception as e:
            self.log(f"Error: {e}")
        return results


# ─────────────────────────────────────────────
# Registry — maps scraper_key → class
# ─────────────────────────────────────────────

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "daad":             DAADScraper,
    "chevening":        CheveningScraper,
    "erasmus":          ErasmusScraper,
    "turkiye_burslari": TurkishScholarshipsScraper,
    "reliefweb":        ReliefWebScraper,
    "amideast":         AMIDEASTScraper,
    "arab_fund":        ArabFundScraper,
    "fulbright":        FulbrightScraper,
    "anera":            ANERAScraper,
    "openalex":         OpenAlexScraper,
}
