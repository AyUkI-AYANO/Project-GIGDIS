"""Project GIGDIS beta4.6 service entrypoint (stdlib HTTP server)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen
import re

import importlib

from pipeline import Event as HotspotEvent
from pipeline import (
    aggregate_by_country,
    build_adaptive_panel,
    fetch_events,
    filter_events_by_source_types,
    filter_events_by_topics,
    normalize_language,
)
from sources import AVAILABLE_TOPICS, COUNTRY_COORDS, RSS_SOURCES, SOURCE_TYPES, get_source_profile

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
    "market_indices": [],
    "market_last_refresh": None,
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


MARKET_INDEX_SOURCES = [
    {"index_code": "000001.SH", "stooq_symbol": "^shc", "yahoo_symbol": "000001.SS", "yfinance_symbols": ["000001.SS"], "tencent_symbols": ["s_sh000001"], "sina_symbols": ["s_sh000001"], "preferred_sources": ["tencent", "sina", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "399001.SZ", "stooq_symbol": "^szc", "yahoo_symbol": "399001.SZ", "yfinance_symbols": ["399001.SZ"], "tencent_symbols": ["s_sz399001"], "sina_symbols": ["s_sz399001"], "preferred_sources": ["tencent", "sina", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "HSI", "stooq_symbol": "^hsi", "yahoo_symbol": "^HSI", "yfinance_symbols": ["^HSI"], "tencent_symbols": ["s_hkHSI"], "sina_symbols": ["s_hkHSI", "int_hangseng"], "preferred_sources": ["tencent", "sina", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "N225", "stooq_symbol": "^nkx", "yahoo_symbol": "^N225", "yfinance_symbols": ["^N225", "NIY=F"], "tencent_symbols": ["r_JP225", "jp_nky"], "sina_symbols": ["int_nikkei", "znb_NKY"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "STI", "stooq_symbol": "^sti", "yahoo_symbol": "^STI", "yfinance_symbols": ["^STI", "ES3.SI"], "tencent_symbols": ["r_STI", "sg_sti"], "sina_symbols": ["int_sti", "znb_STI"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "NIFTY", "stooq_symbol": "^nif", "yahoo_symbol": "^NSEI", "yfinance_symbols": ["^NSEI", "NIFTYBEES.NS"], "tencent_symbols": ["r_NIFTY", "in_nifty"], "sina_symbols": ["int_nifty", "znb_NIFTY"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "DAX", "stooq_symbol": "^dax", "yahoo_symbol": "^GDAXI", "yfinance_symbols": ["^GDAXI", "EXS1.DE"], "tencent_symbols": ["r_DAX", "de_dax"], "sina_symbols": ["int_dax", "znb_DAX"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "PX1", "stooq_symbol": "^cac", "yahoo_symbol": "^FCHI", "yfinance_symbols": ["^FCHI", "CAC.PA"], "tencent_symbols": ["r_CAC40", "fr_cac"], "sina_symbols": ["int_cac", "znb_CAC"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "UKX", "stooq_symbol": "^ukx", "yahoo_symbol": "^FTSE", "yfinance_symbols": ["^FTSE", "UKX.L", "ISF.L"], "tencent_symbols": ["r_UKX", "uk_ftse"], "sina_symbols": ["int_ftse", "znb_UKX"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "DJI", "stooq_symbol": "^dji", "yahoo_symbol": "^DJI", "yfinance_symbols": ["^DJI", "DIA"], "tencent_symbols": ["usDJI"], "sina_symbols": ["int_dji", "gb_dji"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "IXIC", "stooq_symbol": "^ndq", "yahoo_symbol": "^IXIC", "yfinance_symbols": ["^IXIC", "QQQ"], "tencent_symbols": ["usIXIC"], "sina_symbols": ["int_nasdaq", "gb_ixic"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "TSX", "stooq_symbol": "^tsx", "yahoo_symbol": "^GSPTSE", "yfinance_symbols": ["^GSPTSE", "XIU.TO"], "tencent_symbols": ["r_TSX", "ca_tsx"], "sina_symbols": ["int_tsx", "znb_TSX"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "IBOV", "stooq_symbol": "^bvp", "yahoo_symbol": "^BVSP", "yfinance_symbols": ["^BVSP", "BOVA11.SA"], "tencent_symbols": ["r_IBOV", "br_ibov"], "sina_symbols": ["int_bovespa", "znb_IBOV"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
    {"index_code": "XJO", "stooq_symbol": "^asx", "yahoo_symbol": "^AXJO", "yfinance_symbols": ["^AXJO", "VAS.AX"], "tencent_symbols": ["r_ASX200", "au_asx200"], "sina_symbols": ["int_asx", "int_asx200", "znb_ASX"], "preferred_sources": ["sina", "tencent", "yfinance", "stooq", "yahoo"], "fallback_value": "N/A", "fallback_delta": "N/A"},
]


def _format_market_value(value: float) -> str:
    return f"{value:,.2f}"


def _format_market_delta(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f}%"


MARKET_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json,text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get_text(url: str, timeout: float = 6.0) -> str:
    request = Request(url, headers=MARKET_HTTP_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except URLError:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")


def _safe_float(value: str) -> float | None:
    cleaned = str(value or "").strip().replace("%", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_market_from_stooq(symbol: str) -> tuple[float, float] | None:
    payload = _http_get_text(f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcvncp&e=csv", timeout=6).strip().splitlines()
    if len(payload) < 2:
        return None
    cols = payload[1].split(",")
    close_price = _safe_float(cols[6] if len(cols) > 6 else "")
    percent_change = _safe_float(cols[10] if len(cols) > 10 else "")
    if close_price is None or percent_change is None:
        return None
    return close_price, percent_change


def _fetch_market_from_yahoo(symbol: str) -> tuple[float, float] | None:
    encoded_symbol = quote(symbol, safe="")
    payload = json.loads(
        _http_get_text(
            f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={encoded_symbol}",
            timeout=6,
        )
    )
    result = ((payload or {}).get("quoteResponse") or {}).get("result") or []
    if not result:
        return None
    quote_item = result[0] if isinstance(result[0], dict) else {}
    price = quote_item.get("regularMarketPrice")
    delta = quote_item.get("regularMarketChangePercent")
    if price is None:
        return None
    if delta is None:
        previous_close = quote_item.get("regularMarketPreviousClose")
        if previous_close in (None, 0):
            return None
        delta = (float(price) - float(previous_close)) / float(previous_close) * 100
    return float(price), float(delta)


def _fetch_market_from_yfinance(symbol: str) -> tuple[float, float] | None:
    yf_module = importlib.import_module("yfinance")
    ticker = yf_module.Ticker(symbol)
    info = getattr(ticker, "info", None) or {}
    if isinstance(info, dict):
        price = _safe_float(str(info.get("regularMarketPrice") or info.get("currentPrice") or ""))
        previous_close = _safe_float(str(info.get("regularMarketPreviousClose") or info.get("previousClose") or ""))
        if price is not None:
            if previous_close not in (None, 0):
                delta = (price - previous_close) / previous_close * 100
                return price, delta
            market_change_percent = _safe_float(str(info.get("regularMarketChangePercent") or ""))
            if market_change_percent is not None:
                return price, market_change_percent

    fast_info = getattr(ticker, "fast_info", None) or {}
    if hasattr(fast_info, "get"):
        price = _safe_float(str(fast_info.get("last_price") or fast_info.get("regular_market_price") or ""))
        previous_close = _safe_float(str(fast_info.get("previous_close") or ""))
        if price is not None and previous_close not in (None, 0):
            delta = (price - previous_close) / previous_close * 100
            return price, delta

    history = ticker.history(period="5d", interval="1d", auto_adjust=False, timeout=5)
    if history.empty or "Close" not in history:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    latest_close = float(closes.iloc[-1])
    previous_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
    if previous_close in (None, 0):
        return latest_close, 0.0
    delta = (latest_close - float(previous_close)) / float(previous_close) * 100
    return latest_close, delta


def _fetch_market_from_yfinance_candidates(symbols: list[str]) -> tuple[float, float] | None:
    for symbol in symbols:
        symbol = str(symbol).strip()
        if not symbol:
            continue
        try:
            quote = _fetch_market_from_yfinance(symbol)
        except Exception:
            quote = None
        if quote is not None:
            return quote
    return None


def _fetch_market_from_tencent(symbol: str) -> tuple[float, float] | None:
    payload = _http_get_text(f"https://qt.gtimg.cn/q={quote(symbol, safe='')}", timeout=6)
    first_line = payload.strip().splitlines()[0] if payload.strip() else ""
    if "\"" not in first_line:
        return None
    body = first_line.split('"', 1)[1].rsplit('"', 1)[0]
    cols = body.split("~")
    if len(cols) < 4:
        return None

    value = _safe_float(cols[3]) if len(cols) > 3 else None
    delta = _safe_float(cols[5]) if len(cols) > 5 else None

    if value is None:
        for token in cols:
            parsed = _safe_float(token)
            if parsed is None or parsed <= 0:
                continue
            value = parsed
            break

    if delta is None:
        previous_close = _safe_float(cols[4]) if len(cols) > 4 else None
        if value is not None and previous_close not in (None, 0):
            delta = (value - previous_close) / previous_close * 100
        else:
            for token in cols:
                parsed = _safe_float(token)
                if parsed is None:
                    continue
                if -30 <= parsed <= 30:
                    delta = parsed
                    break

    if value is None or delta is None:
        return None
    return value, delta


def _fetch_market_from_sina(symbol: str) -> tuple[float, float] | None:
    payload = _http_get_text(f"https://hq.sinajs.cn/list={quote(symbol, safe='')}", timeout=6)
    if '="' not in payload:
        return None
    body = payload.split('="', 1)[1].split('"', 1)[0]
    cols = [part.strip() for part in body.split(',')]
    if len(cols) < 2:
        return None

    value = _safe_float(cols[1]) if len(cols) > 1 else None
    delta = _safe_float(cols[3]) if len(cols) > 3 else None
    if delta is None and len(cols) > 2:
        delta = _safe_float(cols[2])

    if value is None:
        for token in cols:
            parsed = _safe_float(token)
            if parsed is None or parsed <= 0:
                continue
            value = parsed
            break

    if delta is None:
        percent_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", body)
        if percent_match:
            delta = _safe_float(percent_match.group(1))

    if delta is None and value is not None:
        previous_close = _safe_float(cols[2]) if len(cols) > 2 else None
        if previous_close not in (None, 0):
            delta = (value - previous_close) / previous_close * 100

    if value is None or delta is None:
        return None
    return value, delta


def _fetch_market_from_tencent_candidates(symbols: list[str]) -> tuple[float, float] | None:
    for symbol in symbols:
        candidate = str(symbol).strip()
        if not candidate:
            continue
        try:
            quote_data = _fetch_market_from_tencent(candidate)
        except Exception:
            quote_data = None
        if quote_data is not None:
            return quote_data
    return None


def _fetch_market_from_sina_candidates(symbols: list[str]) -> tuple[float, float] | None:
    for symbol in symbols:
        candidate = str(symbol).strip()
        if not candidate:
            continue
        try:
            quote_data = _fetch_market_from_sina(candidate)
        except Exception:
            quote_data = None
        if quote_data is not None:
            return quote_data
    return None


def _refresh_market_indices() -> None:
    previous = {item.get("index_code"): item for item in STATE.get("market_indices", []) if isinstance(item, dict)}
    refreshed: list[dict[str, str]] = []

    for item in MARKET_INDEX_SOURCES:
        index_code = item["index_code"]
        prior = previous.get(index_code, {})
        fallback_value = str(prior.get("index_value") or item["fallback_value"])
        fallback_delta = str(prior.get("index_delta") or item["fallback_delta"])
        record = {"index_code": index_code, "index_value": fallback_value, "index_delta": fallback_delta}

        quote = None
        preferred_sources = [str(source).strip().lower() for source in (item.get("preferred_sources") or []) if str(source).strip()]
        if not preferred_sources:
            preferred_sources = ["tencent", "sina", "yfinance", "stooq", "yahoo"]

        for source in preferred_sources:
            try:
                if source == "tencent":
                    tencent_symbols = item.get("tencent_symbols") or [item.get("tencent_symbol")]
                    quote = _fetch_market_from_tencent_candidates([str(symbol or "") for symbol in tencent_symbols])
                elif source == "sina":
                    sina_symbols = item.get("sina_symbols") or [item.get("sina_symbol")]
                    quote = _fetch_market_from_sina_candidates([str(symbol or "") for symbol in sina_symbols])
                elif source == "yfinance":
                    yfinance_symbols = item.get("yfinance_symbols") or [str(item.get("yahoo_symbol", ""))]
                    quote = _fetch_market_from_yfinance_candidates(list(yfinance_symbols))
                elif source == "stooq":
                    quote = _fetch_market_from_stooq(str(item.get("stooq_symbol", "")))
                elif source == "yahoo":
                    quote = _fetch_market_from_yahoo(str(item.get("yahoo_symbol", "")))
            except Exception:
                quote = None

            if quote is not None:
                break


        if quote is not None:
            close_value, change_value = quote
            record["index_value"] = _format_market_value(close_value)
            record["index_delta"] = _format_market_delta(change_value)

        refreshed.append(record)

    STATE["market_indices"] = refreshed
    STATE["market_last_refresh"] = datetime.now(timezone.utc).isoformat()



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

    conflict_events = [event for event in military if _is_conflict_event(event)]
    conflict_count = len(conflict_events)
    avg_hotness = sum(event.hotness for event in military) / military_count
    conflict_ratio = conflict_count / military_count
    spread_countries = len({event.country for event in military})

    # 使用饱和曲线避免“常态高位”，只有在冲突密度与范围显著扩大时才会接近 90+。
    count_score = 42.0 * (1.0 - math.exp(-military_count / 24.0))
    heat_score = 24.0 * ((min(avg_hotness, 100.0) / 100.0) ** 1.2)
    conflict_score = 22.0 * (conflict_ratio**1.35)
    spread_score = min(12.0, spread_countries * 0.85)

    score = count_score + heat_score + conflict_score + spread_score
    if conflict_count < 45 and score > 88.0:
        score = 88.0 + (score - 88.0) * 0.35

    return int(round(min(100.0, score)))


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
    _refresh_market_indices()


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


def _read_source_type_filters(query: dict[str, list[str]]) -> list[str]:
    values = query.get("source_types", [])
    source_types: list[str] = []
    for value in values:
        if not value:
            continue
        source_types.extend([part.strip().lower() for part in value.split(",") if part.strip()])
    return source_types


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
                    "version": "1.0-beta4.6",
                    "last_refresh": STATE["last_refresh"],
                    "event_count": len(STATE["events"]),
                    "limit_per_source": STATE["limit_per_source"],
                    "topics": AVAILABLE_TOPICS,
                    "source_types": SOURCE_TYPES,
                    "market_last_refresh": STATE["market_last_refresh"],
                }
            )

        if parsed.path == "/api/v1/sources":
            return self._json(
                {
                    "types": SOURCE_TYPES,
                    "sources": [
                        {
                            "name": source.get("name"),
                            "url": source.get("url"),
                            "credibility": source.get("credibility"),
                            "type": source.get("type", "mainstream"),
                            "outlet": get_source_profile(str(source.get("name", "")))["outlet"],
                            "political_leaning": get_source_profile(str(source.get("name", "")))["political_leaning"],
                        }
                        for source in RSS_SOURCES
                    ],
                }
            )

        if parsed.path == "/api/v1/source-content":
            source_name = query.get("source", [""])[0].strip().lower()
            if not source_name:
                return self._json({"error": "Missing source parameter"}, status=400)
            events: list[HotspotEvent] = STATE["events"]
            matched = [
                {
                    "title": event.title,
                    "summary": event.summary,
                    "country": event.country,
                    "topic": event.topic,
                    "source": event.source,
                    "source_type": event.source_type,
                    "source_outlet": event.source_outlet,
                    "political_leaning": event.political_leaning,
                    "political_leaning_color": event.political_leaning_color,
                    "published_at": event.published_at.isoformat(),
                    "hotness": event.hotness,
                    "link": event.link,
                }
                for event in events
                if source_name in event.source.lower()
            ]
            return self._json({"source": source_name, "count": len(matched), "items": matched[:30]})

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
            source_types = _read_source_type_filters(query)
            lang = _read_lang(query)
            filtered = filter_events_by_topics(events, topics)
            filtered = filter_events_by_source_types(filtered, source_types)
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
                    "active_source_types": source_types,
                    "lang": lang,
                    "countries": aggregate_by_country(filtered, lang=lang),
                    "markets": STATE["market_indices"],
                    "market_last_refresh": STATE["market_last_refresh"],
                    "global_tension": {
                        "score": latest_tension["score"],
                        "top_regions": latest_tension["top_regions"],
                        "hourly_trend": timeline,
                    },
                }
            )

        if parsed.path == "/api/v1/markets":
            return self._json(
                {
                    "last_refresh": STATE["market_last_refresh"],
                    "markets": STATE["market_indices"],
                }
            )

        if parsed.path == "/api/v1/panel":
            events: list[HotspotEvent] = STATE["events"]
            viewport_country = query.get("viewport_country", [None])[0]
            topics = _read_topic_filters(query)
            source_types = _read_source_type_filters(query)
            lang = _read_lang(query)
            filtered = filter_events_by_topics(events, topics)
            filtered = filter_events_by_source_types(filtered, source_types)
            panel = build_adaptive_panel(filtered, viewport_country, lang=lang)
            panel["active_topics"] = topics
            panel["active_source_types"] = source_types
            panel["lang"] = lang
            return self._json(panel)

        self._json({"error": "Not Found"}, status=404)


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)

    refresher = Refresher()
    refresher.start()
    print("=" * 64, flush=True)
    print("Project GIGDIS beta4.6 已启动", flush=True)
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
