"""게시글 작성일 파싱 유틸. RAG/크롤러에서 공용으로 사용 (순환 import 방지)."""
import re
from datetime import datetime, timezone

# 인벤/마이그레이션 작성일 파싱용 패턴
_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})[.-](\d{1,2})[.-](\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?"), "datetime"),
    (re.compile(r"^(\d{4})[.-](\d{1,2})[.-](\d{1,2})T(\d{1,2}):(\d{2})"), "datetime_iso"),
    (re.compile(r"^(\d{4})[.-](\d{1,2})[.-](\d{1,2})$"), "date_only"),
    (re.compile(r"^(\d{1,2})[.-](\d{1,2})\s+(\d{1,2}):(\d{2})"), "m-d-hm"),
    (re.compile(r"^(\d{1,2})[.-](\d{1,2})$"), "m-d"),
]


def parse_post_date(date_str: str) -> datetime | None:
    """게시글 작성일 문자열을 datetime으로 파싱. 실패 시 None."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    now = datetime.now(timezone.utc)
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.match(s)
        if not m:
            continue
        try:
            if fmt == "datetime":
                g = m.groups()
                y, mo, d, h, mi = int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4])
                return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
            if fmt == "datetime_iso":
                y, mo, d, h, mi = m.groups()
                return datetime(int(y), int(mo), int(d), int(h), int(mi), tzinfo=timezone.utc)
            if fmt == "date_only":
                y, mo, d = m.groups()
                return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc)
            if fmt == "m-d-hm":
                mo, d, h, mi = m.groups()
                return datetime(now.year, int(mo), int(d), int(h), int(mi), tzinfo=timezone.utc)
            if fmt == "m-d":
                mo, d = m.groups()
                return datetime(now.year, int(mo), int(d), tzinfo=timezone.utc)
        except (ValueError, TypeError, IndexError):
            continue
    return None
