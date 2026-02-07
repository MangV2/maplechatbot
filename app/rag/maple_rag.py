"""MapleRAG: Qdrant + GPT-4o 기반 메이플스토리 RAG."""
import logging
from typing import Any, Generator

from app.rag.openai_client import OpenAIClient
from app.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

# ── 시스템 프롬프트 ─────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = "질문을 분석하고 간단히 답변하세요."

ANSWER_SYSTEM_PROMPT = """당신은 메이플스토리 전문가 AI 어드바이저입니다.

규칙:
1. 제공된 게시글과 댓글을 바탕으로 정확하고 유용한 답변을 제공하세요
2. 확실하지 않은 정보는 "~라는 의견이 있습니다"로 표현하세요
3. 직업별 차이가 있다면 명확히 구분해주세요
4. 간단명료하게 핵심만 답변하세요
5. 출처 정보는 자동으로 표시되므로 답변에 포함하지 마세요"""


class MapleRAG:
    """Qdrant + GPT-4o 기반 메이플스토리 RAG."""

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
        """CoT: 질문을 분석해서 검색 전략 결정."""
        job_sample = ", ".join(self.job_list[:50])
        analysis_prompt = f"""당신은 메이플스토리 질문 분석 전문가입니다.

사용자의 질문을 분석하고, 어떤 검색 전략이 필요한지 판단하세요.

<사용 가능한 직업 목록>
{job_sample}

<질문>
{query}

<분석 기준>
1. 특정 직업의 스킬, 육성, 장비 등을 묻는 질문 → 해당 직업만 검색
2. 여러 직업을 비교하거나 추천을 묻는 질문 → 전체 검색
3. 일반적인 게임 정보 질문 → 전체 검색
4. 직업명이 언급되어도 비교/선택의 맥락이면 → 전체 검색

<응답 형식>
반드시 다음 형식으로만 답변하세요:

필터링할직업: [직업명 또는 "없음"]
이유: [한 줄로 설명]"""

        logger.info("질문 분석 중...")
        response = self.ai.chat_completion(
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": analysis_prompt},
            ],
            max_tokens=150,
            temperature=0.3,
        )

        filter_job = None
        reasoning = ""
        for line in response.split("\n"):
            if "필터링할직업:" in line:
                job_text = line.split("필터링할직업:")[-1].strip()
                if job_text and job_text != "없음" and job_text in self.job_list:
                    filter_job = job_text
            elif "이유:" in line:
                reasoning = line.split("이유:")[-1].strip()

        logger.info("분석 결과: %s (필터: %s)", reasoning, filter_job or "전체 검색")
        return {"filter_job": filter_job, "reasoning": reasoning}

    # ── 검색 ───────────────────────────────────────────

    def search(
        self, query: str, top_k: int = 5, filter_job: str | None = None
    ) -> list[dict[str, Any]]:
        """질문과 유사한 게시글 검색."""
        query_vector = self.ai.create_embedding(query)
        results = self.store.search(query_vector, top_k=top_k, filter_job=filter_job)

        # 필터 결과가 없으면 전체 검색으로 폴백
        if not results and filter_job:
            logger.warning("'%s' 게시글 없음, 전체 검색으로 전환", filter_job)
            results = self.store.search(query_vector, top_k=top_k, filter_job=None)

        return results

    # ── 컨텍스트 구성 ──────────────────────────────────

    def _build_context(self, results: list[dict[str, Any]]) -> str:
        """검색 결과를 LLM 컨텍스트 문자열로 변환."""
        context = ""
        for idx, doc in enumerate(results, 1):
            context += f"\n{'=' * 60}\n"
            context += f"[참고자료 {idx}]\n"
            context += f"직업군: {doc.get('직업군', '')} | 직업: {doc.get('직업', '')}\n"
            context += f"제목: {doc.get('제목', '')}\n"
            context += f"작성일: {doc.get('작성일', '')}\n"
            본문 = doc.get("본문", "")
            context += f"\n본문:\n{본문[:500]}"
            댓글 = doc.get("댓글", "")
            if 댓글:
                comments = str(댓글).split("|")[:3]
                context += "\n\n주요 댓글:\n"
                for i, comment in enumerate(comments, 1):
                    context += f"  {i}. {comment.strip()[:200]}\n"
        return context

    def _build_answer_messages(
        self, query: str, context: str
    ) -> list[dict[str, str]]:
        """답변 생성용 메시지 목록 구성."""
        return [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"다음은 메이플스토리 인벤 게시판에서 검색한 관련 정보입니다:\n"
                    f"{context}\n\n"
                    f"질문: {query}\n\n"
                    f"위 정보를 바탕으로 질문에 답변해주세요."
                ),
            },
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

    # ── 답변 생성 ──────────────────────────────────────

    def generate_answer(
        self,
        query: str,
        top_k: int = 5,
        use_cot: bool = True,
    ) -> dict[str, Any]:
        """CoT 기반 RAG 답변 생성 (동기)."""
        logger.info("질문: %s", query)

        # 1) CoT 질문 분석
        filter_job = None
        if use_cot and self.job_list:
            analysis = self.analyze_query(query)
            filter_job = analysis["filter_job"]

        # 2) 관련 게시글 검색
        logger.info("관련 게시글 검색 중...")
        results = self.search(query, top_k, filter_job=filter_job)
        if not results:
            return {"answer": "관련 게시글을 찾을 수 없습니다.", "references": []}

        # 3) 답변 생성
        context = self._build_context(results)
        messages = self._build_answer_messages(query, context)
        logger.info("답변 생성 중...")
        answer = self.ai.chat_completion(messages=messages, temperature=0.7)

        # 4) 참조 정보
        references = self._build_references(results)
        return {"answer": answer, "references": references}

    def generate_answer_stream(
        self,
        query: str,
        top_k: int = 5,
        use_cot: bool = True,
    ) -> Generator[dict[str, Any], None, None]:
        """스트리밍 RAG 답변 생성 (제너레이터)."""
        logger.info("질문 (스트리밍): %s", query)

        # 1) CoT 질문 분석
        filter_job = None
        if use_cot and self.job_list:
            analysis = self.analyze_query(query)
            filter_job = analysis["filter_job"]

        # 2) 관련 게시글 검색
        results = self.search(query, top_k, filter_job=filter_job)
        if not results:
            yield {"type": "answer_chunk", "content": "관련 게시글을 찾을 수 없습니다."}
            yield {"type": "done", "content": ""}
            yield {"type": "references", "content": []}
            return

        # 3) 스트리밍 답변
        context = self._build_context(results)
        messages = self._build_answer_messages(query, context)
        for chunk in self.ai.chat_completion_stream(messages=messages, temperature=0.7):
            yield {"type": "answer_chunk", "content": chunk}

        yield {"type": "done", "content": ""}

        # 4) 참조 정보
        references = self._build_references(results)
        yield {"type": "references", "content": references}
