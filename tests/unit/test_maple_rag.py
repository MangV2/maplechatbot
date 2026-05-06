"""MapleRAG 단위 테스트."""
import math
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.rag.maple_rag import MapleRAG


class TestMapleRAGAnalyzeQuery:
    """CoT 질문 분석 테스트."""

    def test_analyze_specific_job_returns_filter(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """특정 직업 질문 시 해당 직업 필터 반환."""
        mock_openai_client.chat_completion.return_value = (
            "필터링할직업: 아크\n이유: 아크 스킬 관련 질문"
        )
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.analyze_query("아크 스킬 트리 어떻게 해야 하나요?")

        # "아크"는 JOB_ALIASES에 있어 로컬 매핑으로 처리 (LLM 호출 없음)
        assert result["filter_job"] == "아크"
        assert "아크" in result["reasoning"]

    def test_analyze_general_query_returns_no_filter(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """일반 질문 시 필터 없음 반환 (LLM 폴백)."""
        mock_openai_client.chat_completion.return_value = (
            "필터링할직업: 없음\n이유: 범용적인 게임 정보 질문"
        )
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        # 직업명이 없는 쿼리 → LLM 분석
        result = rag.analyze_query("보스 데미지 올리는 법")

        assert result["filter_job"] is None

    def test_analyze_unknown_job_returns_no_filter(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """직업 목록에 없는 직업명은 필터 없음 처리."""
        mock_openai_client.chat_completion.return_value = (
            "필터링할직업: 존재하지않는직업\n이유: 테스트"
        )
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.analyze_query("존재하지않는직업 스킬")

        assert result["filter_job"] is None

    def test_analyze_empty_job_list_skips_analysis(
        self, mock_openai_client, mock_qdrant_store
    ):
        """직업 목록이 비었으면 분석을 수행하되 필터 없음."""
        mock_openai_client.chat_completion.return_value = (
            "필터링할직업: 없음\n이유: 직업 목록 없음"
        )
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, job_list=[])

        result = rag.analyze_query("아무 질문")

        assert result["filter_job"] is None


class TestMapleRAGSearch:
    """검색 테스트."""

    def test_search_calls_embedding_and_store(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """검색 시 임베딩 생성 후 Qdrant 검색 호출."""
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        results = rag.search("아크 스킬", top_k=5)

        assert len(results) == 2
        mock_openai_client.create_embedding.assert_called_once_with("아크 스킬")
        mock_qdrant_store.search.assert_called_once()

    def test_search_with_filter_fallback_to_all(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """필터 검색 결과 없으면 전체 검색으로 폴백."""
        mock_qdrant_store.search.side_effect = [
            [],  # 필터 검색: 결과 없음
            [{"id": 1, "score": 0.8, "직업": "아크", "직업군": "전사", "제목": "테스트", "작성일": "", "본문": "", "댓글": "", "post_id": "1"}],
        ]
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        results = rag.search("질문", filter_job="없는직업")

        assert mock_qdrant_store.search.call_count == 2
        assert len(results) == 1

    def test_search_without_filter(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """필터 없이 검색."""
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        rag.search("질문", top_k=3)

        call_kwargs = mock_qdrant_store.search.call_args.kwargs
        assert call_kwargs["filter_job"] is None


class TestMapleRAGRecencyScore:
    """최신성 점수 지수 감쇠 테스트."""

    def test_recent_post_high_score(self):
        """최근 게시글은 높은 점수."""
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        recent = now.replace(day=now.day)  # 오늘
        score = MapleRAG._compute_recency_score(recent, now)
        assert score > 0.99

    def test_old_post_low_score(self):
        """오래된 게시글은 낮은 점수 (지수 감쇠, 클리프 없음)."""
        from datetime import timedelta
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        old = now - timedelta(days=365)  # 1년 전
        score = MapleRAG._compute_recency_score(old, now)
        expected = math.exp(-365 / 180)
        assert abs(score - expected) < 0.01

    def test_none_date_returns_zero(self):
        """날짜 파싱 실패 시 0 반환."""
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        assert MapleRAG._compute_recency_score(None, now) == 0.0

    def test_no_cliff_at_two_years(self):
        """2년 이상 지난 게시글도 0이 아닌 점수 (클리프 효과 없음)."""
        from datetime import timedelta
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        two_years_ago = now - timedelta(days=730)
        score = MapleRAG._compute_recency_score(two_years_ago, now)
        assert score > 0.0  # 선형 방식이었다면 0


class TestMapleRAGGenerateAnswer:
    """답변 생성 테스트."""

    def test_generate_answer_local_alias_skips_llm_analysis(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """로컬 별칭 매핑으로 직업 분류 시 LLM 분석 생략 → LLM 1번만 호출."""
        mock_openai_client.chat_completion.return_value = "아크는 강력한 전사 직업입니다."
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        # "아크"는 JOB_ALIASES에 있어 로컬 매핑 → analyze_query LLM 호출 없음
        result = rag.generate_answer("아크 추천하나요?")

        assert result["answer"] == "아크는 강력한 전사 직업입니다."
        assert len(result["references"]) == 2
        assert mock_openai_client.chat_completion.call_count == 1

    def test_generate_answer_with_cot_llm_fallback(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """로컬 별칭 매핑 실패 시 LLM 분석 + 답변 2번 호출."""
        mock_openai_client.chat_completion.side_effect = [
            "필터링할직업: 없음\n이유: 범용 질문",  # analyze_query (LLM 폴백)
            "보스 데미지는 주스탯과 공격력에 의존합니다.",  # generate_answer
        ]
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        # 직업명 없는 쿼리 → LLM 분석 필요
        result = rag.generate_answer("보스 데미지 올리는 법 알려줘")

        assert result["answer"] == "보스 데미지는 주스탯과 공격력에 의존합니다."
        assert mock_openai_client.chat_completion.call_count == 2

    def test_generate_answer_without_cot(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """CoT 비활성화 시 답변 1번만 호출."""
        mock_openai_client.chat_completion.return_value = "답변입니다."
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.generate_answer("질문", use_cot=False)

        assert result["answer"] == "답변입니다."
        assert mock_openai_client.chat_completion.call_count == 1

    def test_generate_answer_skip_analysis_uses_pre_filter(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """skip_analysis=True이면 LLM 호출 없이 pre_filter 사용."""
        mock_openai_client.chat_completion.return_value = "팔라딘 답변."
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.generate_answer(
            "팔라딘 코어 세팅",
            pre_filter_job="팔라딘",
            skip_analysis=True,
        )

        assert result["answer"] == "팔라딘 답변."
        assert mock_openai_client.chat_completion.call_count == 1  # 답변 생성만

    def test_generate_answer_no_results(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """검색 결과가 없으면 안내 메시지 반환."""
        mock_qdrant_store.search.return_value = []
        mock_openai_client.chat_completion.return_value = (
            "필터링할직업: 없음\n이유: 일반 질문"
        )
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.generate_answer("검색결과없는질문")

        assert result["answer"] == "관련 게시글을 찾을 수 없습니다."
        assert result["references"] == []

    def test_generate_answer_references_format(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """참조 정보의 필드가 올바른 형식."""
        mock_openai_client.chat_completion.return_value = "답변"
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        result = rag.generate_answer("질문", use_cot=False)

        ref = result["references"][0]
        assert "직업" in ref
        assert "직업군" in ref
        assert "제목" in ref
        assert "작성일" in ref
        assert "similarity_score" in ref
        assert "본문_요약" in ref


class TestMapleRAGBuildContext:
    """컨텍스트 구성 테스트."""

    def test_build_context_includes_all_documents(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """검색 결과의 모든 문서가 컨텍스트에 포함."""
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        results = mock_qdrant_store.search.return_value
        context = rag._build_context(results)

        assert "[참고자료 1]" in context
        assert "[참고자료 2]" in context
        assert "아크 스킬 트리 가이드" in context
        assert "아크 보스 세팅" in context

    def test_build_context_includes_comments(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """댓글이 있는 문서는 댓글도 컨텍스트에 포함."""
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        results = mock_qdrant_store.search.return_value
        context = rag._build_context(results)

        assert "좋은 정보 감사합니다" in context

    def test_build_context_respects_token_budget(
        self, mock_openai_client, mock_qdrant_store, sample_job_list
    ):
        """토큰 예산 초과 시 문서 잘림."""
        rag = MapleRAG(mock_qdrant_store, mock_openai_client, sample_job_list)

        # 매우 작은 토큰 예산으로 두 번째 문서가 잘리는지 확인
        results = mock_qdrant_store.search.return_value
        context_limited = rag._build_context(results, max_context_tokens=50)
        context_full = rag._build_context(results, max_context_tokens=10000)

        assert len(context_limited) < len(context_full)


class TestMapleRAGDeduplication:
    """청크 중복 제거 테스트."""

    def test_deduplicate_chunks_keeps_highest_score(self):
        """동일 post_id의 청크는 가장 높은 점수만 유지."""
        results = [
            {"id": 1, "score": 0.9, "post_id": "p1", "제목": "A"},
            {"id": 2, "score": 0.7, "post_id": "p1", "제목": "A"},  # 중복 (낮은 점수)
            {"id": 3, "score": 0.8, "post_id": "p2", "제목": "B"},
        ]
        deduped = MapleRAG._deduplicate_chunks(results)

        assert len(deduped) == 2
        p1_doc = next(d for d in deduped if d["post_id"] == "p1")
        assert p1_doc["score"] == 0.9

    def test_deduplicate_no_duplicates(self):
        """중복 없으면 전체 유지."""
        results = [
            {"id": 1, "score": 0.9, "post_id": "p1", "제목": "A"},
            {"id": 2, "score": 0.8, "post_id": "p2", "제목": "B"},
        ]
        deduped = MapleRAG._deduplicate_chunks(results)
        assert len(deduped) == 2
