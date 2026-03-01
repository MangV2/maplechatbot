"""Local smoke test - in-memory Qdrant pipeline verification.

Usage:
    1. Set OPENAI_API_KEY in .env
    2. python -m scripts.local_smoke_test
"""
import io
import sys
from pathlib import Path

# Windows cp949 encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_test")


def main():
    from app.config import settings

    print("=" * 60)
    print("🍁 메이플 챗봇 — 로컬 스모크 테스트")
    print("=" * 60)

    # ── 1. OpenAI API 키 확인 ──
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        print("\n❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일에 OPENAI_API_KEY=sk-... 를 설정해주세요.")
        sys.exit(1)

    print(f"\n✅ OpenAI API Key: ...{settings.openai_api_key[-6:]}")
    print(f"   모델: {settings.openai_chat_model}")
    print(f"   임베딩: {settings.openai_embedding_model}")

    # ── 2. OpenAI 연결 테스트 ──
    print("\n📡 OpenAI 연결 테스트...")
    from app.rag.openai_client import OpenAIClient

    ai = OpenAIClient()
    try:
        embedding = ai.create_embedding("테스트 텍스트")
        print(f"   ✅ 임베딩 생성 성공 (차원: {len(embedding)})")
    except Exception as e:
        print(f"   ❌ 임베딩 실패: {e}")
        sys.exit(1)

    try:
        answer = ai.chat_completion(
            messages=[{"role": "user", "content": "안녕하세요. 짧게 인사해주세요."}],
            max_tokens=50,
        )
        print(f"   ✅ GPT-4o 응답: {answer[:50]}...")
    except Exception as e:
        print(f"   ❌ GPT-4o 실패: {e}")
        sys.exit(1)

    # ── 3. 인메모리 Qdrant 테스트 ──
    print("\n📦 Qdrant 인메모리 테스트...")
    from app.rag.qdrant_store import QdrantStore

    store = QdrantStore(collection_name="smoke_test", in_memory=True)
    print(f"   ✅ 컬렉션 생성: {store.collection_name}")

    # 샘플 데이터 적재
    sample_posts = [
        {
            "직업": "아크",
            "직업군": "전사",
            "제목": "아크 보스 세팅 가이드 2025",
            "본문": "아크는 전사 계열 직업으로 보스전에서 높은 딜을 낼 수 있습니다. "
                    "주력 스킬은 인피니티 블레이드이며, 헥사 매트릭스에서 강화 코어를 "
                    "우선적으로 올려야 합니다. 보스 세팅 시에는 공격력 퍼센트 위주로 세팅합니다.",
            "댓글": "아크 최고! | 세팅 감사합니다 | 스킬 순서도 알려주세요",
            "작성일": "2025-01-15",
        },
        {
            "직업": "제로",
            "직업군": "전사",
            "제목": "제로 쿨타임 뚝딱이 필요한가요?",
            "본문": "제로는 알파와 베타를 번갈아 사용하는 독특한 직업입니다. "
                    "쿨타임 뚝딱이(쿨뚝)는 스킬 쿨타임을 줄여주는 능력으로, "
                    "제로에게는 필수적이지 않다는 의견이 많습니다. "
                    "태그 시스템으로 쿨타임이 자연스럽게 관리되기 때문입니다.",
            "댓글": "쿨뚝 없어도 됩니다 | 태그로 충분해요 | 다른 걸 올리세요",
            "작성일": "2025-01-10",
        },
        {
            "직업": "아델",
            "직업군": "전사",
            "제목": "아델 메소 효율 사냥터 추천",
            "본문": "아델은 넓은 범위의 스킬로 사냥 효율이 높은 직업입니다. "
                    "레벨 260 이상에서는 리버스 시티, 세르니움 등에서 "
                    "높은 메소 효율을 보여줍니다.",
            "댓글": "아델 사냥 꿀잼 | 리버스시티 추천합니다",
            "작성일": "2025-01-20",
        },
    ]

    # 임베딩 생성 & 적재
    print("   📥 샘플 데이터 3건 적재 중...")
    texts = [
        f"직업: {p['직업']} | 제목: {p['제목']} | {p['본문'][:300]}"
        for p in sample_posts
    ]
    vectors = ai.create_embeddings_batch(texts)
    store.upsert_batch(
        ids=list(range(len(sample_posts))),
        vectors=vectors,
        payloads=sample_posts,
    )
    print(f"   ✅ Qdrant 문서 수: {store.count()}")

    # ── 4. RAG 파이프라인 테스트 ──
    print("\n🤖 RAG 파이프라인 테스트...")
    from app.rag.maple_rag import MapleRAG

    job_list = ["아크", "제로", "아델"]
    rag = MapleRAG(qdrant_store=store, openai_client=ai, job_list=job_list)

    test_queries = [
        "아크 보스 세팅 어떻게 해야 하나요?",
        "제로 쿨뚝 필요한가요?",
        "메소 효율 좋은 직업 추천해주세요",
    ]

    for query in test_queries:
        print(f"\n   💬 질문: {query}")
        result = rag.generate_answer(query, top_k=2, use_cot=True)
        answer = result["answer"]
        refs = result["references"]
        print(f"   🤖 답변: {answer[:100]}...")
        print(f"   📚 참고 문서: {len(refs)}건")
        for ref in refs:
            print(f"      - [{ref['직업']}] {ref['제목']} (유사도: {ref['similarity_score']})")

    # ── 5. 결과 ──
    print("\n" + "=" * 60)
    print("✅ 스모크 테스트 성공!")
    print("=" * 60)
    print("\n다음 단계:")
    print("  1. Docker Desktop 설치")
    print("  2. docker compose up --build -d")
    print("  3. http://localhost:8501 에서 채팅 UI 접속")


if __name__ == "__main__":
    main()
