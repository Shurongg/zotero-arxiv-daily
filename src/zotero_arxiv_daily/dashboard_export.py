"""Small JSON handoff for a local Obsidian dashboard."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .protocol import Paper


def build_dashboard_payload(papers: list[Paper], generated_at: datetime | None = None) -> dict:
    now = generated_at or datetime.now(timezone.utc)
    return {
        "version": 1,
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "papers": [
            {
                "title": paper.title,
                "authors": paper.authors,
                "url": paper.url,
                "pdf_url": paper.pdf_url,
                "score": round(float(paper.score), 2) if paper.score is not None else None,
                "tldr": paper.tldr or "",
                "reading_card": paper.reading_card or {},
            }
            for paper in papers
        ],
    }


def write_dashboard_payload(papers: list[Paper], output: str) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_dashboard_payload(papers), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
