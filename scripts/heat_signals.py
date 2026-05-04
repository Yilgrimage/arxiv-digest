#!/usr/bin/env python3
"""
Heat signal collector for arXiv papers.

Unified interface for fetching multiple heat signals.
To add a new signal: implement fetch_* function and register it in HEAT_SOURCES.
"""
import json, subprocess, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "memory" / "heat_cache.json"
CACHE_TTL_SECONDS = 3600 * 6  # 6 hours

# ---------------------------------------------------------------------------
# Config: register heat sources here
# ---------------------------------------------------------------------------
HEAT_SOURCES = {
    "hn": {
        "enabled": True,
        "label": "🔥 HN",
        "fetch": "fetch_hackernews",
    },
    "citations": {
        "enabled": False,  # Requires Semantic Scholar API key
        "label": "📚 Citations",
        "fetch": "fetch_semantic_scholar",
    },
    # Future sources:
    # "reddit": {"enabled": False, "label": "📰 Reddit", "fetch": "fetch_reddit"},
    # "twitter": {"enabled": False, "label": "🐦 X", "fetch": "fetch_twitter"},
}


def _load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(data):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_fresh(cached_at):
    return (time.time() - cached_at) < CACHE_TTL_SECONDS


def _curl_json(url, timeout=15):
    r = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 5
    )
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HackerNews (Algolia) — free, no API key needed
# ---------------------------------------------------------------------------
def fetch_hackernews(arxiv_id):
    """
    Search HackerNews for arXiv paper mentions.
    Returns: {"points": int, "comments": int, "discussions": list}
    """
    url = f"https://hn.algolia.com/api/v1/search?query=arxiv%20{arxiv_id}&tags=story"
    data = _curl_json(url)
    if not data:
        return {"points": 0, "comments": 0, "discussions": []}

    hits = data.get("hits", [])
    # Filter: exact arxiv_id match in URL (allow vN suffix)
    matched = []
    for h in hits:
        story_url = h.get("url", "")
        # Match patterns: arxiv.org/abs/XXXX.XXXXX or arxiv.org/abs/XXXX.XXXXXvN
        if f"arxiv.org/abs/{arxiv_id}" in story_url:
            matched.append({
                "title": h.get("title", ""),
                "points": h.get("points", 0),
                "comments": h.get("num_comments", 0),
                "url": f"https://news.ycombinator.com/item?id={h.get('objectID', '')}",
            })

    total_points = sum(d["points"] for d in matched)
    total_comments = sum(d["comments"] for d in matched)

    return {
        "points": total_points,
        "comments": total_comments,
        "discussions": matched,
    }


# ---------------------------------------------------------------------------
# Semantic Scholar — requires API key for higher rate limits
# ---------------------------------------------------------------------------
def fetch_semantic_scholar(arxiv_id):
    """
    Fetch citation count and influential citations from Semantic Scholar.
    Returns: {"citation_count": int, "influential_citations": int}
    """
    url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=title,citationCount,influentialCitationCount"
    data = _curl_json(url, timeout=10)
    if not data:
        return {"citation_count": 0, "influential_citations": 0}
    return {
        "citation_count": data.get("citationCount", 0),
        "influential_citations": data.get("influentialCitationCount", 0),
    }


# ---------------------------------------------------------------------------
# Unified fetch
# ---------------------------------------------------------------------------
def fetch_all_heat(arxiv_id):
    """
    Fetch all enabled heat signals for a paper.
    Uses caching to avoid repeated API calls.

    Returns:
        {
            "hn": {"points": X, "comments": Y, "discussions": [...]},
            "citations": {"citation_count": Z, ...},
            "_cached_at": timestamp,
        }
    """
    cache = _load_cache()
    key = arxiv_id

    if key in cache:
        entry = cache[key]
        if _is_fresh(entry.get("_cached_at", 0)):
            return entry

    result = {"_cached_at": time.time()}

    for source_id, cfg in HEAT_SOURCES.items():
        if not cfg.get("enabled", False):
            continue
        fetch_fn_name = cfg.get("fetch", "")
        fetch_fn = globals().get(fetch_fn_name)
        if fetch_fn:
            try:
                result[source_id] = fetch_fn(arxiv_id)
            except Exception as e:
                result[source_id] = {"error": str(e)}
        else:
            result[source_id] = {"error": f"Unknown fetch function: {fetch_fn_name}"}

    cache[key] = result
    _save_cache(cache)
    return result


def format_heat_badge(heat_data):
    """Format heat signals as a compact badge string for markdown."""
    badges = []
    if "hn" in heat_data:
        hn = heat_data["hn"]
        pts = hn.get("points", 0)
        cmt = hn.get("comments", 0)
        if pts > 0 or cmt > 0:
            badges.append(f"🔥HN {pts}pts/{cmt}cmt")
    if "citations" in heat_data:
        cit = heat_data["citations"]
        cc = cit.get("citation_count", 0)
        if cc > 0:
            badges.append(f"📚{cc}cites")
    return " | ".join(badges) if badges else ""


def compute_heat_score(heat_data):
    """
    Compute a normalized heat score (0-10) from all signals.
    Tunable weights for each source.
    """
    score = 0.0

    # HN: 1 point = 0.1 score, cap at 5.0
    if "hn" in heat_data:
        hn = heat_data["hn"]
        score += min(hn.get("points", 0) * 0.1, 5.0)
        score += min(hn.get("comments", 0) * 0.2, 3.0)

    # Citations: 1 citation = 0.05 score, cap at 5.0
    if "citations" in heat_data:
        cit = heat_data["citations"]
        score += min(cit.get("citation_count", 0) * 0.05, 5.0)

    return round(min(score, 10.0), 1)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 heat_signals.py <arxiv_id>")
        sys.exit(1)

    arxiv_id = sys.argv[1]
    heat = fetch_all_heat(arxiv_id)
    print(json.dumps(heat, ensure_ascii=False, indent=2))
    print("\nBadge:", format_heat_badge(heat))
    print("Heat score:", compute_heat_score(heat))
