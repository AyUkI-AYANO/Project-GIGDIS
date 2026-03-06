"""Project GIGDIS alpha0.2.5 service entrypoint (stdlib HTTP server)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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
from sources import AVAILABLE_TOPICS

HOST = "0.0.0.0"
PORT = 8000
REFRESH_SECONDS = 15 * 60

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

STATE: dict[str, object] = {
    "events": [],
    "last_refresh": None,
    "tension_history": [],
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
    events = fetch_events(limit_per_source=40)
    STATE["events"] = events
    STATE["last_refresh"] = datetime.now(timezone.utc).isoformat()
    tension = _compute_tension(events)
    _append_tension_history(tension, events)


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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            return self._serve_index()

        if parsed.path == "/api/v1/health":
            return self._json(
                {
                    "service": "Project GIGDIS",
                    "version": "0.2.5",
                    "last_refresh": STATE["last_refresh"],
                    "event_count": len(STATE["events"]),
                    "topics": AVAILABLE_TOPICS,
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
            return self._json(
                {
                    "last_refresh": STATE["last_refresh"],
                    "active_topics": topics,
                    "lang": lang,
                    "countries": aggregate_by_country(filtered, lang=lang),
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
    print("Project GIGDIS alpha0.2.5 已启动", flush=True)
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
