"""인벤 크롤러 단위 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.inven_crawler import (
    CrawledPost,
    InvenCrawler,
    JOB_GROUPS,
)


class TestInvenCrawlerJobList:
    """직업 목록 수집 테스트."""

    @pytest.mark.asyncio
    async def test_get_job_list_parses_html(self):
        """HTML에서 직업 목록을 정상 파싱."""
        html = """
        <div id="new-board">
            <div class="cate-area">
                <a>전체</a>
                <a>히어로</a>
                <a>팔라딘</a>
                <a>다크나이트</a>
            </div>
        </div>
        """
        crawler = InvenCrawler()
        session = AsyncMock()
        with patch.object(crawler, "_fetch", return_value=html):
            jobs = await crawler.get_job_list(session, "2294")

        assert "히어로" in jobs
        assert "팔라딘" in jobs
        assert "다크나이트" in jobs
        assert "전체" not in jobs  # 제외 키워드

    @pytest.mark.asyncio
    async def test_get_job_list_returns_empty_on_failure(self):
        """HTTP 실패 시 빈 리스트 반환."""
        crawler = InvenCrawler()
        session = AsyncMock()
        with patch.object(crawler, "_fetch", return_value=None):
            jobs = await crawler.get_job_list(session, "2294")

        assert jobs == []

    @pytest.mark.asyncio
    async def test_get_job_list_excludes_special_items(self):
        """팁/정보, 인증글 등 특수 카테고리 제외."""
        html = """
        <div id="new-board">
            <div class="cate-area">
                <a>전체</a>
                <a>팁/정보</a>
                <a>인증글</a>
                <a>10추글</a>
                <a>즐겨찾기</a>
                <a>아크</a>
            </div>
        </div>
        """
        crawler = InvenCrawler()
        session = AsyncMock()
        with patch.object(crawler, "_fetch", return_value=html):
            jobs = await crawler.get_job_list(session, "2294")

        assert jobs == ["아크"]


class TestCrawledPost:
    """CrawledPost 데이터 클래스 테스트."""

    def test_create_post(self):
        """게시글 객체 생성."""
        post = CrawledPost(
            직업군="전사",
            직업="아크",
            제목="테스트 제목",
            본문="테스트 본문",
            댓글="댓글1 | 댓글2",
            작성일="2025-01-01",
            link="https://example.com/1",
            post_id="12345",
        )
        assert post.직업 == "아크"
        assert post.post_id == "12345"

    def test_post_empty_comments(self):
        """댓글이 없는 게시글."""
        post = CrawledPost(
            직업군="전사", 직업="아크", 제목="제목",
            본문="본문", 댓글="", 작성일="",
        )
        assert post.댓글 == ""


class TestInvenCrawlerConfig:
    """크롤러 설정 테스트."""

    def test_default_config(self):
        """기본 설정값 확인."""
        crawler = InvenCrawler()
        assert crawler.request_delay == 1.5
        assert crawler.group_delay == 2.0
        assert crawler.request_timeout == 15

    def test_custom_config(self):
        """커스텀 설정."""
        crawler = InvenCrawler(request_delay=0.5, group_delay=1.0, request_timeout=10)
        assert crawler.request_delay == 0.5
        assert crawler.group_delay == 1.0

    def test_job_groups_defined(self):
        """직업군 매핑이 5개 정의됨."""
        assert len(JOB_GROUPS) == 5
        assert "전사" in JOB_GROUPS.values()
        assert "마법사" in JOB_GROUPS.values()
        assert "궁수" in JOB_GROUPS.values()
        assert "도적" in JOB_GROUPS.values()
        assert "해적" in JOB_GROUPS.values()
