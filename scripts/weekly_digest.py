#!/usr/bin/env python3
"""
Weekly arXiv digest summarizer.
Reads daily digests from the past week, extracts high-value papers,
and generates a weekly highlight report.
"""
import json, re
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
DIGESTS_DIR = BASE / "memory" / "digests"
WEEKLY_DIR = BASE / "memory" / "weekly"
HISTORY = BASE / "memory" / "recommended_history.json"

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def get_week_dates():
    """Get dates for the current week (Monday to Sunday)."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    dates = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    return dates

def get_week_number():
    return datetime.now().strftime("%Y-W%W")

def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def extract_papers_from_digest(digest_path):
    """Extract paper entries from a daily digest markdown file."""
    if not digest_path.exists():
        return []
    text = digest_path.read_text(encoding="utf-8")
    papers = []
    
    # Find paper blocks
    # Pattern: ### Title ... followed by metadata lines
    sections = text.split("### ")
    for section in sections[1:]:  # Skip header
        lines = section.strip().split("\n")
        if not lines:
            continue
        title = lines[0].split("🎯")[0].split("🔥")[0].strip()
        
        paper = {"title": title, "raw": section}
        for line in lines:
            if line.startswith("- **Authors**:"):
                paper["authors"] = line.replace("- **Authors**:", "").strip()
            elif line.startswith("- **Date**:"):
                paper["date"] = line.replace("- **Date**:", "").strip()
            elif line.startswith("- **Categories**:"):
                paper["categories"] = line.replace("- **Categories**:", "").strip()
            elif line.startswith("- **Link**:"):
                match = re.search(r'\[(.*?)\]\((.*?)\)', line)
                if match:
                    paper["link"] = match.group(2)
            elif line.startswith("- **摘要**:"):
                paper["zh_summary"] = line.replace("- **摘要**:", "").strip()
            elif line.startswith("- **🤖 LLM点评**:"):
                paper["llm_reason"] = line.replace("- **🤖 LLM点评**:", "").strip()
            elif "🎯LLM评分:" in line:
                match = re.search(r'🎯LLM评分:([\d.]+)', line)
                if match:
                    paper["score"] = float(match.group(1))
        papers.append(paper)
    return papers

def main():
    week_dates = get_week_dates()
    week_num = get_week_number()
    
    all_papers = []
    for date in week_dates:
        digest_path = DIGESTS_DIR / f"{date}.md"
        papers = extract_papers_from_digest(digest_path)
        all_papers.extend(papers)
    
    if not all_papers:
        print(f"No papers found for week {week_num}")
        return
    
    # Deduplicate by title
    seen = set()
    unique_papers = []
    for p in all_papers:
        if p["title"] not in seen:
            seen.add(p["title"])
            unique_papers.append(p)
    
    # Sort by score if available
    scored = [p for p in unique_papers if "score" in p]
    unscored = [p for p in unique_papers if "score" not in p]
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    # Build weekly report
    lines = [f"# Weekly Digest — {week_num}", ""]
    lines.append(f"Period: {week_dates[0]} to {week_dates[-1]}")
    lines.append(f"Total unique papers: {len(unique_papers)}")
    lines.append(f"High-scored papers (≥8.0): {len([p for p in scored if p['score'] >= 8.0])}")
    lines.append("")
    
    # Top picks
    top_papers = scored[:5]
    if top_papers:
        lines.append("## 🏆 Weekly Top Picks")
        lines.append("")
        for p in top_papers:
            score_str = f" 🎯{p['score']}分" if "score" in p else ""
            lines.append(f"### {p['title']}{score_str}")
            if "authors" in p:
                lines.append(f"- **Authors**: {p['authors']}")
            if "date" in p:
                lines.append(f"- **Date**: {p['date']}")
            if "categories" in p:
                lines.append(f"- **Categories**: {p['categories']}")
            if "zh_summary" in p:
                lines.append(f"- **摘要**: {p['zh_summary']}")
            if "llm_reason" in p:
                lines.append(f"- **点评**: {p['llm_reason']}")
            if "link" in p:
                lines.append(f"- **Link**: {p['link']}")
            lines.append("")
    
    # All papers by category
    if scored:
        lines.append("## 📊 All Scored Papers")
        lines.append("")
        for p in scored:
            score_str = f" 🎯{p['score']}分"
            lines.append(f"- **{p['title']}**{score_str}")
            if "zh_summary" in p:
                lines.append(f"  - {p['zh_summary']}")
            lines.append("")
    
    output = "\n".join(lines)
    
    # Save weekly report
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    weekly_file = WEEKLY_DIR / f"{week_num}.md"
    weekly_file.write_text(output, encoding="utf-8")
    
    print(f"Weekly digest saved to {weekly_file}")
    print(output[:2000])

if __name__ == "__main__":
    main()
