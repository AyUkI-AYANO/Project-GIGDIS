"""Hotspot extraction pipeline for Project GIGDIS alpha0.1.0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import md5
from typing import Iterable
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from sources import COUNTRY_COORDS, COUNTRY_KEYWORDS, RSS_SOURCES, TOPIC_KEYWORDS


@dataclass
class Event:
    event_id: str
    title: str
    summary: str
    source: str
    source_credibility: float
    published_at: datetime
    country: str
    lat: float
    lon: float
    topic: str
    hotness: float


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _infer_country(text: str) -> str | None:
    lower = text.lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return country
    return None


def _infer_topic(text: str) -> str:
    lower = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return topic
    return "general"


def _recency_score(published_at: datetime) -> float:
    minutes = max((datetime.now(timezone.utc) - published_at).total_seconds() / 60, 0)
    return max(0.0, 1.0 - min(minutes / (24 * 60), 1.0))


def _severity_score(topic: str) -> float:
    if topic == "conflict":
        return 1.0
    if topic in {"disaster", "public-health"}:
        return 0.85
    if topic == "diplomacy":
        return 0.65
    if topic == "economy":
        return 0.6
    return 0.5


def _event_id(title: str, source: str) -> str:
    return md5(f"{source}:{title}".encode("utf-8")).hexdigest()


def _text(node: ET.Element | None, default: str = "") -> str:
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _find_child(item: ET.Element, candidates: list[str]) -> str:
    for tag in candidates:
        node = item.find(tag)
        value = _text(node)
        if value:
            return value
    return ""


def _fetch_rss_entries(url: str) -> list[dict]:
    with urlopen(url, timeout=10) as response:
        data = response.read()
    root = ET.fromstring(data)

    entries: list[dict] = []
    items = root.findall("./channel/item")
    if not items:
        items = root.findall("{http://www.w3.org/2005/Atom}entry")

    for item in items:
        title = _find_child(item, ["title", "{http://www.w3.org/2005/Atom}title"])
        summary = _find_child(
            item,
            ["description", "summary", "{http://www.w3.org/2005/Atom}summary"],
        )
        published = _find_child(
            item,
            [
                "pubDate",
                "published",
                "updated",
                "{http://www.w3.org/2005/Atom}updated",
                "{http://www.w3.org/2005/Atom}published",
            ],
        )
        entries.append({"title": title, "summary": summary, "published": published})

    return entries




def _fallback_events() -> list[Event]:
    now = datetime.now(timezone.utc)
    samples = [
        ("Ceasefire talks intensify in Middle East", "Israel", "diplomacy", "Demo Feed", 0.9),
        ("Severe earthquake response underway", "Japan", "disaster", "Demo Feed", 0.9),
        ("Trade negotiation round impacts markets", "China", "economy", "Demo Feed", 0.9),
    ]
    result = []
    for idx, (title, country, topic, source, credibility) in enumerate(samples, start=1):
        lat, lon = COUNTRY_COORDS[country]
        hotness = round(100 * (0.35 * credibility + 0.25 * 0.95 + 0.20 * 0.6 + 0.20 * _severity_score(topic)), 2)
        result.append(
            Event(
                event_id=_event_id(title, source + str(idx)),
                title=title,
                summary=title,
                source=source,
                source_credibility=credibility,
                published_at=now,
                country=country,
                lat=lat,
                lon=lon,
                topic=topic,
                hotness=hotness,
            )
        )
    return result


def fetch_events(limit_per_source: int = 20) -> list[Event]:
    events: list[Event] = []
    for source in RSS_SOURCES:
        try:
            entries = _fetch_rss_entries(source["url"])[:limit_per_source]
        except Exception:
            continue

        for entry in entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            body = f"{title} {summary}"
            country = _infer_country(body)
            if not country:
                continue

            topic = _infer_topic(body)
            published_at = _parse_datetime(entry.get("published"))
            recency = _recency_score(published_at)
            severity = _severity_score(topic)
            hotness = round(
                100
                * (
                    0.35 * source["credibility"]
                    + 0.25 * recency
                    + 0.20 * 0.7
                    + 0.20 * severity
                ),
                2,
            )
            lat, lon = COUNTRY_COORDS[country]
            events.append(
                Event(
                    event_id=_event_id(title, source["name"]),
                    title=title,
                    summary=summary,
                    source=source["name"],
                    source_credibility=source["credibility"],
                    published_at=published_at,
                    country=country,
                    lat=lat,
                    lon=lon,
                    topic=topic,
                    hotness=hotness,
                )
            )

    deduped = dedupe_events(events)
    if deduped:
        return deduped
    return _fallback_events()


def dedupe_events(events: Iterable[Event]) -> list[Event]:
    unique: dict[str, Event] = {}
    for event in events:
        key = f"{event.country}:{event.title.strip().lower()[:80]}"
        if key not in unique:
            unique[key] = event
    return sorted(unique.values(), key=lambda item: item.hotness, reverse=True)


def aggregate_by_country(events: Iterable[Event]) -> list[dict]:
    bucket: dict[str, dict] = {}
    for event in events:
        if event.country not in bucket:
            bucket[event.country] = {
                "country": event.country,
                "lat": event.lat,
                "lon": event.lon,
                "event_count": 0,
                "avg_hotness": 0.0,
                "top_topic": event.topic,
                "top_events": [],
            }
        record = bucket[event.country]
        record["event_count"] += 1
        record["avg_hotness"] += event.hotness
        record["top_events"].append(
            {
                "event_id": event.event_id,
                "title": event.title,
                "source": event.source,
                "published_at": event.published_at.isoformat(),
                "hotness": event.hotness,
                "topic": event.topic,
            }
        )

    result = []
    for record in bucket.values():
        record["avg_hotness"] = round(record["avg_hotness"] / record["event_count"], 2)
        record["top_events"] = sorted(
            record["top_events"], key=lambda item: item["hotness"], reverse=True
        )[:3]
        topic_count: dict[str, int] = {}
        for event in record["top_events"]:
            topic_count[event["topic"]] = topic_count.get(event["topic"], 0) + 1
        record["top_topic"] = sorted(topic_count.items(), key=lambda item: item[1], reverse=True)[0][0]
        result.append(record)

    return sorted(result, key=lambda item: item["avg_hotness"], reverse=True)


def build_adaptive_panel(events: list[Event], viewport_country: str | None = None) -> dict:
    global_top = [
        {
            "title": event.title,
            "country": event.country,
            "hotness": event.hotness,
            "topic": event.topic,
            "source": event.source,
        }
        for event in events[:5]
    ]

    viewport_related = []
    if viewport_country:
        viewport_related = [
            {
                "title": event.title,
                "country": event.country,
                "hotness": event.hotness,
                "topic": event.topic,
                "source": event.source,
            }
            for event in events
            if event.country.lower() == viewport_country.lower()
        ][:5]

    return {
        "global_top": global_top,
        "viewport_related": viewport_related,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
