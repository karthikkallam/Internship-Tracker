from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx
from dateutil import parser as date_parser
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal
from .models import Job, serialize_job
from .notifier import Notifier

logger = logging.getLogger(__name__)

INTERN_REGEX = re.compile(r"\b(?:intern|interns|internship|internships|co[- ]?op|coops?|co-op)\b", re.IGNORECASE)
US_HINTS = (
    "united states",
    "u.s.",
    "u.s.a",
    "usa",
    "us-based",
    "us only",
    "remote - us",
    "remote, us",
    "remote within the us",
    "remote in the us"
)
STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}
STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming", "district of columbia"
}
DEFAULT_GREENHOUSE_BOARDS = [slug for slug in os.getenv("GREENHOUSE_BOARDS", "airbnb,databricks").split(",") if slug.strip()]
DEFAULT_LEVER_COMPANIES = [slug for slug in os.getenv("LEVER_COMPANIES", "lever").split(",") if slug.strip()]
DEFAULT_ASHBY_ORGS = [slug for slug in os.getenv("ASHBY_ORGANIZATIONS", "").split(",") if slug.strip()]
DEFAULT_SMARTRECRUITERS_COMPANIES = [slug for slug in os.getenv("SMARTRECRUITERS_COMPANIES", "smartrecruiters").split(",") if slug.strip()]
DEFAULT_RECRUITEE_COMPANIES = [slug for slug in os.getenv("RECRUITEE_COMPANIES", "").split(",") if slug.strip()]

POLL_MIN_SECONDS = int(os.getenv("POLL_INTERVAL_MIN_SECONDS", "120"))
POLL_MAX_SECONDS = int(os.getenv("POLL_INTERVAL_MAX_SECONDS", "300"))


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive parsing
        logger.debug("Unable to parse datetime %s: %s", value, exc)
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_internship(title: Optional[str]) -> bool:
    if not title:
        return False
    return bool(INTERN_REGEX.search(title))





def _is_us_location(location: Optional[str]) -> bool:
    if not location:
        return False
    normalized = location.lower()
    if any(hint in normalized for hint in US_HINTS):
        return True
    if 'remote' in normalized:
        non_us_remote_hints = (
            'canada', 'emea', 'europe', 'apac', 'asia', 'uk', 'ireland', 'australia', 'new zealand', 'latam', 'global', 'worldwide'
        )
        if not any(hint in normalized for hint in non_us_remote_hints):
            return True
    tokens = re.split(r"[\/;|]", location)
    for token in tokens:
        parts = [part.strip() for part in token.split(',')]
        if not parts:
            continue
        for part in reversed(parts):
            candidate = re.sub(r"\([^)]*\)", "", part).strip()
            if not candidate:
                continue
            lower = candidate.lower()
            upper = candidate.upper()
            if lower in STATE_NAMES:
                return True
            if upper in STATE_ABBREVIATIONS:
                return True
    return False



def _clamp_sleep_window() -> int:
    low = max(120, POLL_MIN_SECONDS)
    high = max(low, min(600, POLL_MAX_SECONDS))
    return random.randint(low, high)


def _safe_json(response: httpx.Response, context: str) -> Optional[Any]:
    try:
        return response.json()
    except ValueError as exc:
        logger.warning("%s returned invalid JSON: %s", context, exc)
        return None


async def start_poller(notifier: Notifier) -> None:
    logger.info("Polling task starting")
    while True:
        try:
            new_jobs = await poll_once(notifier=notifier)
            if new_jobs:
                logger.info("Stored %d new internship postings", len(new_jobs))
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            logger.info("Polling task cancelled")
            raise
        except Exception as exc:  # pragma: no cover - top-level resilience
            logger.exception("Unhandled error during polling: %s", exc)
        sleep_for = _clamp_sleep_window()
        logger.debug("Sleeping %s seconds before next poll", sleep_for)
        await asyncio.sleep(sleep_for)


async def poll_once(notifier: Notifier) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, read=20.0)) as client:
        harvested: List[Dict[str, Any]] = []
        harvested.extend(await fetch_greenhouse_jobs(client, DEFAULT_GREENHOUSE_BOARDS))
        harvested.extend(await fetch_lever_jobs(client, DEFAULT_LEVER_COMPANIES))
        harvested.extend(await fetch_ashby_jobs(client, DEFAULT_ASHBY_ORGS))
        harvested.extend(await fetch_smartrecruiters_jobs(client, DEFAULT_SMARTRECRUITERS_COMPANIES))
        harvested.extend(await fetch_recruitee_jobs(client, DEFAULT_RECRUITEE_COMPANIES))

    if not harvested:
        return []

    new_jobs = await asyncio.to_thread(_persist_jobs, harvested)

    for job in new_jobs:
        await notifier.broadcast_job(job)

    return new_jobs



async def fetch_greenhouse_jobs(client: httpx.AsyncClient, boards: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for board in boards:
        board_slug = board.strip()
        if not board_slug:
            continue
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Greenhouse request failed for %s: %s", board_slug, exc)
            continue
        payload = _safe_json(response, f"Greenhouse {board_slug}")
        if not isinstance(payload, dict):
            continue
        jobs = payload.get("jobs", [])
        for job in jobs:
            title = job.get("title")
            if not _is_internship(title):
                continue
            location = (job.get("location") or {}).get("name")
            if location and not _is_us_location(location):
                offices = job.get("offices") or []
                office_names = ", ".join(
                    filter(None, [office.get("name") for office in offices if isinstance(office, dict)])
                )
                if office_names:
                    location = office_names
            if not _is_us_location(location):
                continue
            normalized = {
                "title": title,
                "company": job.get("company_name") or board_slug.capitalize(),
                "location": location,
                "url": job.get("absolute_url"),
                "posted_at": _parse_datetime(job.get("updated_at") or job.get("first_published")),
                "req_id": str(job.get("id")),
                "source": "greenhouse",
            }
            if normalized["url"]:
                results.append(normalized)
    return results





async def fetch_lever_jobs(client: httpx.AsyncClient, companies: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for company in companies:
        slug = company.strip()
        if not slug:
            continue
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            response = await client.get(url)
            if response.status_code == 404:
                logger.debug("Lever company %s not found", slug)
                continue
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Lever request failed for %s: %s", slug, exc)
            continue
        payload = _safe_json(response, f"Lever {slug}")
        if isinstance(payload, dict) and not payload.get("ok", True):
            logger.debug("Lever API responded with error for %s: %s", slug, payload)
            continue
        postings = payload if isinstance(payload, list) else []
        for posting in postings:
            title = posting.get("text") or posting.get("title")
            if not _is_internship(title):
                continue
            categories = posting.get("categories") or {}
            location = categories.get("location")
            if not location:
                all_locations = categories.get("allLocations")
                if isinstance(all_locations, list) and all_locations:
                    location = ", ".join(all_locations)
            loc_obj = posting.get("location")
            if not location and isinstance(loc_obj, dict):
                location_parts = [loc_obj.get("city"), loc_obj.get("state"), loc_obj.get("country")]
                location = ", ".join(filter(None, location_parts)) or None
            if isinstance(loc_obj, str) and not location:
                location = loc_obj
            if not location and categories.get("country") in {"United States", "USA"}:
                location = categories.get("country")
            if not _is_us_location(location):
                continue
            normalized = {
                "title": title,
                "company": posting.get("company") or slug.capitalize(),
                "location": location,
                "url": posting.get("hostedUrl") or posting.get("applyUrl"),
                "posted_at": _parse_datetime(posting.get("createdAt")),
                "req_id": posting.get("id") or posting.get("leverId") or posting.get("postingId"),
                "source": "lever",
            }
            if normalized["url"] and normalized["req_id"]:
                results.append(normalized)
    return results



async def fetch_ashby_jobs(client: httpx.AsyncClient, org_slugs: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not org_slugs:
        return results
    query = (
        "query JobBoardWithTeams($organizationHostedJobsPageName: String!) { "
        "jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { "
        "jobPostings { id title locationName employmentType teamId } "
        "teams { id name } "
        "} }"
    )
    for slug in org_slugs:
        hosted_name = slug.strip()
        if not hosted_name:
            continue
        payload = {
            "operationName": "JobBoardWithTeams",
            "query": query,
            "variables": {"organizationHostedJobsPageName": hosted_name},
        }
        try:
            response = await client.post(
                "https://jobs.ashbyhq.com/api/non-user-graphql",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Ashby request failed for %s: %s", hosted_name, exc)
            continue
        payload_json = _safe_json(response, f"Ashby {hosted_name}")
        if not isinstance(payload_json, dict):
            continue
        board = (payload_json.get("data") or {}).get("jobBoardWithTeams") or {}
        postings = board.get("jobPostings") or []
        teams = {team.get("id"): team.get("name") for team in board.get("teams") or []}
        for posting in postings:
            title = posting.get("title")
            if not _is_internship(title):
                continue
            team_name = teams.get(posting.get("teamId")) if posting.get("teamId") else None
            location = posting.get("locationName") or posting.get("locationAddress")
            if not _is_us_location(location):
                continue
            normalized = {
                "title": title,
                "company": team_name or hosted_name.capitalize(),
                "location": location,
                "url": f"https://jobs.ashbyhq.com/{hosted_name}/{posting.get('id')}",
                "posted_at": None,  # Ashby board response does not include timestamps
                "req_id": posting.get("id"),
                "source": "ashby",
            }
            if normalized["req_id"]:
                results.append(normalized)
    return results




async def fetch_smartrecruiters_jobs(client: httpx.AsyncClient, companies: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for company in companies:
        slug = company.strip()
        if not slug:
            continue
        list_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        try:
            response = await client.get(list_url, params={"limit": 100})
            response.raise_for_status()
        except Exception as exc:
            logger.warning("SmartRecruiters list request failed for %s: %s", slug, exc)
            continue
        payload = _safe_json(response, f"SmartRecruiters {slug}")
        if not isinstance(payload, dict):
            continue
        for posting in payload.get("content", []):
            title = posting.get("name")
            if not _is_internship(title):
                continue
            posting_id = posting.get("id")
            detail_url = posting.get("ref") or f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"
            apply_url = None
            posted_at = _parse_datetime(posting.get("releasedDate"))
            location_data = posting.get("location") or {}
            location = location_data.get("fullLocation") or location_data.get("city")
            country_code = (location_data.get("country") or location_data.get("countryCode") or "").lower()
            if not location and country_code in {"us", "usa"}:
                location = "United States"
            if location and not _is_us_location(location):
                if country_code in {"us", "usa"} and "united states" not in location.lower():
                    location = f"{location}, United States"
                else:
                    location = None
            if not location or not _is_us_location(location):
                continue
            if detail_url:
                try:
                    detail = await client.get(detail_url)
                    if detail.status_code == 200:
                        detail_payload = _safe_json(detail, f"SmartRecruiters detail {posting_id}")
                        if isinstance(detail_payload, dict):
                            apply_url = (
                                detail_payload.get("applyUrl")
                                or (detail_payload.get("jobAd") or {}).get("applyUrl")
                            )
                except Exception as exc:
                    logger.debug("SmartRecruiters detail fetch failed for %s: %s", posting_id, exc)
            normalized = {
                "title": title,
                "company": (posting.get("company") or {}).get("name") or slug.capitalize(),
                "location": location,
                "url": apply_url or posting.get("ref") or posting.get("jobAdId"),
                "posted_at": posted_at,
                "req_id": posting_id,
                "source": "smartrecruiters",
            }
            if normalized["url"] and normalized["req_id"]:
                results.append(normalized)
    return results





async def fetch_recruitee_jobs(client: httpx.AsyncClient, companies: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for company in companies:
        slug = company.strip()
        if not slug:
            continue
        url = f"https://{slug}.recruitee.com/api/offers/"
        try:
            response = await client.get(url, params={"limit": 100})
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Recruitee request failed for %s: %s", slug, exc)
            continue
        payload = _safe_json(response, f"Recruitee {slug}")
        if not isinstance(payload, dict):
            continue
        offers = payload.get("offers") or []
        for offer in offers:
            title = offer.get("title")
            if not _is_internship(title):
                continue
            raw_location = offer.get("location")
            location_label = offer.get("location_label")
            country_code = ""
            location = None
            if isinstance(raw_location, dict):
                country_code = (raw_location.get("country") or raw_location.get("country_code") or "").lower()
                location_parts = [
                    raw_location.get("city"),
                    raw_location.get("region"),
                    raw_location.get("country"),
                ]
                location = ", ".join(filter(None, location_parts)) or location_label
            elif isinstance(raw_location, str):
                location = raw_location or location_label
            else:
                location = location_label
            if country_code in {"us", "usa"}:
                if location and "united states" not in location.lower():
                    location = f"{location}, United States"
                elif not location:
                    location = "United States"
            if not _is_us_location(location):
                continue
            normalized = {
                "title": title,
                "company": offer.get("company_name") or slug.capitalize(),
                "location": location,
                "url": offer.get("careers_url") or offer.get("url"),
                "posted_at": _parse_datetime(offer.get("published_at")),
                "req_id": str(offer.get("id")),
                "source": "recruitee",
            }
            if normalized["url"]:
                results.append(normalized)
    return results


def _persist_jobs(jobs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    session = SessionLocal()
    inserted: List[Dict[str, Any]] = []
    try:
        for job in jobs:
            if not job.get("req_id") or not job.get("url"):
                continue
            record = Job(
                title=job["title"],
                company=job.get("company") or "Unknown",
                location=job.get("location"),
                url=job["url"],
                posted_at=job.get("posted_at"),
                req_id=str(job["req_id"]),
                source=job.get("source") or "unknown",
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                continue
            session.refresh(record)
            inserted.append(serialize_job(record))
    finally:
        session.close()
    return inserted
