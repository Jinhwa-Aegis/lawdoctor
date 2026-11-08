"""관리자 대시보드 집계 테스트"""

from datetime import date, datetime, timezone

from api.admin import _excerpt, count_citation_issues, summarize_activity


def _row(role, iso, confidence=None, meta=None):
    return {
        "role": role,
        "created_at": datetime.fromisoformat(iso),
        "confidence": confidence,
        "answer_meta": meta,
    }


def test_count_citation_issues():
    meta = {"verified_citations": [
        {"status": "verified"}, {"status": "repealed"}, {"status": "not_found"},
        {"status": "unverified"}, "깨진 값",
    ]}
    assert count_citation_issues(meta) == 2
    assert count_citation_issues(None) == 0
    assert count_citation_issues({"followups": []}) == 0


def test_summarize_activity_groups_by_kst_day():
    today = date(2026, 11, 6)
    rows = [
        # UTC 11/5 16:00 = KST 11/6 01:00 → 오늘로 집계
        _row("user", "2026-11-05T16:00:00+00:00"),
        _row("user", "2026-11-05T10:00:00+00:00"),  # KST 11/5 19:00
        _row("assistant", "2026-11-05T16:00:10+00:00", "low",
             {"verified_citations": [{"status": "not_found"}]}),
        _row("assistant", "2026-11-05T10:00:10+00:00", "high", None),
        _row("user", "2026-10-01T00:00:00+00:00"),  # 기간 밖
    ]
    out = summarize_activity(rows, days=14, today=today)
    daily = {d["date"]: d["count"] for d in out["daily_questions"]}
    assert len(out["daily_questions"]) == 14
    assert out["daily_questions"][0]["date"] == "2026-10-24"
    assert daily["2026-11-06"] == 1 and daily["2026-11-05"] == 1
    assert sum(daily.values()) == 2
    assert out["recent_answers"] == 2
    assert out["citation_issue_answers"] == 1
    assert out["low_confidence_answers"] == 1


def test_summarize_activity_accepts_naive_datetime_as_utc():
    out = summarize_activity(
        [{"role": "user", "created_at": datetime(2026, 11, 6, 1, 0), "confidence": None, "answer_meta": None}],
        days=1, today=date(2026, 11, 6),
    )
    assert out["daily_questions"] == [{"date": "2026-11-06", "count": 1}]


def test_excerpt_strips_markdown_and_truncates():
    assert _excerpt("## 결론\n**가능**합니다") == "결론 가능합니다"
    assert _excerpt("요약\n| 쟁점 | A |\n|---|---|\n| x | y |\n다음") == "요약 다음"
    long = _excerpt("가" * 300)
    assert len(long) == 241 and long.endswith("…")
