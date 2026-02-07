"""메이플스토리 인벤 게시판 크롤러.

기존 crawl.ipynb의 MapleInvenScraper를 프로덕션 모듈로 변환.
비동기(aiohttp) 기반으로 동작하며, rate limiting과 에러 핸들링을 포함합니다.
"""
import asyncio
import html as html_module
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 직업군 ID 매핑 ─────────────────────────────────────
JOB_GROUPS: dict[str, str] = {
    "2294": "전사",
    "2295": "마법사",
    "2296": "궁수",
    "2297": "도적",
    "2298": "해적",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.inven.co.kr/",
}


@dataclass
class CrawledPost:
    """크롤링된 게시글 데이터."""

    직업군: str
    직업: str
    제목: str
    본문: str
    댓글: str  # " | " 구분자로 연결된 문자열
    작성일: str
    link: str = ""
    post_id: str = ""  # 게시글 고유 ID (중복 체크용)


@dataclass
class CrawlResult:
    """크롤링 실행 결과."""

    posts: list[CrawledPost] = field(default_factory=list)
    total_jobs_crawled: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0


class InvenCrawler:
    """메이플스토리 인벤 게시판 크롤러."""

    BASE_URL = "https://www.inven.co.kr/board/maple/"

    def __init__(
        self,
        request_delay: float = 1.5,
        group_delay: float = 2.0,
        request_timeout: int = 15,
    ):
        self.request_delay = request_delay
        self.group_delay = group_delay
        self.request_timeout = request_timeout

    # ── HTTP 요청 ──────────────────────────────────────

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str | None:
        """안전한 HTTP GET 요청."""
        try:
            async with session.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            ) as resp:
                if resp.status != 200:
                    logger.warning("HTTP %d: %s", resp.status, url)
                    return None
                body = await resp.read()
                return body.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error("요청 실패 (%s): %s", url, e)
            return None

    # ── 직업 목록 수집 ─────────────────────────────────

    async def get_job_list(
        self, session: aiohttp.ClientSession, group_id: str
    ) -> list[str]:
        """직업군 내 직업 목록 수집."""
        page_html = await self._fetch(session, f"{self.BASE_URL}{group_id}")
        if not page_html:
            return []

        soup = BeautifulSoup(page_html, "html.parser")
        cate_area = soup.select_one("#new-board div.cate-area")
        if not cate_area:
            return []

        exclude = {"전체", "팁/정보", "인증글", "10추글", "즐겨찾기"}
        jobs = []
        for link in cate_area.select("a"):
            name = link.get_text(strip=True)
            if name and name not in exclude:
                jobs.append(name)
        return jobs

    # ── 댓글 수집 (API) ───────────────────────────────

    async def _get_comments(
        self, session: aiohttp.ClientSession, post_url: str
    ) -> list[str]:
        """인벤 댓글 API로 댓글 수집."""
        match = re.search(r"/board/\w+/(\d+)/(\d+)", post_url)
        if not match:
            return []

        comeidx = match.group(1)
        articlecode = match.group(2)

        api_url = "https://www.inven.co.kr/common/board/comment.json.php"
        params = {"dummy": int(time.time() * 1000)}
        data = {
            "comeidx": comeidx,
            "articlecode": articlecode,
            "sortorder": "date",
            "act": "list",
            "out": "json",
            "replynick": "",
            "replyidx": "0",
            "uploadurl": "",
            "imageposition": "",
            "videoloading": "lazy",
        }
        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.inven.co.kr",
            "Referer": post_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            async with session.post(
                api_url,
                params=params,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                json_data = await resp.json()
                comments = []
                for group in json_data.get("commentlist", []):
                    for item in group.get("list", []):
                        raw = item.get("o_comment", "")
                        if raw:
                            decoded = html_module.unescape(raw)
                            decoded = decoded.replace("&nbsp;", " ").replace("\u00a0", " ")
                            cleaned = " ".join(decoded.split())
                            if cleaned and len(cleaned) > 2:
                                comments.append(cleaned)
                return comments
        except Exception:
            return []

    # ── 게시글 상세 크롤링 ─────────────────────────────

    async def _fetch_post_detail(
        self,
        session: aiohttp.ClientSession,
        group_name: str,
        job_name: str,
        title: str,
        link: str,
    ) -> CrawledPost | None:
        """게시글 상세 페이지 크롤링."""
        page_html = await self._fetch(session, link)
        if not page_html:
            return None

        soup = BeautifulSoup(page_html, "html.parser")

        # 제목
        title_el = soup.select_one("#tbArticle div.articleTitle")
        final_title = title_el.get_text(strip=True) if title_el else title

        # 본문
        content_el = soup.select_one("#tbArticle div.articleContent")
        content = (
            content_el.get_text(separator="\n", strip=True)
            if content_el
            else "본문 없음"
        )

        # 작성일
        date_el = soup.select_one("#tbArticle div.articleDate")
        date_str = date_el.get_text(strip=True) if date_el else ""

        # 댓글
        comments = await self._get_comments(session, link)

        # 게시글 ID 추출
        match = re.search(r"/(\d+)/?$", link)
        post_id = match.group(1) if match else link

        return CrawledPost(
            직업군=group_name,
            직업=job_name,
            제목=final_title,
            본문=content,
            댓글=" | ".join(comments) if comments else "",
            작성일=date_str,
            link=link,
            post_id=post_id,
        )

    # ── 직업 게시판 크롤링 ─────────────────────────────

    async def _scrape_job_board(
        self,
        session: aiohttp.ClientSession,
        group_id: str,
        group_name: str,
        job_name: str,
        max_pages: int = 1,
        max_posts_per_page: int = 20,
    ) -> list[CrawledPost]:
        """특정 직업 게시판에서 게시글 수집."""
        posts: list[CrawledPost] = []

        for page in range(1, max_pages + 1):
            url = (
                f"{self.BASE_URL}{group_id}"
                f"?category={quote(job_name)}&p={page}"
            )
            page_html = await self._fetch(session, url)
            if not page_html:
                continue

            soup = BeautifulSoup(page_html, "html.parser")
            tbody = soup.select_one("#new-board form table tbody")
            if not tbody:
                logger.warning("[%s/%s] 게시글 목록 없음 (page %d)", group_name, job_name, page)
                continue

            rows = tbody.select("tr")
            tasks = []
            count = 0

            for row in rows:
                if "notice" in row.get("class", []):
                    continue

                title_link = row.select_one("td.tit div div a")
                if not title_link:
                    continue

                href = title_link.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = "https://www.inven.co.kr" + href

                post_title = title_link.get_text(strip=True)
                tasks.append(
                    self._fetch_post_detail(session, group_name, job_name, post_title, href)
                )
                count += 1
                if count >= max_posts_per_page:
                    break

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, CrawledPost):
                        posts.append(r)
                    elif isinstance(r, Exception):
                        logger.error("게시글 크롤링 실패: %s", r)

        return posts

    # ── 전체 크롤링 실행 ───────────────────────────────

    async def crawl(
        self,
        max_jobs_per_group: int | None = None,
        max_pages: int = 1,
        max_posts_per_page: int = 20,
        target_groups: dict[str, str] | None = None,
    ) -> CrawlResult:
        """전체 크롤링 실행.

        Args:
            max_jobs_per_group: 직업군당 수집할 최대 직업 수 (None이면 전체)
            max_pages: 직업별 수집할 페이지 수
            max_posts_per_page: 페이지당 수집할 최대 게시글 수
            target_groups: 크롤링할 직업군 (None이면 전체 5개)
        """
        groups = target_groups or JOB_GROUPS
        result = CrawlResult()
        start = time.time()

        logger.info("크롤링 시작 — 직업군: %d개", len(groups))

        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar()
        ) as session:
            for group_id, group_name in groups.items():
                logger.info("[%s] 직업군 크롤링 시작", group_name)

                # 직업 목록 수집
                jobs = await self.get_job_list(session, group_id)
                if not jobs:
                    logger.warning("[%s] 직업 목록 수집 실패", group_name)
                    result.errors += 1
                    continue

                logger.info("[%s] 직업 %d개 발견: %s", group_name, len(jobs), ", ".join(jobs[:5]))

                jobs_to_crawl = (
                    jobs if max_jobs_per_group is None else jobs[:max_jobs_per_group]
                )

                for job in jobs_to_crawl:
                    logger.info("[%s/%s] 게시판 크롤링", group_name, job)
                    try:
                        posts = await self._scrape_job_board(
                            session, group_id, group_name, job,
                            max_pages=max_pages,
                            max_posts_per_page=max_posts_per_page,
                        )
                        result.posts.extend(posts)
                        result.total_jobs_crawled += 1
                        logger.info(
                            "[%s/%s] %d개 게시글 수집",
                            group_name, job, len(posts),
                        )
                    except Exception as e:
                        logger.error("[%s/%s] 크롤링 실패: %s", group_name, job, e)
                        result.errors += 1

                    await asyncio.sleep(self.request_delay)

                await asyncio.sleep(self.group_delay)

        result.elapsed_seconds = time.time() - start
        logger.info(
            "크롤링 완료 — 게시글: %d개, 직업: %d개, 에러: %d, 소요: %.1f초",
            len(result.posts), result.total_jobs_crawled,
            result.errors, result.elapsed_seconds,
        )
        return result
