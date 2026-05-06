"""MCP 서버: Nexon Open API + RAG 검색 도구를 외부 AI 클라이언트에 노출.

노출 도구:
  - search_community_posts   : Qdrant RAG 검색
  - nexon_get_character_basic: 넥슨 API 캐릭터 기본 정보
  - nexon_get_character_stat : 넥슨 API 캐릭터 스탯

마운트:
  app.mount("/mcp", create_mcp_app())  → /mcp/sse, /mcp/messages 엔드포인트 생성
"""
import json
import logging

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "maple-tools",
        instructions="메이플스토리 커뮤니티 검색 및 캐릭터 정보 조회 도구를 제공합니다.",
    )

    @mcp.tool()
    async def search_community_posts(query: str, top_k: int = 3) -> str:
        """메이플스토리 인벤 커뮤니티 게시글 검색.

        Args:
            query: 검색 키워드 (예: '히어로 코어 세팅', '카오스 루시드 공략')
            top_k: 반환할 결과 수 (기본값: 3, 최대: 10)
        """
        try:
            from app.rag.loader import get_rag
            rag = get_rag()
            results = rag.search(query, top_k=min(top_k, 10))
            return json.dumps(
                [
                    {
                        "제목": r.get("제목", ""),
                        "직업": r.get("직업", ""),
                        "직업군": r.get("직업군", ""),
                        "본문_요약": r.get("본문", "")[:400],
                        "작성일": r.get("작성일", ""),
                        "score": round(r.get("score", 0.0), 4),
                    }
                    for r in results
                ],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            logger.error("MCP search_community_posts 오류: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def nexon_get_character_basic(character_name: str) -> str:
        """넥슨 Open API로 메이플스토리 캐릭터 기본 정보 조회 (레벨, 직업, 서버 등).

        Args:
            character_name: 메이플스토리 캐릭터 닉네임
        """
        try:
            from app.nexon.client import NexonMapleClient
            with NexonMapleClient() as client:
                ocid = client.get_ocid(character_name)
                basic = client.get_character_basic(ocid)
            return json.dumps(basic, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("MCP nexon_get_character_basic 오류: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def nexon_get_character_stat(character_name: str) -> str:
        """넥슨 Open API로 메이플스토리 캐릭터 스탯 조회 (전투력, 주스탯 등).

        Args:
            character_name: 메이플스토리 캐릭터 닉네임
        """
        try:
            from app.nexon.client import NexonMapleClient
            with NexonMapleClient() as client:
                ocid = client.get_ocid(character_name)
                stat = client.get_character_stat(ocid)
            return json.dumps(stat, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("MCP nexon_get_character_stat 오류: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def create_mcp_app():
        """FastAPI에 마운트할 MCP ASGI 앱 반환."""
        return mcp.sse_app()

    _MCP_AVAILABLE = True
    logger.info("MCP 서버 초기화 완료 (maple-tools)")

except ImportError:
    _MCP_AVAILABLE = False
    mcp = None  # type: ignore[assignment]
    logger.warning("mcp 패키지 없음: MCP 서버 비활성화 (pip install mcp)")

    def create_mcp_app():  # type: ignore[misc]
        """mcp 패키지 미설치 시 None 반환."""
        return None
