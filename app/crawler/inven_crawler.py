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

# ── 직업군 ID 매핑 (직업별 게시판) ─────────────────────
JOB_GROUPS: dict[str, str] = {
    "2294": "전사",
    "2295": "마법사",
    "2296": "궁수",
    "2297": "도적",
    "2298": "해적",
}

# ── 단일 게시판 ID 매핑 (직업 하위 없음: 공지/이벤트/팁 등) ─
# 2314: 실시간 소식 게시판 — 공지, 이벤트, 업데이트, 패치노트 등
# 2304: 팁과 노하우 게시판 — 사냥/보스/아이템/전문기술 등 팁
FLAT_BOARDS: dict[str, str] = {
    "2314": "실시간소식",
    "2304": "팁과노하우",
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

    # ── 본문 텍스트 정리 ──────────────────────────────

    # 본문 끝에 붙는 노이즈 패턴 (목록|댓글 버튼, 추천/공유, 유저 프로필 등)
    _NOISE_PATTERNS = [
        # "목록 | 댓글(N)" 부터 이후 전부 제거
        re.compile(r"목록\s*\|?\s*댓글\s*\(.*", re.DOTALL),
        # "N 공유 스크랩 신고하기" 패턴
        re.compile(r"\d+\s*공유\s*스크랩\s*신고하기.*", re.DOTALL),
        # "추천 확인" 이후 프로필 영역
        re.compile(r"추천\s*확인.*", re.DOTALL),
        # 유저 프로필: "레벨 경험치 ... 포인트 이니 베니 제니 명성 획득스킬"
        re.compile(r"(EXP|경험치)\s*[\d,]+\s*\(.*", re.DOTALL),
        # 인벤 레벨/포인트 블록
        re.compile(r"(인벤쪽지|이니힐링|더보기)\s*펼치기.*", re.DOTALL),
    ]

    @staticmethod
    def _clean_content(raw: str) -> str:
        """크롤링된 본문에서 노이즈(버튼, 프로필 등)를 제거."""
        text = raw
        for pattern in InvenCrawler._NOISE_PATTERNS:
            text = pattern.sub("", text)
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

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

        # 본문: 불필요한 하위 요소 제거 후 텍스트 추출
        content_el = soup.select_one("#tbArticle div.articleContent")
        if content_el:
            # 좋아요/공유/스크랩/신고 버튼 영역
            for sel in [
                "div.articleBtm", "div.articleFoot", "div.articleWriter",
                "div.ven_wrap", "div.articleGood", "div.articleBookmark",
                "div.articleShareBtn", "div.articleReportBtn",
                "div.prev-next", "div.cmtAll", "div.bot-area",
                "script", "style", "iframe",
            ]:
                for el in content_el.select(sel):
                    el.decompose()
            raw_content = content_el.get_text(separator="\n", strip=True)
            content = self._clean_content(raw_content)
        else:
            content = "본문 없음"

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

    # ── 단일 게시판 크롤링 (직업 하위 없음: 2314 실시간소식, 2304 팁과노하우) ─

    async def _scrape_flat_board(
        self,
        session: aiohttp.ClientSession,
        board_id: str,
        board_label: str,
        max_pages: int = 1,
        max_posts_per_page: int = 20,
        skip_notice: bool = False,
    ) -> list[CrawledPost]:
        """단일 게시판(실시간 소식 / 팁과 노하우)에서 게시글 수집.
        직업군='정보공유', 직업=board_label(실시간소식|팁과노하우)로 저장.
        """
        posts: list[CrawledPost] = []
        group_name = "정보공유"

        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}{board_id}?p={page}"
            page_html = await self._fetch(session, url)
            if not page_html:
                continue

            soup = BeautifulSoup(page_html, "html.parser")
            tbody = soup.select_one("#new-board form table tbody")
            if not tbody:
                logger.warning("[%s/%s] 게시글 목록 없음 (page %d)", group_name, board_label, page)
                continue

            rows = tbody.select("tr")
            tasks = []
            count = 0

            for row in rows:
                if skip_notice and "notice" in row.get("class", []):
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
                    self._fetch_post_detail(session, group_name, board_label, post_title, href)
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
        include_flat_boards: bool = True,
        flat_boards: dict[str, str] | None = None,
        flat_board_pages: int = 1,
        flat_board_posts_per_page: int = 20,
    ) -> CrawlResult:
        """전체 크롤링 실행.

        Args:
            max_jobs_per_group: 직업군당 수집할 최대 직업 수 (None이면 전체)
            max_pages: 직업별 수집할 페이지 수
            max_posts_per_page: 페이지당 수집할 최대 게시글 수
            target_groups: 크롤링할 직업군 (None이면 전체 5개)
            include_flat_boards: True면 실시간소식(2314)·팁과노하우(2304) 추가 수집
            flat_boards: 단일 게시판 ID→라벨 (None이면 FLAT_BOARDS 사용)
            flat_board_pages: 단일 게시판당 수집 페이지 수
            flat_board_posts_per_page: 단일 게시판 페이지당 게시글 수
        """
        groups = target_groups or JOB_GROUPS
        result = CrawlResult()
        start = time.time()

        logger.info("크롤링 시작 — 직업군: %d개, 단일게시판: %s", len(groups), include_flat_boards)

        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar()
        ) as session:
            # ── 1) 직업 게시판 (전사/마법사/궁수/도적/해적) ──
            for group_id, group_name in groups.items():
                logger.info("[%s] 직업군 크롤링 시작", group_name)

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

            # ── 2) 단일 게시판 (실시간 소식 2314, 팁과 노하우 2304) ──
            if include_flat_boards:
                flat = flat_boards or FLAT_BOARDS
                for board_id, board_label in flat.items():
                    logger.info("[정보공유/%s] 단일 게시판 크롤링 (board_id=%s)", board_label, board_id)
                    try:
                        posts = await self._scrape_flat_board(
                            session, board_id, board_label,
                            max_pages=flat_board_pages,
                            max_posts_per_page=flat_board_posts_per_page,
                            skip_notice=False,  # 공지·이벤트 포함
                        )
                        result.posts.extend(posts)
                        result.total_jobs_crawled += 1
                        logger.info("[정보공유/%s] %d개 게시글 수집", board_label, len(posts))
                    except Exception as e:
                        logger.error("[정보공유/%s] 크롤링 실패: %s", board_label, e)
                        result.errors += 1
                    await asyncio.sleep(self.group_delay)

        result.elapsed_seconds = time.time() - start
        logger.info(
            "크롤링 완료 — 게시글: %d개, 직업/게시판: %d개, 에러: %d, 소요: %.1f초",
            len(result.posts), result.total_jobs_crawled,
            result.errors, result.elapsed_seconds,
        )
        return result
