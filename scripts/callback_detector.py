#!/usr/bin/env python3
"""
Callback detector: scans filtered papers for heat surge.
If a previously filtered paper gains significant heat, triggers callback.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE / "memory" / "papers"
PAPER_INDEX = BASE / "memory" / "paper_index.json"

# Thresholds for callback trigger
CALLBACK_THRESHOLDS = {
    "hn_points_delta": 15,       # HN points increase by 15+
    "hn_comments_delta": 5,        # HN comments increase by 5+
    "citation_delta": 3,           # Citations increase by 3+
    "days_since_filtered": 30,     # Only check papers filtered within last 30 days
}


def _load_paper(arxiv_id):
    path = PAPERS_DIR / f"{arxiv_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_paper(arxiv_id, data):
    path = PAPERS_DIR / f"{arxiv_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_index_status(arxiv_id, new_status):
    if PAPER_INDEX.exists():
        index = json.loads(PAPER_INDEX.read_text(encoding="utf-8"))
        if arxiv_id in index:
            index[arxiv_id]["status"] = new_status
            PAPER_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_callbacks():
    """Scan all filtered papers and detect heat surges."""
    if not PAPERS_DIR.exists():
        print("No papers directory found")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    callbacks = []

    for f in PAPERS_DIR.glob("*.json"):
        archive = json.loads(f.read_text(encoding="utf-8"))
        arxiv_id = archive.get("arxiv_id", f.stem)

        # Only check filtered papers
        if archive.get("status") != "filtered":
            continue

        # Check if filtered recently
        status_history = archive.get("status_history", [])
        filtered_dates = [h["date"] for h in status_history if h.get("status") == "filtered"]
        if not filtered_dates:
            continue
        last_filtered = max(filtered_dates)
        days_since = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(last_filtered, "%Y-%m-%d")).days
        if days_since > CALLBACK_THRESHOLDS["days_since_filtered"]:
            continue

        # Analyze heat timeline
        heat_timeline = archive.get("heat_timeline", [])
        if len(heat_timeline) < 2:
            continue  # Need at least 2 data points to detect surge

        # Sort by date
        heat_timeline.sort(key=lambda x: x.get("date", ""))
        first = heat_timeline[0]
        latest = heat_timeline[-1]

        hn_points_delta = latest.get("hn_points", 0) - first.get("hn_points", 0)
        hn_comments_delta = latest.get("hn_comments", 0) - first.get("hn_comments", 0)
        citation_delta = latest.get("citation_count", 0) - first.get("citation_count", 0)

        triggered = False
        reasons = []
        if hn_points_delta >= CALLBACK_THRESHOLDS["hn_points_delta"]:
            triggered = True
            reasons.append(f"HN points +{hn_points_delta}")
        if hn_comments_delta >= CALLBACK_THRESHOLDS["hn_comments_delta"]:
            triggered = True
            reasons.append(f"HN comments +{hn_comments_delta}")
        if citation_delta >= CALLBACK_THRESHOLDS["citation_delta"]:
            triggered = True
            reasons.append(f"Citations +{citation_delta}")

        if triggered:
            # Update status to callback
            archive["status"] = "callback"
            archive["status_history"].append({
                "date": today,
                "status": "callback",
                "reason": "Heat surge: " + ", ".join(reasons)
            })
            _save_paper(arxiv_id, archive)
            _update_index_status(arxiv_id, "callback")

            callbacks.append({
                "arxiv_id": arxiv_id,
                "title": archive.get("title", ""),
                "previous_score": archive.get("llm_evaluations", [{}])[-1].get("score", 0),
                "reason": ", ".join(reasons),
                "hn_points_delta": hn_points_delta,
                "hn_comments_delta": hn_comments_delta,
                "citation_delta": citation_delta,
            })

    return callbacks


def format_callback_report(callbacks):
    """Format callback results as markdown."""
    if not callbacks:
        return "🔍 Callback 检测：无热度飙升的 filtered 论文。"

    lines = ["🔥 Callback Alert — 以下 filtered 论文热度飙升，建议重新关注：", ""]
    for c in callbacks:
        lines.append(f"### {c['title']} 🎯之前评分:{c['previous_score']}")
        lines.append(f"- arXiv: https://arxiv.org/abs/{c['arxiv_id']}")
        lines.append(f"- 触发原因: {c['reason']}")
        lines.append(f"- HN: +{c['hn_points_delta']}pts / +{c['hn_comments_delta']}cmt")
        lines.append(f"- Citations: +{c['citation_delta']}")
        lines.append("")

    return "\n".join(lines)


def main():
    callbacks = detect_callbacks()
    print(format_callback_report(callbacks))
    if callbacks:
        print(f"\n共计 {len(callbacks)} 篇论文触发 callback")


if __name__ == "__main__":
    main()
