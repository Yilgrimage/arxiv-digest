#!/usr/bin/env python3
"""
Enhanced arXiv digest generator.
Supports: topic search, alphaxiv trending scrape, HuggingFace Daily Papers,
recommendation history, detailed formatting with repeat detection,
and LLM-ready raw output for rerank.
"""
import json, subprocess, xml.etree.ElementTree as ET, urllib.parse, re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
CONFIG_TOPICS = BASE / "config" / "topics.json"
CONFIG_PREFS = BASE / "config" / "preferences.json"
LOG = BASE / "memory" / "RESEARCH_LOG.md"
HISTORY = BASE / "memory" / "recommended_history.json"
RAW_OUT = BASE / "memory" / "daily_raw.json"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom"
}

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_url(url, timeout=60):
    result = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 10
    )
    return result.stdout

def fetch_huggingface_papers(max_papers=10):
    """Scrape HuggingFace Daily Papers page for today's papers."""
    html = fetch_url("https://huggingface.co/papers", timeout=30)
    if not html:
        return []
    # Extract paper IDs like /papers/2605.00658
    ids = re.findall(r'/papers/(\d{4}\.\d+)', html)
    seen = set()
    unique_ids = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    if not unique_ids:
        return []
    papers = fetch_by_ids(unique_ids[:max_papers * 2])
    return papers[:max_papers]

def fetch_alphaxiv_ids(max_ids=20):
    """Scrape alphaxiv.org homepage for trending paper IDs."""
    html = fetch_url("https://alphaxiv.org/", timeout=30)
    if not html:
        return []
    ids = re.findall(r'\b(\d{4}\.\d+)(?:v\d+)?\b', html)
    # Deduplicate while preserving order
    seen = set()
    out = []
    for raw_id in ids:
        if raw_id not in seen:
            seen.add(raw_id)
            out.append(raw_id)
    return out[:max_ids]

def fetch_by_ids(ids, count_per_batch=20):
    """Fetch papers by arXiv ID list via arXiv API."""
    all_papers = []
    for i in range(0, len(ids), count_per_batch):
        batch = ids[i:i + count_per_batch]
        id_str = ",".join(batch)
        url = f"https://export.arxiv.org/api/query?id_list={id_str}&max_results={len(batch)}"
        xml = fetch_url(url)
        if xml:
            all_papers.extend(parse_arxiv_xml(xml))
    return all_papers

def fetch_by_topic(topic, count=5):
    """Fetch papers by keyword search."""
    q = urllib.parse.quote(topic)
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={count}&sortBy=submittedDate&sortOrder=descending"
    xml = fetch_url(url)
    if xml:
        return parse_arxiv_xml(xml)
    return []

def parse_arxiv_xml(xml_text):
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        summary_el = entry.find("atom:summary", NS)
        published_el = entry.find("atom:published", NS)
        updated_el = entry.find("atom:updated", NS)
        comment_el = entry.find("arxiv:comment", NS)
        authors = entry.findall("atom:author/atom:name", NS)
        categories = entry.findall("atom:category", NS)

        pdf_link = None
        abs_link = None
        for link in entry.findall("atom:link", NS):
            rel = link.get("rel")
            typ = link.get("type", "")
            href = link.get("href", "")
            if rel == "related" and typ == "application/pdf":
                pdf_link = href
            elif rel == "alternate" and typ == "text/html":
                abs_link = href

        # Extract arXiv ID from URL
        arxiv_id = ""
        if abs_link:
            m = re.search(r'/(\d+\.\d+)(v\d+)?$', abs_link)
            if m:
                arxiv_id = m.group(1)

        papers.append({
            "arxiv_id": arxiv_id,
            "title": clean_text(title_el.text) if title_el is not None else "",
            "summary": clean_text(summary_el.text) if summary_el is not None else "",
            "published": (published_el.text or "")[:10] if published_el is not None else "",
            "updated": (updated_el.text or "")[:10] if updated_el is not None else "",
            "comment": clean_text(comment_el.text) if comment_el is not None else "",
            "authors": [a.text for a in authors if a.text and a.text.strip()],
            "categories": [c.get("term", "") for c in categories],
            "pdf": pdf_link,
            "abs": abs_link,
        })
    return papers

def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split())

def load_history():
    data = load_json(HISTORY)
    return data.get("papers", {})

def update_history(papers):
    history = load_history()
    today = today_str()
    for p in papers:
        aid = p.get("arxiv_id") or p.get("title", "")
        if not aid:
            continue
        if aid not in history:
            history[aid] = {
                "title": p["title"],
                "first_seen": today,
                "times_recommended": 0,
                "last_recommended": None,
                "dates": []
            }
        if today not in history[aid]["dates"]:
            history[aid]["dates"].append(today)
            history[aid]["times_recommended"] = len(history[aid]["dates"])
        history[aid]["last_recommended"] = today
        history[aid]["title"] = p["title"]
    save_json(HISTORY, {"papers": history})
    return history

def format_authors(authors):
    if not authors:
        return "Unknown"
    if len(authors) <= 3:
        return ", ".join(authors)
    return f"{', '.join(authors[:3])} et al. ({len(authors)} authors)"

def format_paper(paper, history, prefs, heat_source=None, llm_score=None, llm_reason=None, llm_zh_summary=None):
    aid = paper.get("arxiv_id") or paper.get("title", "")
    h = history.get(aid, {})
    times = h.get("times_recommended", 0)
    threshold = prefs.get("summary", {}).get("repeated_threshold", 2)
    max_len = prefs.get("summary", {}).get("max_length", 800)
    is_repeated = times >= threshold

    lines = []
    title_line = f"### {paper['title']}"
    badges = []
    if is_repeated:
        badges.append(f"🔥🔥×{times}")
    if heat_source:
        badges.append(heat_source)
    if llm_score is not None:
        badges.append(f"🎯LLM评分:{llm_score}/10")
    if badges:
        title_line += " " + " ".join(badges)
    lines.append(title_line)

    lines.append(f"- **Authors**: {format_authors(paper['authors'])}")
    lines.append(f"- **Date**: {paper['published']}")
    if paper.get("categories"):
        lines.append(f"- **Categories**: {', '.join(paper['categories'])}")
    if paper.get("comment"):
        lines.append(f"- **Note**: {paper['comment']}")
    lines.append(f"- **Link**: [{paper['abs']}]({paper['abs']})")
    lines.append(f"- **PDF**: [{paper['pdf']}]({paper['pdf']})")

    summary = paper.get("summary", "")
    if llm_zh_summary:
        zh = llm_zh_summary
        if len(zh) > max_len:
            zh = zh[:max_len].rsplit(" ", 1)[0] + " ..."
        lines.append(f"- **摘要**: {zh}")
        en = summary[:max_len].rsplit(" ", 1)[0] + " ..." if len(summary) > max_len else summary
        lines.append(f"- **Abstract**: {en}")
    else:
        display_summary = summary
        if len(display_summary) > max_len:
            display_summary = display_summary[:max_len].rsplit(" ", 1)[0] + " ..."
        lines.append(f"- **Summary**: {display_summary}")

    if llm_reason:
        lines.append(f"- **🤖 LLM点评**: {llm_reason}")
    if is_repeated:
        lines.append(f"- **🚨 推荐理由**: 该论文已连续多次出现在推荐列表中，说明社区讨论热度持续走高，建议重点关注。")

    lines.append("")
    return "\n".join(lines)

def build_section(title, papers, history, prefs, heat_source=None, llm_scores=None):
    if not papers:
        return [f"## {title}", "", "_暂无新论文。_", ""]
    lines = [f"## {title}", ""]
    for idx, p in enumerate(papers):
        aid = p.get("arxiv_id") or p.get("title", "")
        score = llm_scores.get(aid) if llm_scores else None
        lines.append(format_paper(p, history, prefs, heat_source=heat_source,
            llm_score=score.get("score") if score else None,
            llm_reason=score.get("reason") if score else None,
            llm_zh_summary=score.get("zh_summary") if score else None))
    return lines

def compute_paper_features(paper, topics):
    """Compute heuristic features for pre-ranking."""
    title = paper.get("title", "").lower()
    summary = paper.get("summary", "").lower()
    text = title + " " + summary
    features = {
        "topic_match_count": sum(1 for t in topics if t.lower() in text),
        "is_recent": paper.get("published", "") >= today_str(),
        "has_comment": bool(paper.get("comment")),
        "author_count": len(paper.get("authors", [])),
    }
    return features

def pre_rank_papers(papers, topics, history):
    """Pre-rank papers using heuristic scoring before LLM rerank."""
    def score(p):
        aid = p.get("arxiv_id") or p.get("title", "")
        h = history.get(aid, {})
        feats = compute_paper_features(p, topics)
        s = 0
        s += feats["topic_match_count"] * 3
        s += h.get("times_recommended", 0) * 2
        s += 1 if feats["is_recent"] else 0
        s += 1 if feats["has_comment"] else 0
        s += min(feats["author_count"], 5) * 0.5
        return s
    return sorted(papers, key=score, reverse=True)

def build_raw_data(topic_papers, cross_papers, hf_papers, history, prefs, topics):
    """Build structured raw data for LLM rerank."""
    all_sources = []
    seen = set()
    for p in topic_papers:
        aid = p.get("arxiv_id") or p.get("title", "")
        if aid not in seen:
            seen.add(aid)
            p["sources"] = ["arxiv-topic"]
            p["features"] = compute_paper_features(p, topics)
            all_sources.append(p)
    for p in cross_papers:
        aid = p.get("arxiv_id") or p.get("title", "")
        existing = next((x for x in all_sources if (x.get("arxiv_id") or x.get("title")) == aid), None)
        if existing:
            existing["sources"] = list(set(existing.get("sources", []) + ["alphaxiv-trending"]))
        elif aid not in seen:
            seen.add(aid)
            p["sources"] = ["alphaxiv-trending"]
            p["features"] = compute_paper_features(p, topics)
            all_sources.append(p)
    for p in hf_papers:
        aid = p.get("arxiv_id") or p.get("title", "")
        existing = next((x for x in all_sources if (x.get("arxiv_id") or x.get("title")) == aid), None)
        if existing:
            existing["sources"] = list(set(existing.get("sources", []) + ["huggingface-daily"]))
        elif aid not in seen:
            seen.add(aid)
            p["sources"] = ["huggingface-daily"]
            p["features"] = compute_paper_features(p, topics)
            all_sources.append(p)

    # Pre-rank
    all_sources = pre_rank_papers(all_sources, topics, history)

    raw = {
        "date": today_str(),
        "topics": topics,
        "preferences": prefs,
        "total_papers": len(all_sources),
        "papers": []
    }
    for p in all_sources:
        aid = p.get("arxiv_id") or p.get("title", "")
        h = history.get(aid, {})
        raw["papers"].append({
            "arxiv_id": p.get("arxiv_id", ""),
            "title": p["title"],
            "summary": p["summary"][:500] + "..." if len(p["summary"]) > 500 else p["summary"],
            "authors": p.get("authors", []),
            "published": p.get("published", ""),
            "categories": p.get("categories", []),
            "comment": p.get("comment", ""),
            "sources": p.get("sources", []),
            "features": p.get("features", {}),
            "history": {
                "times_recommended": h.get("times_recommended", 0),
                "first_seen": h.get("first_seen", ""),
                "last_recommended": h.get("last_recommended", "")
            },
            "links": {"abs": p.get("abs"), "pdf": p.get("pdf")}
        })
    return raw

def generate_rerank_prompt(raw_data):
    """Generate a prompt for LLM to rerank papers."""
    topics = raw_data["topics"]
    total_all = raw_data.get("total_papers", len(raw_data.get("papers", [])))
    lines = [
        "# LLM Paper Rerank Task",
        "",
        f"Date: {raw_data['date']}",
        f"Topics of interest: {', '.join(topics)}",
        f"Total papers to evaluate: {total_all}",
        "",
        "Instructions:",
        "1. For each paper below, evaluate:",
        "   - relevance to topics (1-10): LLM post-training, agentic RL, LLM agent, RL reasoning, RLHF, DPO, test-time compute, self-play LLM",
        "   - novelty (1-10)",
        "   - impact (1-10)",
        "2. Score = round((relevance*2 + novelty + impact) / 4, 1)",
        "3. Provide zh_summary: 2-3 sentences in Chinese covering: (a) core method/approach, (b) key finding or insight, (c) significance or impact. Be specific, not vague.",
        "4. Provide reason: 2-3 sentences in Chinese explaining the score. Analyze specific strengths, limitations, and why it matters to the user's research interests.",
        "5. Output JSON: {arxiv_id: {score, relevance, novelty, impact, reason, zh_summary}}",
        "",
        "Papers:"
    ]
    for p in raw_data["papers"]:
        lines.append("")
        lines.append(f"--- {p['arxiv_id']} ---")
        lines.append(f"Title: {p['title']}")
        lines.append(f"Sources: {', '.join(p['sources'])}")
        lines.append(f"Categories: {', '.join(p['categories'])}")
        lines.append(f"History: recommended {p['history']['times_recommended']} times")
        lines.append(f"Summary: {p['summary']}")
    lines.append("")
    lines.append("Output valid JSON only.")
    return "\n".join(lines)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", action="store_true", help="Output raw JSON for LLM rerank")
    parser.add_argument("--rerank-json", type=str, help="Path to LLM rerank JSON output")
    parser.add_argument("--output", "-o", type=str, help="Output file path (default stdout)")
    args = parser.parse_args()

    prefs = load_json(CONFIG_PREFS)
    topics_cfg = load_json(CONFIG_TOPICS)
    topics = topics_cfg.get("topics", [])
    per_topic = topics_cfg.get("per_topic_count", 5)

    # 1. Fetch topic papers
    topic_papers = []
    seen = set()
    for topic in topics:
        papers = fetch_by_topic(topic, per_topic)
        for p in papers:
            if p["title"] not in seen:
                seen.add(p["title"])
                topic_papers.append(p)

    # 2. Fetch cross-domain trending from alphaxiv
    cross_papers = []
    cross_cfg = prefs.get("cross_domain", {})
    if cross_cfg.get("enabled", True):
        max_cross = cross_cfg.get("max_papers", 5)
        ids = fetch_alphaxiv_ids(max_ids=max_cross * 2)
        if ids:
            papers = fetch_by_ids(ids)
            for p in papers:
                if p["title"] not in seen:
                    seen.add(p["title"])
                    cross_papers.append(p)
            cross_papers = cross_papers[:max_cross]

    # 3. Fetch HuggingFace Daily Papers
    hf_papers = []
    hf_cfg = prefs.get("huggingface", {})
    if hf_cfg.get("enabled", True):
        max_hf = hf_cfg.get("max_papers", 5)
        papers = fetch_huggingface_papers(max_papers=max_hf)
        for p in papers:
            if p["title"] not in seen:
                seen.add(p["title"])
                hf_papers.append(p)
        hf_papers = hf_papers[:max_hf]

    # 4. Update history
    all_papers = topic_papers + cross_papers + hf_papers
    history = update_history(all_papers)

    # 5. If --raw, output structured JSON and prompt, then exit
    if args.raw:
        raw_data = build_raw_data(topic_papers, cross_papers, hf_papers, history, prefs, topics)
        # Include ALL papers for parallel batch processing
        raw_data["total_papers"] = len(raw_data["papers"])
        save_json(RAW_OUT, raw_data)
        print(f"Raw data saved to {RAW_OUT} ({len(raw_data['papers'])} papers total)")
        return

    # 6. Load LLM rerank scores if provided, fill missing with default 5.0
    llm_scores = {}
    if args.rerank_json and Path(args.rerank_json).exists():
        llm_scores = load_json(Path(args.rerank_json))
        # Fill missing papers with default score
        for p in all_papers:
            aid = p.get("arxiv_id") or p.get("title", "")
            if aid not in llm_scores:
                llm_scores[aid] = {"score": 5.0, "reason": "相关性较低，未详细评估", "relevance": 5, "novelty": 5, "impact": 5, "zh_summary": ""}

    # 6.5 Filter low-score papers if configured
    filter_cfg = prefs.get("llm_rerank", {})
    filter_threshold = filter_cfg.get("filter_threshold", 0)
    filter_enabled = filter_cfg.get("filter_low_score", False)
    filtered_out = 0
    if llm_scores and filter_enabled and filter_threshold > 0:
        def passes_filter(p):
            aid = p.get("arxiv_id") or p.get("title", "")
            s = llm_scores.get(aid, {}).get("score", 0)
            return s >= filter_threshold
        filtered_topic = [p for p in topic_papers if passes_filter(p)]
        filtered_cross = [p for p in cross_papers if passes_filter(p)]
        filtered_hf = [p for p in hf_papers if passes_filter(p)]
        filtered_out = (len(topic_papers) - len(filtered_topic)) + (len(cross_papers) - len(filtered_cross)) + (len(hf_papers) - len(filtered_hf))
        topic_papers = filtered_topic
        cross_papers = filtered_cross
        hf_papers = filtered_hf
        all_papers = topic_papers + cross_papers + hf_papers

    # 7. Pre-rank all papers
    all_papers = pre_rank_papers(all_papers, topics, history)

    # 8. Build digest
    date = today_str()
    digest = [f"# ArXiv Daily Digest — {date}", ""]

    # Stats
    digest.append("## 📊 今日概览")
    digest.append("")
    digest.append(f"- 关注领域: {len(topic_papers)} 篇")
    digest.append(f"- 跨领域热门: {len(cross_papers)} 篇")
    digest.append(f"- HuggingFace Daily: {len(hf_papers)} 篇")
    digest.append(f"- 去重后总计: {len(all_papers)} 篇")
    if llm_scores:
        high_score = sum(1 for s in llm_scores.values() if s.get("score", 0) >= 8)
        digest.append(f"- 🎯 LLM高推荐（≥8分）: {high_score} 篇")
    if filtered_out > 0:
        digest.append(f"- 🗑️ 已过滤低相关论文（<{filter_threshold}分）: {filtered_out} 篇")
    repeated = [p for p in all_papers
                if history.get(p.get("arxiv_id") or p.get("title", ""), {}).get("times_recommended", 0)
                >= prefs.get("summary", {}).get("repeated_threshold", 2)]
    if repeated:
        digest.append(f"- 🔥🔥 持续热门: {len(repeated)} 篇")
    digest.append("")

    # Top recommendations (if LLM reranked)
    if llm_scores:
        scored = [(p, llm_scores.get(p.get("arxiv_id") or p.get("title", ""), {}).get("score", 0)) for p in all_papers]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_papers = [p for p, s in scored if s >= 7][:10]
        if top_papers:
            digest.extend(build_section("🎯 LLM精选推荐（Top Picks）", top_papers, history, prefs, llm_scores=llm_scores))

    # Topic section
    digest.extend(build_section(
        prefs.get("topics", {}).get("label", "📌 关注领域"),
        topic_papers, history, prefs
    ))

    # Cross-domain section
    if cross_papers:
        digest.extend(build_section(
            cross_cfg.get("label", "🔥 跨领域热门"),
            cross_papers, history, prefs,
            heat_source="🔥 alphaxiv trending"
        ))

    # HuggingFace section
    if hf_papers:
        digest.extend(build_section(
            hf_cfg.get("label", "🤗 HuggingFace Daily"),
            hf_papers, history, prefs,
            heat_source="🤗 HuggingFace"
        ))

    output = "\n".join(digest)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Digest saved to {args.output}")
    else:
        print(output)

    # 9. Save to daily file (per-date)
    daily_file = LOG.parent / "digests" / f"{date}.md"
    daily_file.parent.mkdir(parents=True, exist_ok=True)
    daily_file.write_text(output, encoding="utf-8")

    # 10. Append to cumulative log
    if prefs.get("output", {}).get("include_log", True):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n\n--- {date} ---\n\n")
            f.write(f"[Full report: digests/{date}.md]\n")
            f.write("\n".join(digest[:3]))  # Just header + stats anchor
            f.write("\n")

if __name__ == "__main__":
    main()
