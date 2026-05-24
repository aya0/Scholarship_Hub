"""
scraper/normalizer.py
---------------------
Takes raw scraped text and uses the Claude API to normalize it
into a clean, structured JSON object ready for admin review.
The AI never publishes — it only helps admins review faster.
"""

import json
import anthropic
from loguru import logger
from scraper.scrapers import RawScholarship


NORMALIZE_PROMPT = """
You are a data extraction assistant for a Palestinian scholarship platform.
Given raw scraped scholarship data, extract and normalize it into structured JSON.

Return ONLY a valid JSON object with these exact keys (use null for missing fields):
{
  "title": "string — clean scholarship title",
  "type": "one of: study | work | volunteer | training | research",
  "country": "string — host country",
  "funder": "string — organization providing the scholarship",
  "description": "string — 2-3 sentence summary",
  "eligibility": "string — who can apply, key requirements",
  "application_steps": "string — how to apply",
  "open_date": "YYYY-MM-DD or null",
  "close_date": "YYYY-MM-DD or null",
  "degree_levels": ["Bachelor" | "Master" | "PhD" | "Any"],
  "fields": ["list of academic fields"],
  "language_req": "string e.g. IELTS 6.5 or null",
  "min_gpa": float or null,
  "funding_amount": "string description of what is covered or null",
  "application_url": "string URL or null",
  "palestinians_eligible": true | false | null,
  "confidence": 0.0-1.0
}

If you are not confident a field is accurate, set it to null.
The `confidence` score (0-1) reflects overall data quality of what you extracted.
Return only the JSON object, no explanation, no markdown.
"""


class AIScholarshipNormalizer:
    def __init__(self):
        self.client = anthropic.Anthropic()

    async def normalize(self, raw: RawScholarship) -> dict:
        """
        Send raw scraped data to Claude and get back normalized fields.
        Falls back to raw data if the API call fails.
        """
        raw_text = f"""
Source: {raw.source_name}
URL: {raw.source_url}
Title: {raw.title}
Description: {raw.description}
Eligibility: {raw.eligibility}
Funder: {raw.funder}
Country: {raw.country}
Type: {raw.scholarship_type}
Open date: {raw.open_date}
Close date: {raw.close_date}
Degree levels: {', '.join(raw.degree_levels) if raw.degree_levels else ''}
Fields: {', '.join(raw.fields) if raw.fields else ''}
Language requirement: {raw.language_req}
Funding amount: {raw.funding_amount}
"""
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=NORMALIZE_PROMPT,
                messages=[{"role": "user", "content": raw_text}]
            )
            response_text = message.content[0].text.strip()
            # strip markdown fences if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            normalized = json.loads(response_text)
            logger.info(f"[normalizer] {raw.source_name} — normalized '{raw.title[:60]}' "
                        f"(confidence={normalized.get('confidence',0):.2f})")
            return normalized
        except json.JSONDecodeError as e:
            logger.warning(f"[normalizer] JSON parse error for {raw.title}: {e}")
            return self._fallback(raw)
        except Exception as e:
            logger.error(f"[normalizer] API error for {raw.title}: {e}")
            return self._fallback(raw)

    def _fallback(self, raw: RawScholarship) -> dict:
        """Return raw fields as-is if normalization fails."""
        return {
            "title": raw.title,
            "type": raw.scholarship_type,
            "country": raw.country,
            "funder": raw.funder,
            "description": raw.description,
            "eligibility": raw.eligibility,
            "application_steps": None,
            "open_date": raw.open_date,
            "close_date": raw.close_date,
            "degree_levels": raw.degree_levels,
            "fields": raw.fields,
            "language_req": raw.language_req,
            "min_gpa": None,
            "funding_amount": raw.funding_amount,
            "application_url": raw.application_url,
            "palestinians_eligible": None,
            "confidence": 0.3,
        }
