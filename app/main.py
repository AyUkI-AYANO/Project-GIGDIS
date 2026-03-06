"""Project GIGDIS beta1.1 service entrypoint (stdlib HTTP server)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, urlparse

from pipeline import Event as HotspotEvent
from pipeline import (
    aggregate_by_country,
    build_adaptive_panel,
    fetch_events,
    filter_events_by_topics,
    normalize_language,
)
from sources import AVAILABLE_TOPICS, COUNTRY_COORDS

HOST = "0.0.0.0"
PORT = 8000
REFRESH_SECONDS = 15 * 60
DEFAULT_LIMIT_PER_SOURCE = 40
MIN_LIMIT_PER_SOURCE = 5
MAX_LIMIT_PER_SOURCE = 100

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

STATE: dict[str, object] = {
    "events": [],
    "last_refresh": None,
    "tension_history": [],
    "limit_per_source": DEFAULT_LIMIT_PER_SOURCE,
}

CONFLICT_KEYWORDS = {
    "airstrike",
    "airstrikes",
    "bombardment",
    "clash",
    "clashes",
    "conflict",
    "drone strike",
    "hostilities",
    "invasion",
    "missile",
    "missiles",
    "offensive",
    "shelling",
    "troops",
    "ceasefire",
    "casualties",
    "wounded",
    "interception",
    "patrol",
    "readiness",
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


class Refresher(Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            refresh_hotspots()
            self._stop_event.wait(REFRESH_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()


def _compute_tension(events: list[HotspotEvent]) -> int:
    military = [event for event in events if event.topic == "military"]
    military_count = len(military)
    if military_count == 0:
        return 0
    avg_hotness = sum(event.hotness for event in military) / military_count
    count_score = min(60.0, military_count * 2.6)
    heat_score = min(40.0, avg_hotness * 0.4)
    return int(round(min(100.0, count_score + heat_score)))


def _append_tension_history(tension: int, events: list[HotspotEvent]) -> None:
    hotspots: dict[str, float] = {}
    for event in events:
        if event.topic != "military":
            continue
        hotspots[event.country] = hotspots.get(event.country, 0.0) + event.hotness

    top_regions = [
        {"region": country, "heat": round(heat, 2)}
        for country, heat in sorted(hotspots.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    history: list[dict[str, object]] = STATE.get("tension_history", [])  # type: ignore[assignment]
    history.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": tension,
            "top_regions": top_regions,
        }
    )
    STATE["tension_history"] = history[-24:]


def refresh_hotspots() -> None:
    limit_per_source = int(STATE.get("limit_per_source", DEFAULT_LIMIT_PER_SOURCE))
    events = fetch_events(limit_per_source=limit_per_source)
    STATE["events"] = events
    STATE["last_refresh"] = datetime.now(timezone.utc).isoformat()
    tension = _compute_tension(events)
    _append_tension_history(tension, events)


def _build_conflict_zones(events: list[HotspotEvent]) -> list[dict[str, object]]:
    military = [event for event in events if event.topic == "military" and _is_conflict_event(event)]
    bucket: dict[str, dict[str, object]] = {}
    for event in military:
        if event.country not in bucket:
            bucket[event.country] = {
                "country": event.country,
                "lat": event.lat,
                "lon": event.lon,
                "event_count": 0,
                "avg_hotness": 0.0,
                "headline": event.title,
            }
        record = bucket[event.country]
        record["event_count"] = int(record["event_count"]) + 1
        record["avg_hotness"] = float(record["avg_hotness"]) + event.hotness

    zones: list[dict[str, object]] = []
    for country, record in bucket.items():
        event_count = int(record["event_count"])
        avg_hotness = round(float(record["avg_hotness"]) / max(event_count, 1), 2)
        zones.append(
            {
                "country": country,
                "lat": record["lat"],
                "lon": record["lon"],
                "event_count": event_count,
                "intensity": avg_hotness,
                "headline": record["headline"],
            }
        )

    result = sorted(zones, key=lambda item: (float(item["intensity"]), int(item["event_count"])), reverse=True)
    return result[:8]


def _is_conflict_event(event: HotspotEvent) -> bool:
    text = f"{event.title} {event.summary}".lower()
    has_conflict_keyword = any(keyword in text for keyword in CONFLICT_KEYWORDS)
    has_military_context = any(keyword in text for keyword in MILITARY_CONTEXT_KEYWORDS)
    non_military_attack = "attack" in text and any(hint in text for hint in NON_MILITARY_ATTACK_HINTS)
    return has_conflict_keyword and has_military_context and not non_military_attack


def _read_limit_per_source(query: dict[str, list[str]]) -> int:
    raw = query.get("limit_per_source", [None])[0]
    if not raw:
        return int(STATE.get("limit_per_source", DEFAULT_LIMIT_PER_SOURCE))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(STATE.get("limit_per_source", DEFAULT_LIMIT_PER_SOURCE))
    return max(MIN_LIMIT_PER_SOURCE, min(MAX_LIMIT_PER_SOURCE, value))


def _read_topic_filters(query: dict[str, list[str]]) -> list[str]:
    values = query.get("topics", [])
    topics: list[str] = []
    for value in values:
        if not value:
            continue
        topics.extend([part.strip().lower() for part in value.split(",") if part.strip()])
    return topics


def _read_lang(query: dict[str, list[str]]) -> str:
    raw = query.get("lang", ["zh"])[0]
    return normalize_language(raw)


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self) -> None:
        index_path = STATIC_DIR / "index.html"
        data = index_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, relative_path: str) -> None:
        safe_path = relative_path.lstrip("/")
        file_path = (STATIC_DIR / safe_path).resolve()
        try:
            file_path.relative_to(STATIC_DIR)
        except ValueError:
            self._json({"error": "Forbidden"}, status=403)
            return

        if not file_path.exists() or not file_path.is_file():
            self._json({"error": "Not Found"}, status=404)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            return self._serve_index()

        if parsed.path.startswith("/plugins/"):
            return self._serve_static(parsed.path)

        if parsed.path == "/api/v1/health":
            return self._json(
                {
                    "service": "Project GIGDIS",
                    "version": "1.0-beta1",
                    "last_refresh": STATE["last_refresh"],
                    "event_count": len(STATE["events"]),
                    "limit_per_source": STATE["limit_per_source"],
                    "topics": AVAILABLE_TOPICS,
                }
            )

        if parsed.path == "/api/v1/refresh":
            limit_per_source = _read_limit_per_source(query)
            STATE["limit_per_source"] = limit_per_source
            refresh_hotspots()
            return self._json(
                {
                    "ok": True,
                    "last_refresh": STATE["last_refresh"],
                    "event_count": len(STATE["events"]),
                    "limit_per_source": STATE["limit_per_source"],
                }
            )

        if parsed.path == "/api/v1/hotspots":
            events: list[HotspotEvent] = STATE["events"]
            topics = _read_topic_filters(query)
            lang = _read_lang(query)
            filtered = filter_events_by_topics(events, topics)
            tension_history: list[dict] = STATE["tension_history"]  # type: ignore[assignment]
            latest_tension = tension_history[-1] if tension_history else {"score": 0, "top_regions": []}
            timeline = [
                {"timestamp": item["timestamp"], "score": item["score"]}
                for item in tension_history
            ]
            conflict_zones = _build_conflict_zones(filtered)
            return self._json(
                {
                    "last_refresh": STATE["last_refresh"],
                    "active_topics": topics,
                    "lang": lang,
                    "countries": aggregate_by_country(filtered, lang=lang),
                    "conflict_zones": conflict_zones,
                    "global_tension": {
                        "score": latest_tension["score"],
                        "top_regions": latest_tension["top_regions"],
                        "hourly_trend": timeline,
                    },
                }
            )

        if parsed.path == "/api/v1/panel":
            events: list[HotspotEvent] = STATE["events"]
            viewport_country = query.get("viewport_country", [None])[0]
            topics = _read_topic_filters(query)
            lang = _read_lang(query)
            filtered = filter_events_by_topics(events, topics)
            panel = build_adaptive_panel(filtered, viewport_country, lang=lang)
            panel["active_topics"] = topics
            panel["lang"] = lang
            return self._json(panel)

        self._json({"error": "Not Found"}, status=404)


def run() -> None:
    refresh_hotspots()
    refresher = Refresher()
    refresher.start()

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 64, flush=True)
    print("Project GIGDIS beta1.1 已启动", flush=True)
    print(f"服务地址: http://localhost:{PORT}", flush=True)
    print("在 PowerShell / 终端中按 Ctrl+C 可结束进程", flush=True)
    print("=" * 64, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n接收到 Ctrl+C，正在关闭 Project GIGDIS ...")
    finally:
        refresher.stop()
        server.server_close()
        print("服务已停止", flush=True)


if __name__ == "__main__":
    run()
