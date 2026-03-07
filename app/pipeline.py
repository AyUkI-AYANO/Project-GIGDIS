"""Hotspot extraction pipeline for Project GIGDIS beta4.6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import md5
from typing import Iterable
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from sources import (
    COUNTRY_COORDS,
    COUNTRY_KEYWORDS,
    POLITICAL_LEANING_COLORS,
    RSS_SOURCES,
    TOPIC_KEYWORDS,
    get_source_profile,
)

MIN_EVENTS_PER_TOPIC = 3
SUPPORTED_LANGUAGES = {"zh", "en", "ru", "fr", "de"}

TOPIC_TRANSLATIONS = {
    "zh": {
        "military": "军事",
        "politics": "政治",
        "technology": "科技",
        "science": "科学",
        "disaster": "灾害",
        "public-health": "公共卫生",
        "diplomacy": "外交",
        "economy": "经济",
        "general": "综合",
    },
    "en": {},
    "ru": {
        "military": "Военные",
        "politics": "Политика",
        "technology": "Технологии",
        "science": "Наука",
        "disaster": "Бедствия",
        "public-health": "Общественное здоровье",
        "diplomacy": "Дипломатия",
        "economy": "Экономика",
        "general": "Общее",
    },
    "fr": {
        "military": "Militaire",
        "politics": "Politique",
        "technology": "Technologie",
        "science": "Science",
        "disaster": "Catastrophe",
        "public-health": "Santé publique",
        "diplomacy": "Diplomatie",
        "economy": "Économie",
        "general": "Général",
    },
    "de": {
        "military": "Militär",
        "politics": "Politik",
        "technology": "Technologie",
        "science": "Wissenschaft",
        "disaster": "Katastrophe",
        "public-health": "Öffentliche Gesundheit",
        "diplomacy": "Diplomatie",
        "economy": "Wirtschaft",
        "general": "Allgemein",
    },
}


MILITARY_CONTEXT_KEYWORDS = {
    "war",
    "airstrike",
    "missile",
    "military",
    "armed forces",
    "troop",
    "defense ministry",
    "artillery",
    "frontline",
    "ceasefire",
    "drone strike",
    "navy",
    "army",
}

NON_MILITARY_ATTACK_HINTS = {
    "animal",
    "shark",
    "crocodile",
    "spider",
    "snake",
    "wildlife",
    "tourist",
    "hiker",
    "killed by",
}


TOPIC_COLORS = {
    "military": "#ef4444",
    "politics": "#8b5cf6",
    "technology": "#06b6d4",
    "science": "#10b981",
    "disaster": "#f97316",
    "public-health": "#22c55e",
    "diplomacy": "#eab308",
    "economy": "#f59e0b",
    "general": "#64748b",
}

PHRASE_TRANSLATIONS = {
    "zh": {
        "Regional defense exercise expands naval deployment": "区域防务演习扩大海军部署",
        "Joint patrol activity raises regional alert": "联合巡逻活动提升区域警戒",
        "Border security forces conduct readiness drill": "边防部队开展战备演练",
        "Defense ministry reports missile interception": "国防部通报导弹拦截行动",
        "No data": "暂无数据",
    },
    "ru": {
        "No data": "Нет данных",
    },
    "fr": {
        "No data": "Aucune donnée",
    },
    "de": {
        "No data": "Keine Daten",
    },
}


@dataclass
class Event:
    event_id: str
    title: str
    summary: str
    link: str
    source: str
    source_type: str
    source_credibility: float
    source_outlet: str
    political_leaning: str
    political_leaning_color: str
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
        if topic != "military":
            if any(keyword in lower for keyword in keywords):
                return topic
            continue

        military_hits = [keyword for keyword in keywords if keyword in lower]
        has_context = any(keyword in lower for keyword in MILITARY_CONTEXT_KEYWORDS)
        non_military_attack = "attack" in lower and any(hint in lower for hint in NON_MILITARY_ATTACK_HINTS)
        if military_hits and has_context and not non_military_attack:
            return "military"
    return "general"


def normalize_language(lang: str | None) -> str:
    candidate = (lang or "zh").strip().lower()
    return candidate if candidate in SUPPORTED_LANGUAGES else "zh"


def translate_topic(topic: str, lang: str) -> str:
    language = normalize_language(lang)
    return TOPIC_TRANSLATIONS.get(language, {}).get(topic, topic)


def translate_text(text: str, lang: str) -> str:
    language = normalize_language(lang)
    if language == "en":
        return text
    if text in PHRASE_TRANSLATIONS.get(language, {}):
        return PHRASE_TRANSLATIONS[language][text]
    return text


def _recency_score(published_at: datetime) -> float:
    minutes = max((datetime.now(timezone.utc) - published_at).total_seconds() / 60, 0)
    return max(0.0, 1.0 - min(minutes / (24 * 60), 1.0))


def _severity_score(topic: str) -> float:
    if topic == "military":
        return 1.0
    if topic in {"disaster", "public-health"}:
        return 0.9
    if topic in {"politics", "diplomacy"}:
        return 0.75
    if topic in {"technology", "science", "economy"}:
        return 0.65
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
        summary = _find_child(item, ["description", "summary", "{http://www.w3.org/2005/Atom}summary"])
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
        link = _find_child(item, ["link", "{http://www.w3.org/2005/Atom}link"])
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "").strip()
        entries.append({"title": title, "summary": summary, "published": published})
        entries[-1]["link"] = link

    return entries


def _fallback_events() -> list[Event]:
    now = datetime.now(timezone.utc)
    samples = [
        ("Global AI summit announces new model safety pact", "United States", "technology", "Demo Feed", 0.9),
        ("Regional defense exercise expands naval deployment", "Japan", "military", "Demo Feed", 0.9),
        ("Parliament passes major digital governance bill", "United Kingdom", "politics", "Demo Feed", 0.9),
        ("New climate research mission launched", "France", "science", "Demo Feed", 0.9),
        ("Emergency teams respond to major earthquake", "Turkey", "disaster", "Demo Feed", 0.9),
        ("Cross-border diplomacy talks resume after summit", "Egypt", "diplomacy", "Demo Feed", 0.9),
        ("WHO backs emergency vaccination corridor", "India", "public-health", "Demo Feed", 0.9),
        ("Oil market volatility triggers inflation concern", "Saudi Arabia", "economy", "Demo Feed", 0.9),
        ("City infrastructure upgrade accelerates", "Germany", "general", "Demo Feed", 0.9),
    ]
    result = []
    for idx, (title, country, topic, source, credibility) in enumerate(samples, start=1):
        lat, lon = COUNTRY_COORDS[country]
        hotness = round(
            100 * (0.35 * credibility + 0.25 * 0.95 + 0.20 * 0.6 + 0.20 * _severity_score(topic)),
            2,
        )
        profile = get_source_profile(source)
        result.append(
            Event(
                event_id=_event_id(title, source + str(idx)),
                title=title,
                summary=title,
                link="",
                source=source,
                source_type="mainstream",
                source_credibility=credibility,
                source_outlet=profile["outlet"],
                political_leaning=profile["political_leaning"],
                political_leaning_color=POLITICAL_LEANING_COLORS.get(profile["political_leaning"], "#10b981"),
                published_at=now,
                country=country,
                lat=lat,
                lon=lon,
                topic=topic,
                hotness=hotness,
            )
        )
    return result


def _inject_topic_coverage(events: list[Event]) -> list[Event]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.topic] = counts.get(event.topic, 0) + 1

    now = datetime.now(timezone.utc)
    synthetic: list[Event] = []
    topic_templates = {
        "military": [
            ("Joint patrol activity raises regional alert", "South Korea"),
            ("Border security forces conduct readiness drill", "Ukraine"),
            ("Defense ministry reports missile interception", "Israel"),
        ],
        "politics": [
            ("Coalition talks intensify ahead of leadership vote", "Italy"),
            ("Constitutional reform debate reaches final stage", "Spain"),
            ("Cabinet reshuffle signals policy pivot", "Canada"),
        ],
        "technology": [
            ("Semiconductor investment plan expands manufacturing", "China"),
            ("Cybersecurity agency warns of coordinated attacks", "Australia"),
            ("Cloud platform launch targets enterprise AI", "United States"),
        ],
        "science": [
            ("Space telescope captures deep-field anomalies", "France"),
            ("Polar climate study confirms rapid ice decline", "United Kingdom"),
            ("Gene-editing trial enters larger phase", "Germany"),
        ],
        "disaster": [
            ("Heavy flooding displaces thousands after storms", "Brazil"),
            ("Wildfire containment efforts expand overnight", "Australia"),
            ("Volcanic activity prompts evacuation alerts", "Indonesia"),
        ],
        "public-health": [
            ("Health ministry expands outbreak screening program", "India"),
            ("Regional hospitals increase respiratory ward capacity", "United Kingdom"),
            ("Cross-border disease surveillance network upgraded", "South Africa"),
        ],
        "diplomacy": [
            ("Trilateral summit outlines de-escalation roadmap", "Egypt"),
            ("Mediated talks produce prisoner exchange framework", "Turkey"),
            ("Foreign ministers agree on sanctions review process", "Saudi Arabia"),
        ],
        "economy": [
            ("Central bank holds rates amid inflation pressure", "Mexico"),
            ("Trade corridor agreement boosts export forecasts", "China"),
            ("Energy subsidy reforms trigger market repricing", "Japan"),
        ],
        "general": [
            ("Major transport hub reopens after upgrades", "Saudi Arabia"),
            ("Nationwide infrastructure package enters rollout", "Canada"),
            ("Education reform bill receives cross-party support", "Brazil"),
        ],
    }

    for topic, templates in topic_templates.items():
        existing = counts.get(topic, 0)
        required = max(0, MIN_EVENTS_PER_TOPIC - existing)
        if not required:
            continue
        for idx, (title, country) in enumerate(templates[:required], start=1):
            if country not in COUNTRY_COORDS:
                continue
            lat, lon = COUNTRY_COORDS[country]
            source = "Synthetic Coverage"
            credibility = 0.7
            hotness = round(
                100 * (0.35 * credibility + 0.25 * 0.92 + 0.20 * 0.65 + 0.20 * _severity_score(topic)),
                2,
            )
            profile = get_source_profile(source)
            synthetic.append(
                Event(
                    event_id=_event_id(f"{title}-{topic}-{idx}", source),
                    title=title,
                    summary=title,
                    link="",
                    source=source,
                    source_type="mainstream",
                    source_credibility=credibility,
                    source_outlet=profile["outlet"],
                    political_leaning=profile["political_leaning"],
                    political_leaning_color=POLITICAL_LEANING_COLORS.get(profile["political_leaning"], "#10b981"),
                    published_at=now,
                    country=country,
                    lat=lat,
                    lon=lon,
                    topic=topic,
                    hotness=hotness,
                )
            )

    if not synthetic:
        return events
    return events + synthetic


def fetch_events(limit_per_source: int = 20, source_types: set[str] | None = None) -> list[Event]:
    events: list[Event] = []
    for source in RSS_SOURCES:
        source_type = str(source.get("type", "mainstream"))
        if source_types and source_type not in source_types:
            continue
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
                100 * (0.35 * source["credibility"] + 0.25 * recency + 0.20 * 0.7 + 0.20 * severity),
                2,
            )
            lat, lon = COUNTRY_COORDS[country]
            profile = get_source_profile(source["name"])
            events.append(
                Event(
                    event_id=_event_id(title, source["name"]),
                    title=title,
                    summary=summary,
                    link=entry.get("link", ""),
                    source=source["name"],
                    source_type=source_type,
                    source_credibility=source["credibility"],
                    source_outlet=profile["outlet"],
                    political_leaning=profile["political_leaning"],
                    political_leaning_color=POLITICAL_LEANING_COLORS.get(profile["political_leaning"], "#10b981"),
                    published_at=published_at,
                    country=country,
                    lat=lat,
                    lon=lon,
                    topic=topic,
                    hotness=hotness,
                )
            )

    deduped = dedupe_events(events)
    if not deduped:
        deduped = _fallback_events()
    return dedupe_events(_inject_topic_coverage(deduped))


def filter_events_by_topics(events: Iterable[Event], topics: list[str] | None) -> list[Event]:
    event_list = list(events)
    if not topics:
        return event_list
    allowed = {topic.strip().lower() for topic in topics if topic.strip()}
    if not allowed:
        return event_list
    return [event for event in event_list if event.topic.lower() in allowed]


def filter_events_by_source_types(events: Iterable[Event], source_types: list[str] | None) -> list[Event]:
    event_list = list(events)
    if not source_types:
        return event_list
    allowed = {item.strip().lower() for item in source_types if item.strip()}
    if not allowed:
        return event_list
    return [event for event in event_list if event.source_type.lower() in allowed]


def dedupe_events(events: Iterable[Event]) -> list[Event]:
    unique: dict[str, Event] = {}
    for event in events:
        key = f"{event.country}:{event.title.strip().lower()[:80]}"
        existing = unique.get(key)
        if existing is None or event.hotness > existing.hotness:
            unique[key] = event
    return sorted(unique.values(), key=lambda item: item.hotness, reverse=True)


def _build_related_source_index(events: list[Event]) -> dict[str, dict[tuple[str, str] | str, list[Event]]]:
    return {
        "country_topic": _group_events(events, lambda event: (event.country, event.topic)),
        "country": _group_events(events, lambda event: event.country),
        "topic": _group_events(events, lambda event: event.topic),
    }


def _group_events(events: list[Event], key_fn) -> dict:
    grouped: dict = {}
    for event in events:
        key = key_fn(event)
        grouped.setdefault(key, []).append(event)
    return grouped


def _expand_sources_for_event(country: str, topic: str, existing: list[dict], related_index: dict[str, dict], lang: str) -> list[dict]:
    seen = {str(item.get("source", "")).lower() for item in existing}
    extras: list[dict] = []
    candidate_pools = [
        related_index["country_topic"].get((country, topic), []),
        related_index["country"].get(country, []),
        related_index["topic"].get(topic, []),
    ]

    for pool in candidate_pools:
        for candidate in sorted(pool, key=lambda item: item.hotness, reverse=True):
            source_name = candidate.source.lower()
            if source_name in seen:
                continue
            seen.add(source_name)
            extras.append(
                {
                    "source": candidate.source,
                    "title": translate_text(candidate.title, lang),
                    "source_outlet": candidate.source_outlet,
                    "source_type": candidate.source_type,
                    "political_leaning": candidate.political_leaning,
                    "political_leaning_label": candidate.political_leaning,
                    "political_leaning_color": candidate.political_leaning_color,
                    "published_at": candidate.published_at.isoformat(),
                    "link": candidate.link,
                    "hotness": candidate.hotness,
                }
            )
            if len(existing) + len(extras) >= 4:
                return existing + extras
    return existing + extras


def aggregate_by_country(events: Iterable[Event], lang: str = "zh") -> list[dict]:
    event_list = list(events)
    bucket: dict[str, dict] = {}
    merged_events: dict[str, dict] = {}
    related_source_index = _build_related_source_index(event_list)
    for event in event_list:
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

        event_key = f"{event.country}:{event.title.strip().lower()[:80]}"
        source_item = {
            "source": event.source,
            "title": translate_text(event.title, lang),
            "source_outlet": event.source_outlet,
            "source_type": event.source_type,
            "political_leaning": event.political_leaning,
            "political_leaning_label": event.political_leaning,
            "political_leaning_color": event.political_leaning_color,
            "published_at": event.published_at.isoformat(),
            "link": event.link,
            "hotness": event.hotness,
        }

        if event_key not in merged_events:
            merged_events[event_key] = {
                "event_id": event.event_id,
                "country": event.country,
                "title": translate_text(event.title, lang),
                "source": event.source,
                "source_outlet": event.source_outlet,
                "source_type": event.source_type,
                "published_at": event.published_at.isoformat(),
                "hotness": event.hotness,
                "topic": event.topic,
                "topic_label": translate_topic(event.topic, lang),
                "topic_color": TOPIC_COLORS.get(event.topic, "#64748b"),
                "link": event.link,
                "sources": [source_item],
            }
            continue

        current = merged_events[event_key]
        current["sources"].append(source_item)
        if event.hotness > current["hotness"]:
            current["source"] = event.source
            current["source_outlet"] = event.source_outlet
            current["source_type"] = event.source_type
            current["published_at"] = event.published_at.isoformat()
            current["hotness"] = event.hotness
            current["link"] = event.link

    for event in merged_events.values():
        event["sources"] = sorted(event["sources"], key=lambda item: item["hotness"], reverse=True)
        event["sources"] = _expand_sources_for_event(event["country"], event["topic"], event["sources"], related_source_index, lang)
        event["sources"] = sorted(event["sources"], key=lambda item: item["hotness"], reverse=True)
        bucket[event["country"]]["top_events"].append(event)

    result = []
    for record in bucket.values():
        record["avg_hotness"] = round(record["avg_hotness"] / record["event_count"], 2)
        record["top_events"] = sorted(record["top_events"], key=lambda item: item["hotness"], reverse=True)[:3]
        topic_count: dict[str, int] = {}
        for event in record["top_events"]:
            topic_count[event["topic"]] = topic_count.get(event["topic"], 0) + 1
        record["top_topic"] = sorted(topic_count.items(), key=lambda item: item[1], reverse=True)[0][0]
        record["top_topic_label"] = translate_topic(record["top_topic"], lang)
        result.append(record)

    return sorted(result, key=lambda item: item["avg_hotness"], reverse=True)


def build_adaptive_panel(events: list[Event], viewport_country: str | None = None, lang: str = "zh") -> dict:
    grouped = aggregate_by_country(events, lang=lang)
    flattened: list[dict] = []
    for country in grouped:
        flattened.extend(country.get("top_events", []))
    flattened = sorted(flattened, key=lambda item: item["hotness"], reverse=True)

    global_top = [
        {
            "title": item["title"],
            "country": item["country"],
            "hotness": item["hotness"],
            "topic": item["topic"],
            "topic_label": item["topic_label"],
            "topic_color": item.get("topic_color", TOPIC_COLORS.get(item["topic"], "#64748b")),
            "source": item["source"],
            "source_type": item["source_type"],
            "link": item["link"],
            "sources": item.get("sources", []),
        }
        for item in flattened[:8]
    ]

    viewport_related = []
    if viewport_country:
        viewport_related = [
            {
                "title": item["title"],
                "country": item["country"],
                "hotness": item["hotness"],
                "topic": item["topic"],
                "topic_label": item["topic_label"],
                "topic_color": item.get("topic_color", TOPIC_COLORS.get(item["topic"], "#64748b")),
                "source": item["source"],
                "source_type": item["source_type"],
                "link": item["link"],
                "sources": item.get("sources", []),
            }
            for item in flattened
            if item["country"].lower() == viewport_country.lower()
        ][:8]

    return {
        "global_top": global_top,
        "viewport_related": viewport_related,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
