#!/usr/bin/env python3
"""
Monthly arXiv digest summarizer.
Reads daily digests from the current month, extracts high-value papers,
and generates a monthly highlight report.
"""
import json, re
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
DIGESTS_DIR = BASE / "memory" / "digests"
MONTHLY_DIR = BASE / "memory" / "monthly"
WEEKLY_DIR = BASE / "memory" / "weekly"

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def get_month_dates():
    """Get all dates in the current month."""
    today = datetime.now()
    year, month = today.year, today.month
    # Start from first day of month
    current = datetime(year, month, 1)
    dates = []
    while current.month == month:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

def get_month_label():
    return datetime.now().strftime("%Y-%m")

def extract_papers_from_digest(digest_path):
    """Extract paper entries from a daily digest markdown file."""
    if not digest_path.exists():
        return []
    text = digest_path.read_text(encoding="utf-8")
    papers = []
    
    sections = text.split("### ")
    for section in sections[1:]:
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
    month_dates = get_month_dates()
    month_label = get_month_label()
    
    all_papers = []
    for date in month_dates:
        digest_path = DIGESTS_DIR / f"{date}.md"
        papers = extract_papers_from_digest(digest_path)
        all_papers.extend(papers)
    
    if not all_papers:
        print(f"No papers found for month {month_label}")
        return
    
    # Deduplicate
    seen = set()
    unique_papers = []
    for p in all_papers:
        if p["title"] not in seen:
            seen.add(p["title"])
            unique_papers.append(p)
    
    # Sort by score
    scored = [p for p in unique_papers if "score" in p]
    unscored = [p for p in unique_papers if "score" not in p]
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    # Build monthly report
    lines = [f"# Monthly Digest — {month_label}", ""]
    lines.append(f"Total unique papers this month: {len(unique_papers)}")
    lines.append(f"High-scored papers (≥8.0): {len([p for p in scored if p['score'] >= 8.0])}")
    lines.append(f"Average score: {sum(p['score'] for p in scored) / len(scored):.1f}" if scored else "No scored papers")
    lines.append("")
    
    # Top 10 picks
    top_papers = scored[:10]
    if top_papers:
        lines.append("## 🏆 Monthly Top 10")
        lines.append("")
        for idx, p in enumerate(top_papers, 1):
            score_str = f" 🎯{p['score']}分"
            lines.append(f"### {idx}. {p['title']}{score_str}")
            if "authors" in p:
                lines.append(f"- **Authors**: {p['authors']}")
            if "date" in p:
                lines.append(f"- **Date**: {p['date']}")
            if "zh_summary" in p:
                lines.append(f"- **摘要**: {p['zh_summary']}")
            if "llm_reason" in p:
                lines.append(f"- **点评**: {p['llm_reason']}")
            if "link" in p:
                lines.append(f"- **Link**: {p['link']}")
            lines.append("")
    
    # Research trends
    if scored:
        lines.append("## 📈 Research Trends")
        lines.append("")
        # Count by category
        from collections import Counter
        cats = Counter()
        for p in scored:
            if "categories" in p:
                for c in p["categories"].split(", "):
                    cats[c.strip()] += 1
        
        lines.append("### Hot Categories")
        for cat, count in cats.most_common(10):
            lines.append(f"- {cat}: {count} papers")
        lines.append("")
        
        # Score distribution
        high = len([p for p in scored if p["score"] >= 8.0])
        mid = len([p for p in scored if 6.0 <= p["score"] < 8.0])
        low = len([p for p in scored if p["score"] < 6.0])
        lines.append("### Score Distribution")
        lines.append(f"- 🏆 Excellent (≥8.0): {high} papers")
        lines.append(f"- 📖 Good (6.0-8.0): {mid} papers")
        lines.append(f"- 📑 Skimmed (<6.0): {low} papers")
        lines.append("")
    
    # All papers index
    if scored:
        lines.append("## 📚 All Papers Index")
        lines.append("")
        for p in scored:
            score_str = f"[{p['score']}]"
            date_str = f"({p['date']})" if "date" in p else ""
            lines.append(f"- {score_str} {p['title']} {date_str}")
            if "zh_summary" in p:
                lines.append(f"  → {p['zh_summary'][:100]}...")
            if "link" in p:
                lines.append(f"  → {p['link']}")
            lines.append("")
    
    output = "\n".join(lines)
    
    # Save monthly report
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    monthly_file = MONTHLY_DIR / f"{month_label}.md"
    monthly_file.write_text(output, encoding="utf-8")
    
    print(f"Monthly digest saved to {monthly_file}")
    print(output[:2000])

if __name__ == "__main__":
    main()
