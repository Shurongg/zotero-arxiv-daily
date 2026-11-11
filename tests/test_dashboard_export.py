import json
from datetime import datetime, timezone
from types import SimpleNamespace

from zotero_arxiv_daily.dashboard_export import build_dashboard_payload, write_dashboard_payload
from zotero_arxiv_daily.protocol import Paper


def client_returning(content, captured=None):
    def create(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def paper(**kwargs):
    return Paper(source="arxiv", title="Retrieval Noise", authors=["A"], abstract="Study of retrieval noise.",
                 url="https://arxiv.org/abs/1234.5678", pdf_url="https://arxiv.org/pdf/1234.5678", **kwargs)


def test_abstract_only_card_marks_its_evidence():
    captured = {}
    value = json.dumps({"problem": "P", "method": "M", "results": "R", "relevance": "V", "limitations": "L"})
    item = paper(full_text=None)
    card = item.generate_reading_card(client_returning(value, captured), {"api_mode": "chat_completion", "generation_kwargs": {"model": "test"}})

    assert card == {"basis": "仅摘要", "problem": "P", "method": "M", "results": "R", "relevance": "V", "limitations": "L"}
    assert "如果只给摘要" in captured["messages"][1]["content"]


def test_malformed_card_returns_explicit_unknowns():
    item = paper(full_text="Extracted paper text")
    card = item.generate_reading_card(client_returning("not JSON"), {"api_mode": "chat_completion", "generation_kwargs": {"model": "test"}})

    assert card["basis"] == "提取正文"
    assert card["results"] == "暂无可靠信息"


def test_dashboard_json_excludes_full_text_and_abstract(tmp_path):
    item = paper(full_text="Private extracted text", score=7.123)
    item.tldr = "One-line summary"
    item.reading_card = {"basis": "提取正文", "problem": "P"}
    payload = build_dashboard_payload([item], datetime(2026, 11, 11, tzinfo=timezone.utc))
    target = tmp_path / "nested" / "papers-today.json"
    write_dashboard_payload([item], str(target))

    assert payload["date"] == "2026-11-11"
    assert payload["papers"][0]["score"] == 7.12
    assert "Private extracted text" not in target.read_text()
    assert "Study of retrieval noise" not in target.read_text()
    assert json.loads(target.read_text())["papers"][0]["reading_card"]["problem"] == "P"
