"""MapleRAG: 메이플스토리 RAG.

개선 사항:
- 최신성 점수: 선형 스케일 → 지수 감쇠 (반감기 6개월, 클리프 효과 제거)
- 컨텍스트: 고정 2000자 잘림 → 토큰 예산 기반 동적 패킹
- 청크 중복 제거: post_id 기준 최고 점수 청크만 유지
- 댓글 선택: 앞 3개 고정 → 길이 기준 정렬 (정보량 우선)
- LLM 호출 절감: 라우터에서 추출한 직업/직업군 필터 재사용
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Generator
from zoneinfo import ZoneInfo

from app.crawler.date_utils import parse_post_date
from app.rag.openai_client import OpenAIClient
from app.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

# 리랭킹: 유사도 80% + 최신성 20%
SIMILARITY_WEIGHT = 0.8
RECENCY_WEIGHT = 0.2
# 재정렬 풀 크기 (검색 시 top_k의 배수만큼 가져온 뒤 리랭킹)
RECENCY_RERANK_POOL_MULTIPLIER = 3

# 토큰 예산: 컨텍스트 최대 토큰 (4 chars ≈ 1 token)
MAX_CONTEXT_TOKENS = 2500

# ── 시스템 프롬프트 ─────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = "당신은 메이플스토리 질문 분석 전문가입니다. 지시에 따라 정확히 분석하세요."

ANSWER_SYSTEM_PROMPT = """당신은 메이플스토리 전문가 AI 어드바이저입니다.

규칙:
1. 제공된 게시글과 댓글을 바탕으로 정확하고 유용한 답변을 제공하세요
2. 확실하지 않은 정보는 "~라는 의견이 있습니다"로 표현하세요
3. 직업별 차이가 있다면 명확히 구분해주세요
4. 간단명료하게 핵심만 답변하세요
5. 출처 정보는 자동으로 표시되므로 답변에 포함하지 마세요"""

# ── 직업 별칭 → 정식 직업명 매핑 ────────────────────────
# 사용자가 약어/별명으로 질문해도 정확한 직업명으로 변환
JOB_ALIASES: dict[str, str] = {
    # 전사
    "히어로": "히어로",
    "팔라딘": "팔라딘", "팔라": "팔라딘",
    "다크나이트": "다크나이트", "닼나": "다크나이트",
    "소울마스터": "소울마스터", "소마": "소울마스터",
    "미하일": "미하일",
    "블래스터": "블래스터", "블래": "블래스터",
    "데몬슬레이어": "데몬슬레이어", "데슬": "데몬슬레이어",
    "데몬어벤져": "데몬어벤져", "데벤": "데몬어벤져", "데벤져": "데몬어벤져",
    "아란": "아란",
    "카이저": "카이저",
    "제로": "제로",
    "아델": "아델",
    # 마법사
    "비숍": "비숍", "숍": "비숍",
    "루미너스": "루미너스", "루미": "루미너스",
    "에반": "에반",
    "배틀메이지": "배틀메이지", "배메": "배틀메이지",
    "플레임위자드": "플레임위자드", "플위": "플레임위자드",
    "일리움": "일리움",
    "키네시스": "키네시스", "키네": "키네시스", "키시": "키네시스",
    "라라": "라라",
    "칼리": "칼리",
    # 궁수
    "보우마스터": "보우마스터", "보마": "보우마스터",
    "신궁": "신궁",
    "패스파인더": "패스파인더", "패파": "패스파인더",
    "윈드브레이커": "윈드브레이커", "윈브": "윈드브레이커",
    "와일드헌터": "와일드헌터", "와헌": "와일드헌터",
    "메르세데스": "메르세데스", "메르": "메르세데스",
    # 도적
    "나이트로드": "나이트로드", "나로": "나이트로드",
    "섀도어": "섀도어", "섀도": "섀도어",
    "듀얼블레이드": "듀얼블레이드", "듀블": "듀얼블레이드",
    "나이트워커": "나이트워커", "나워": "나이트워커",
    "괴도팬텀": "괴도팬텀", "팬텀": "괴도팬텀",
    "카데나": "카데나",
    "카인": "카인",
    "호영": "호영",
    "렌": "렌",
    # 해적
    "바이퍼": "바이퍼",
    "캡틴": "캡틴",
    "캐논슈터": "캐논슈터", "캐슈": "캐논슈터",
    "스트라이커": "스트라이커", "스커": "스트라이커",
    "엔젤릭버스터": "엔젤릭버스터", "엔버": "엔젤릭버스터",
    "메카닉": "메카닉", "메카": "메카닉",
    "제논": "제논",
    "은월": "은월",
    "아크": "아크",
    "아크(썬콜)": "아크(썬콜)", "썬콜": "아크(썬콜)",
    "아크(불독)": "아크(불독)", "불독": "아크(불독)",
    # 기타
    "예티": "예티",
    "핑크빈": "핑크빈",
}

# 직업 → 직업군 매핑
JOB_TO_GROUP: dict[str, str] = {
    "히어로": "전사", "팔라딘": "전사", "다크나이트": "전사",
    "소울마스터": "전사", "미하일": "전사", "블래스터": "전사",
    "데몬슬레이어": "전사", "데몬어벤져": "전사", "아란": "전사",
    "카이저": "전사", "제로": "전사", "아델": "전사",
    "비숍": "마법사", "루미너스": "마법사", "에반": "마법사",
    "배틀메이지": "마법사", "플레임위자드": "마법사", "일리움": "마법사",
    "키네시스": "마법사", "라라": "마법사", "칼리": "마법사",
    "보우마스터": "궁수", "신궁": "궁수", "패스파인더": "궁수",
    "윈드브레이커": "궁수", "와일드헌터": "궁수", "메르세데스": "궁수",
    "나이트로드": "도적", "섀도어": "도적", "듀얼블레이드": "도적",
    "나이트워커": "도적", "괴도팬텀": "도적", "카데나": "도적",
    "카인": "도적", "호영": "도적", "렌": "도적",
    "바이퍼": "해적", "캡틴": "해적", "캐논슈터": "해적",
    "스트라이커": "해적", "엔젤릭버스터": "해적", "메카닉": "해적",
    "제논": "해적", "은월": "해적", "아크": "해적",
    "아크(썬콜)": "해적", "아크(불독)": "해적",
}

# 직업군 별칭
GROUP_ALIASES: dict[str, str] = {
    "전사": "전사",
    "마법사": "마법사", "법사": "마법사",
    "궁수": "궁수",
    "도적": "도적", "표도": "도적",
    "해적": "해적",
}


def _resolve_job_from_query(query: str, job_list: list[str]) -> str | None:
    """쿼리에서 직업 별칭을 찾아 정식 직업명으로 변환 (로컬 매칭)."""
    query_lower = query.lower().replace(" ", "")
    for alias in sorted(JOB_ALIASES, key=len, reverse=True):
        if alias.lower().replace(" ", "") in query_lower:
            resolved = JOB_ALIASES[alias]
            if resolved in job_list:
                return resolved
    return None


def _resolve_group_from_query(query: str) -> str | None:
    """쿼리에서 직업군 별칭을 찾아 정식 직업군명으로 변환."""
    query_lower = query.lower().replace(" ", "")
    for alias in sorted(GROUP_ALIASES, key=len, reverse=True):
        if alias.lower().replace(" ", "") in query_lower:
            return GROUP_ALIASES[alias]
    return None


class MapleRAG:
    """Qdrant + GPT-4o-mini 기반 메이플스토리 RAG."""

    def __init__(
        self,
        qdrant_store: QdrantStore,
        openai_client: OpenAIClient,
        job_list: list[str] | None = None,
    ):
        self.store = qdrant_store
        self.ai = openai_client
        self.job_list = job_list or []

    # ── CoT 질문 분석 ──────────────────────────────────

    def analyze_query(self, query: str) -> dict[str, Any]:
        """CoT: 질문을 분석해서 검색 전략 결정.

        1단계: 로컬 별칭 매핑으로 직업명/직업군 즉시 해석
        2단계: 로컬에서 못 찾으면 LLM에게 분석 요청
        """
        local_job = _resolve_job_from_query(query, self.job_list)
        local_group = _resolve_group_from_query(query)

        if local_job:
            logger.info("로컬 별칭 매핑: '%s' → 직업=%s", query, local_job)
            return {"filter_job": local_job, "filter_group": None, "reasoning": f"별칭 매핑: {local_job}"}

        if local_group:
            logger.info("로컬 별칭 매핑: '%s' → 직업군=%s", query, local_group)
            return {"filter_job": None, "filter_group": local_group, "reasoning": f"직업군 매핑: {local_group}"}

        # LLM 분석 (별칭으로 못 찾은 경우)
        job_sample = ", ".join(self.job_list)
        analysis_prompt = f"""사용자의 메이플스토리 관련 질문을 분석하세요.

<DB에 저장된 직업 목록>
{job_sample}

<직업군 목록>
전사, 마법사, 궁수, 도적, 해적

<질문>
{query}

<분석 기준>
1. 특정 직업에 대한 질문 (스킬, 육성, 장비, 쿨뚝, 코어 등) → 해당 직업명을 "필터링할직업"에 기입
2. 특정 직업군에 대한 질문 → 해당 직업군을 "필터링할직업군"에 기입
3. 여러 직업을 비교하거나 추천 질문, 일반 정보 질문 → 둘 다 "없음"
4. 약어/별칭 주의: 윈브=윈드브레이커, 듀블=듀얼블레이드, 데슬=데몬슬레이어, 썬콜=아크(썬콜) 등
5. 특정 직업 이름이 들어가지만 해당 직업에 대한 질문이 아닌경우 "없음"으로 처리

<응답 형식 — 반드시 아래 두 줄만 출력>
필터링할직업: [DB 목록에 있는 정확한 직업명 또는 "없음"]
필터링할직업군: [전사/마법사/궁수/도적/해적 중 하나 또는 "없음"]"""

        logger.info("LLM 질문 분석 중...")
        response = self.ai.chat_completion(
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": analysis_prompt},
            ],
            max_tokens=100,
            temperature=0.1,
        )

        filter_job = None
        filter_group = None
        for line in response.split("\n"):
            if "필터링할직업:" in line and "직업군" not in line:
                job_text = line.split("필터링할직업:")[-1].strip()
                if job_text and job_text != "없음" and job_text in self.job_list:
                    filter_job = job_text
            elif "필터링할직업군:" in line:
                group_text = line.split("필터링할직업군:")[-1].strip()
                if group_text and group_text != "없음" and group_text in ("전사", "마법사", "궁수", "도적", "해적"):
                    filter_group = group_text

        logger.info("LLM 분석 결과: 직업=%s, 직업군=%s", filter_job or "없음", filter_group or "없음")
        return {"filter_job": filter_job, "filter_group": filter_group, "reasoning": response.strip()}

    # ── 검색 ───────────────────────────────────────────

    @staticmethod
    def _compute_recency_score(dt: datetime | None, now: datetime) -> float:
        """지수 감쇠 기반 최신성 점수 0~1. 반감기 ≈ 6개월(180일).

        선형 스케일 대비 장점: 2년 경계의 클리프 효과 없음.
        최신 게시물일수록 1에 가깝고, 오래될수록 자연스럽게 감소.
        """
        if dt is None:
            return 0.0
        dt_kst = dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        age_days = max(0.0, (now - dt_kst).total_seconds() / 86400)
        return round(math.exp(-age_days / 180), 6)

    @staticmethod
    def _deduplicate_chunks(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """청크 검색 결과에서 post_id 기준 중복 제거.

        동일 게시물의 여러 청크가 검색될 때 가장 높은 점수의 청크만 유지.
        """
        seen: dict[str, dict] = {}
        for doc in results:
            key = doc.get("post_id") or doc.get("제목", "") or str(doc.get("id", ""))
            if key not in seen or doc.get("score", 0.0) > seen[key].get("score", 0.0):
                seen[key] = doc
        return sorted(seen.values(), key=lambda d: d.get("score", 0.0), reverse=True)

    def _rerank_by_recency(
        self,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """청크 중복 제거 후 유사도 80% + 최신성 20%으로 재정렬 → 상위 top_k 반환."""
        if not results:
            return results

        now = datetime.now(ZoneInfo("Asia/Seoul"))

        # 청크 중복 제거 먼저 수행
        deduped = self._deduplicate_chunks(results)

        for doc in deduped:
            dt = parse_post_date(str(doc.get("작성일") or ""))
            rec = self._compute_recency_score(dt, now)
            sim = float(doc.get("score") or 0.0)
            doc["score"] = round(SIMILARITY_WEIGHT * sim + RECENCY_WEIGHT * rec, 6)

        deduped.sort(key=lambda d: d["score"], reverse=True)
        return deduped[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_job: str | None = None,
        filter_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """질문과 유사한 게시글 검색. 직업/직업군 필터 적용 후 최신성 반영 리랭킹."""
        query_vector = self.ai.create_embedding(query)
        pool_size = top_k * RECENCY_RERANK_POOL_MULTIPLIER

        if filter_job:
            results = self.store.search(query_vector, top_k=pool_size, filter_job=filter_job)
            if results:
                return self._rerank_by_recency(results, top_k)
            logger.warning("'%s' 직업 게시글 없음, 직업군으로 폴백", filter_job)
            fallback_group = JOB_TO_GROUP.get(filter_job)
            if fallback_group:
                results = self.store.search(query_vector, top_k=pool_size, filter_group=fallback_group)
                if results:
                    return self._rerank_by_recency(results, top_k)

        if filter_group:
            results = self.store.search(query_vector, top_k=pool_size, filter_group=filter_group)
            if results:
                return self._rerank_by_recency(results, top_k)
            logger.warning("'%s' 직업군 게시글 없음, 전체 검색으로 전환", filter_group)

        results = self.store.search(query_vector, top_k=pool_size)
        return self._rerank_by_recency(results, top_k)

    # ── 컨텍스트 구성 ──────────────────────────────────

    def _build_context(
        self,
        results: list[dict[str, Any]],
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> str:
        """토큰 예산 기반 동적 컨텍스트 구성.

        문서마다 고정 2000자 대신, 전체 토큰 예산(기본 2500) 범위 내에서 최대한 포함.
        댓글은 길이 기준 정렬하여 정보량 높은 댓글을 우선 포함.
        """
        context = ""
        used_tokens = 0

        for idx, doc in enumerate(results, 1):
            header = (
                f"\n{'=' * 60}\n"
                f"[참고자료 {idx}]\n"
                f"직업군: {doc.get('직업군', '')} | 직업: {doc.get('직업', '')}\n"
                f"제목: {doc.get('제목', '')}\n"
                f"작성일: {doc.get('작성일', '')}\n"
            )
            본문 = doc.get("본문", "")
            댓글_raw = doc.get("댓글", "")

            # 헤더 토큰 예산 확인
            header_tokens = len(header) // 4
            if used_tokens + header_tokens > max_context_tokens and idx > 1:
                break

            # 남은 예산에 맞춰 본문 길이 결정
            remaining_tokens = max_context_tokens - used_tokens - header_tokens
            body_chars = min(len(본문), max(0, remaining_tokens * 4))
            body_text = 본문[:body_chars]

            doc_text = header + f"\n본문:\n{body_text}"

            # 댓글: 길이 기준 정렬 (긴 댓글 = 정보량 높음)
            if 댓글_raw:
                comments = sorted(
                    (c.strip() for c in str(댓글_raw).split("|") if c.strip()),
                    key=len,
                    reverse=True,
                )[:3]
                if comments:
                    comment_lines = "\n".join(f"  {i}. {c[:200]}" for i, c in enumerate(comments, 1))
                    doc_text += f"\n\n주요 댓글:\n{comment_lines}\n"

            doc_tokens = len(doc_text) // 4
            if used_tokens + doc_tokens > max_context_tokens and idx > 1:
                break

            context += doc_text
            used_tokens += doc_tokens

        return context

    def _build_answer_messages(
        self, query: str, context: str, main_character_name: str | None = None
    ) -> list[dict[str, str]]:
        """답변 생성용 메시지 목록 구성."""
        user_content = (
            f"다음은 메이플스토리 인벤 게시판에서 검색한 관련 정보입니다:\n"
            f"{context}\n\n"
            f"질문: {query}\n\n"
        )
        if main_character_name:
            user_content = f"[사용자 본캐: {main_character_name}]\n\n" + user_content
        user_content += "위 정보를 바탕으로 질문에 답변해주세요."
        return [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _build_references(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """검색 결과에서 참조 정보 목록 구성."""
        return [
            {
                "직업": doc.get("직업", ""),
                "직업군": doc.get("직업군", ""),
                "제목": doc.get("제목", "")[:200],
                "작성일": doc.get("작성일", ""),
                "similarity_score": round(doc.get("score", 0.0), 4),
                "본문_요약": doc.get("본문", "")[:300],
            }
            for doc in results
        ]

    # ── Reflexion ──────────────────────────────────────

    _REFLEXION_SCORE_THRESHOLD = 0.55  # 이 미만이면 쿼리 재작성 후 재검색

    def _should_refine(self, results: list[dict[str, Any]]) -> bool:
        """검색 품질이 낮으면 True (최고 점수 임계값 기반, LLM 호출 없음)."""
        if not results:
            return True
        return max(r.get("score", 0.0) for r in results) < self._REFLEXION_SCORE_THRESHOLD

    def _rewrite_query(self, original_query: str) -> str:
        """검색 품질이 낮을 때 LLM으로 쿼리 재작성. 실패 시 원본 반환."""
        prompt = (
            f"다음 메이플스토리 검색 질문을 검색 엔진에 더 적합하도록 구체적으로 재작성하세요.\n"
            f"원본 질문: {original_query}\n"
            f"재작성된 질문 (한 문장으로만):"
        )
        try:
            rewritten = self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": "메이플스토리 검색 전문가입니다. 지시에 따라 질문을 재작성하세요."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=80,
                temperature=0.2,
            )
            rewritten = rewritten.strip()
            if rewritten:
                logger.info("Reflexion 쿼리 재작성: '%s' → '%s'", original_query, rewritten)
                return rewritten
        except Exception as e:
            logger.warning("쿼리 재작성 실패: %s", e)
        return original_query

    def _reflexion_search(
        self,
        query: str,
        top_k: int,
        filter_job: str | None,
        filter_group: str | None,
        initial_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """초기 검색 품질이 낮으면 쿼리 재작성 후 재검색, 결과 병합."""
        if not self._should_refine(initial_results):
            return initial_results

        logger.info("Reflexion 발동: 검색 품질 낮음, 쿼리 재작성 중...")
        rewritten = self._rewrite_query(query)
        new_results = self.search(rewritten, top_k, filter_job=filter_job, filter_group=filter_group)

        # post_id(또는 제목) 기준 합집합 — 점수 높은 버전 유지
        merged: dict[str, dict] = {}
        for r in initial_results + new_results:
            key = r.get("post_id") or r.get("제목", "") or str(r.get("id", ""))
            if key not in merged or r.get("score", 0.0) > merged[key].get("score", 0.0):
                merged[key] = r

        final = sorted(merged.values(), key=lambda d: d.get("score", 0.0), reverse=True)[:top_k]
        logger.info("Reflexion 완료: %d → %d 결과 (병합 후 %d)", len(initial_results), len(new_results), len(final))
        return final

    def _resolve_filters(
        self,
        query: str,
        use_cot: bool,
        pre_filter_job: str | None,
        pre_filter_group: str | None,
        skip_analysis: bool,
    ) -> tuple[str | None, str | None]:
        """직업/직업군 필터 결정.

        skip_analysis=True: 라우터에서 이미 추출된 필터 재사용 (LLM 호출 없음)
        skip_analysis=False: 로컬 별칭 매핑 → 실패 시 LLM 분석
        """
        if skip_analysis:
            logger.info(
                "라우터 추출 필터 재사용: 직업=%s, 직업군=%s",
                pre_filter_job or "없음", pre_filter_group or "없음",
            )
            return pre_filter_job, pre_filter_group

        if use_cot and self.job_list:
            analysis = self.analyze_query(query)
            return analysis.get("filter_job"), analysis.get("filter_group")

        return None, None

    # ── 답변 생성 ──────────────────────────────────────

    def generate_answer(
        self,
        query: str,
        top_k: int = 3,
        use_cot: bool = True,
        main_character_name: str | None = None,
        pre_filter_job: str | None = None,
        pre_filter_group: str | None = None,
        skip_analysis: bool = False,
    ) -> dict[str, Any]:
        """CoT 기반 RAG 답변 생성 (동기).

        Args:
            pre_filter_job: 라우터에서 미리 추출한 직업 필터
            pre_filter_group: 라우터에서 미리 추출한 직업군 필터
            skip_analysis: True이면 analyze_query() LLM 호출 없이 pre_filter 직접 사용
        """
        logger.info("질문: %s (본캐=%s)", query, main_character_name or "-")

        filter_job, filter_group = self._resolve_filters(
            query, use_cot, pre_filter_job, pre_filter_group, skip_analysis
        )

        logger.info("관련 게시글 검색 중... (직업=%s, 직업군=%s)", filter_job or "없음", filter_group or "없음")
        results = self.search(query, top_k, filter_job=filter_job, filter_group=filter_group)

        # Reflexion: 검색 품질이 낮으면 쿼리 재작성 후 재검색 (사전 필터 사용 시 생략)
        if not skip_analysis:
            results = self._reflexion_search(query, top_k, filter_job, filter_group, results)

        if not results:
            return {"answer": "관련 게시글을 찾을 수 없습니다.", "references": []}

        context = self._build_context(results)
        messages = self._build_answer_messages(query, context, main_character_name)
        logger.info("답변 생성 중...")
        answer = self.ai.chat_completion(messages=messages, temperature=0.1)

        references = self._build_references(results)
        return {"answer": answer, "references": references}

    def generate_answer_stream(
        self,
        query: str,
        top_k: int = 3,
        use_cot: bool = True,
        main_character_name: str | None = None,
        pre_filter_job: str | None = None,
        pre_filter_group: str | None = None,
        skip_analysis: bool = False,
    ) -> Generator[dict[str, Any], None, None]:
        """스트리밍 RAG 답변 생성 (제너레이터).

        Args:
            pre_filter_job: 라우터에서 미리 추출한 직업 필터
            pre_filter_group: 라우터에서 미리 추출한 직업군 필터
            skip_analysis: True이면 analyze_query() LLM 호출 없이 pre_filter 직접 사용
        """
        logger.info("질문 (스트리밍): %s (본캐=%s)", query, main_character_name or "-")

        filter_job, filter_group = self._resolve_filters(
            query, use_cot, pre_filter_job, pre_filter_group, skip_analysis
        )

        results = self.search(query, top_k, filter_job=filter_job, filter_group=filter_group)

        # Reflexion: 검색 품질이 낮으면 쿼리 재작성 후 재검색 (사전 필터 사용 시 생략)
        if not skip_analysis:
            results = self._reflexion_search(query, top_k, filter_job, filter_group, results)

        if not results:
            yield {"type": "answer_chunk", "content": "관련 게시글을 찾을 수 없습니다."}
            yield {"type": "done", "content": ""}
            yield {"type": "references", "content": []}
            return

        context = self._build_context(results)
        messages = self._build_answer_messages(query, context, main_character_name)
        for chunk in self.ai.chat_completion_stream(messages=messages, temperature=0.1):
            yield {"type": "answer_chunk", "content": chunk}

        yield {"type": "done", "content": ""}

        references = self._build_references(results)
        yield {"type": "references", "content": references}
