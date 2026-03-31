"""RAG 전용 라우터 단위 테스트."""
from unittest.mock import MagicMock

from app.agent.rag_router import _parse_rag_router_response, route_rag_query


def test_parse_rag_router_response_job():
    job_list = ["아크", "히어로"]
    out = _parse_rag_router_response(
        "ROUTE: job\nFILTER_JOB: 아크\nFILTER_GROUP: none\nCONFIDENCE: 5",
        job_list,
    )
    assert out["retrieval_route"] == "job"
    assert out["filter_job"] == "아크"
    assert out["filter_group"] is None
    assert out["retrieval_confidence"] == 5


def test_parse_rag_router_response_invalid_job_falls_back_all():
    job_list = ["아크", "히어로"]
    out = _parse_rag_router_response(
        "ROUTE: job\nFILTER_JOB: 없는직업\nFILTER_GROUP: none\nCONFIDENCE: 4",
        job_list,
    )
    assert out["retrieval_route"] == "all"
    assert out["filter_job"] is None


def test_route_rag_query_rule_first_job():
    rag = MagicMock()
    rag.job_list = ["아크", "히어로", "윈드브레이커"]
    out = route_rag_query("아크 스킬 추천", rag)
    assert out["retrieval_route"] == "job"
    assert out["filter_job"] == "아크"
    assert out["retrieval_source"] == "rule"


def test_route_rag_query_rule_first_group():
    rag = MagicMock()
    rag.job_list = ["아크", "히어로", "윈드브레이커"]
    out = route_rag_query("법사 직업 추천해줘", rag)
    assert out["retrieval_route"] == "group"
    assert out["filter_group"] == "마법사"
    assert out["retrieval_source"] == "rule"
