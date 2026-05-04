#!/usr/bin/env python3
"""
Semantic paper search interface.
Searches through paper archives using tags + title fuzzy matching.
"""
import json, re
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE / "memory" / "papers"
PAPER_INDEX = BASE / "memory" / "paper_index.json"
DIGESTS_DIR = BASE / "memory" / "digests"

def _load_index():
    if PAPER_INDEX.exists():
        return json.loads(PAPER_INDEX.read_text(encoding="utf-8"))
    return {}

def _load_paper(arxiv_id):
    path = PAPERS_DIR / f"{arxiv_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None

def _extract_keywords(query):
    """Extract search keywords from query text."""
    # Simple keyword extraction: remove common words, keep meaningful terms
    stopwords = {"的", "了", "和", "是", "在", "有", "什么", "最近", "有没有", "关于", "相关", "的", "the", "a", "an", "is", "are", "have", "has", "do", "does", "what", "recent", "about", "related", "any", "new"}
    words = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', query.lower())
    return [w for w in words if w not in stopwords and len(w) >= 2]

def _score_paper(paper_idx, keywords, today_str):
    """Score a paper for relevance to query."""
    score = 0.0
    tags = [t.lower() for t in paper_idx.get("tags", [])]
    title = paper_idx.get("title", "").lower()

    # Tag exact match: +3 per keyword
    for kw in keywords:
        if kw in tags:
            score += 3.0
        # Tag partial match
        for tag in tags:
            if kw in tag or tag in kw:
                score += 1.5

    # Title match: +2 per keyword
    for kw in keywords:
        if kw in title:
            score += 2.0

    # Score bonus: higher LLM score = more relevant
    llm_score = paper_idx.get("last_score", 0)
    score += llm_score * 0.3

    # Time decay: newer papers get bonus
    last_seen = paper_idx.get("last_seen", "")
    if last_seen:
        try:
            days_old = (datetime.strptime(today_str, "%Y-%m-%d") - datetime.strptime(last_seen, "%Y-%m-%d")).days
            if days_old <= 7:
                score += 2.0
            elif days_old <= 30:
                score += 1.0
            else:
                score -= days_old * 0.05  # decay after 30 days
        except Exception:
            pass

    # Status bonus: active papers get +1
    if paper_idx.get("status") == "active":
        score += 1.0

    return score

def search_papers(query, top_k=10, status_filter=None):
    """
    Search paper archives for papers matching query.

    Args:
        query: User query string (e.g., "DPO 相关的新工作")
        top_k: Number of results to return
        status_filter: "active" | "filtered" | None (all)

    Returns:
        List of dicts: [{arxiv_id, title, score, tags, last_score, status, last_seen, snippet}, ...]
    """
    index = _load_index()
    if not index:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    keywords = _extract_keywords(query)
    if not keywords:
        return []

    results = []
    for arxiv_id, paper_idx in index.items():
        if status_filter and paper_idx.get("status") != status_filter:
            continue

        score = _score_paper(paper_idx, keywords, today)
        if score <= 0:
            continue

        # Load full archive for snippet
        archive = _load_paper(arxiv_id)
        snippet = ""
        if archive and archive.get("llm_evaluations"):
            snippet = archive["llm_evaluations"][-1].get("zh_summary", "")[:150] + "..."

        results.append({
            "arxiv_id": arxiv_id,
            "title": paper_idx.get("title", ""),
            "score": round(score, 1),
            "tags": paper_idx.get("tags", []),
            "last_score": paper_idx.get("last_score", 0),
            "status": paper_idx.get("status", ""),
            "last_seen": paper_idx.get("last_seen", ""),
            "snippet": snippet,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def format_search_results(results, query):
    """Format search results as markdown for user display."""
    if not results:
        return f"未找到与「{query}」相关的论文。"

    lines = [f"🔍 检索结果：「{query}」", ""]
    lines.append(f"找到 {len(results)} 篇相关论文：")
    lines.append("")

    for idx, r in enumerate(results, 1):
        status_icon = "🟢" if r["status"] == "active" else "⚪"
        lines.append(f"{idx}. {status_icon} **{r['title']}**")
        lines.append(f"   - 评分: 🎯{r['last_score']} | 检索分: {r['score']} | 状态: {r['status']}")
        if r.get("tags"):
            lines.append(f"   - 标签: {', '.join(r['tags'])}")
        if r.get("snippet"):
            lines.append(f"   - {r['snippet']}")
        lines.append(f"   - arXiv: https://arxiv.org/abs/{r['arxiv_id']}")
        lines.append("")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--status", choices=["active", "filtered"], default=None)
    args = parser.parse_args()

    results = search_papers(args.query, top_k=args.top_k, status_filter=args.status)
    print(format_search_results(results, args.query))


if __name__ == "__main__":
    main()
