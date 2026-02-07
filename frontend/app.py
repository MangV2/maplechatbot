"""메이플스토리 RAG 챗봇 — Streamlit UI."""
import streamlit as st

from api_client import chat, chat_stream, health_check

# ── 페이지 설정 ────────────────────────────────────────

st.set_page_config(
    page_title="메이플 챗봇",
    page_icon="🍁",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── 커스텀 CSS ─────────────────────────────────────────

st.markdown("""
<style>
/* 전체 배경 */
.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
}

/* 채팅 메시지 스타일 */
.stChatMessage {
    border-radius: 12px;
    margin-bottom: 8px;
}

/* 사이드바 */
section[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #30363d;
}

/* 참고 자료 카드 */
.ref-card {
    background: #1c2333;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px;
    margin: 6px 0;
    font-size: 0.85em;
}
.ref-card .ref-title {
    color: #58a6ff;
    font-weight: 600;
    margin-bottom: 4px;
}
.ref-card .ref-meta {
    color: #8b949e;
    font-size: 0.8em;
}
.ref-card .ref-body {
    color: #c9d1d9;
    margin-top: 6px;
    line-height: 1.5;
}

/* 헤더 */
.main-header {
    text-align: center;
    padding: 20px 0 10px;
}
.main-header h1 {
    background: linear-gradient(90deg, #ff6b35, #f7931a);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2em;
    margin-bottom: 4px;
}
.main-header p {
    color: #8b949e;
    font-size: 0.95em;
}
</style>
""", unsafe_allow_html=True)

# ── 사이드바 ───────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ 설정")

    use_streaming = st.toggle("스트리밍 응답", value=True, help="답변을 실시간으로 표시")
    top_k = st.slider("참고 문서 수", min_value=1, max_value=10, value=5)
    use_cot = st.toggle("CoT 질문 분석", value=True, help="질문을 분석하여 관련 직업 필터링")

    st.divider()

    # 헬스 체크
    st.markdown("### 📊 시스템 상태")
    if st.button("상태 확인", use_container_width=True):
        status = health_check()
        if status.get("status") == "ok":
            st.success(f"✅ 연결됨 | 문서: {status.get('document_count', 0):,}개")
        else:
            st.error(f"❌ {status.get('qdrant_status', '연결 실패')}")

    st.divider()

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown(
        """
        ### 💡 예시 질문
        - 아크 보스 세팅 추천해줘
        - 제로 쿨뚝 필요한가요?
        - 신직업 추천 부탁해
        - 메소 효율 좋은 직업은?
        - 보스 데미지 올리는 법
        """
    )

# ── 메인 화면 ──────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1>🍁 메이플 챗봇</h1>
    <p>메이플스토리 인벤 게시판 기반 AI 어드바이저</p>
</div>
""", unsafe_allow_html=True)

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 기존 대화 표시
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🍁" if msg["role"] == "assistant" else "🧑"):
        st.markdown(msg["content"])
        # 참고 자료 표시
        if msg.get("references"):
            with st.expander(f"📚 참고 자료 ({len(msg['references'])}건)", expanded=False):
                _render_references(msg["references"])

# ── 참고 자료 렌더링 함수 ──────────────────────────────


def _render_references(references: list[dict]):
    """참고 문서 카드 렌더링."""
    for ref in references:
        score = ref.get("similarity_score", 0)
        score_bar = "🟢" if score > 0.8 else "🟡" if score > 0.6 else "🔴"
        st.markdown(
            f"""<div class="ref-card">
                <div class="ref-title">{ref.get('제목', '제목 없음')}</div>
                <div class="ref-meta">
                    {ref.get('직업군', '')} > {ref.get('직업', '')} | {ref.get('작성일', '')} | {score_bar} 유사도 {score:.2f}
                </div>
                <div class="ref-body">{ref.get('본문_요약', '')[:200]}...</div>
            </div>""",
            unsafe_allow_html=True,
        )


# ── 채팅 입력 처리 ─────────────────────────────────────

if prompt := st.chat_input("메이플스토리에 대해 궁금한 것을 물어보세요!"):
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # AI 응답
    with st.chat_message("assistant", avatar="🍁"):
        try:
            if use_streaming:
                # 스트리밍 응답
                answer_placeholder = st.empty()
                full_answer = ""
                references = []

                with st.spinner("검색 중..."):
                    for event in chat_stream(prompt, top_k=top_k, use_cot=use_cot):
                        if event["type"] == "answer_chunk":
                            full_answer += event["content"]
                            answer_placeholder.markdown(full_answer + "▌")
                        elif event["type"] == "done":
                            answer_placeholder.markdown(full_answer)
                        elif event["type"] == "references":
                            references = event["content"]
                        elif event["type"] == "error":
                            st.error(f"오류: {event['content']}")

                # 참고 자료 표시
                if references:
                    with st.expander(f"📚 참고 자료 ({len(references)}건)", expanded=False):
                        _render_references(references)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer,
                    "references": references,
                })

            else:
                # 동기 응답
                with st.spinner("답변 생성 중..."):
                    result = chat(prompt, top_k=top_k, use_cot=use_cot)

                st.markdown(result["answer"])

                references = result.get("references", [])
                if references:
                    with st.expander(f"📚 참고 자료 ({len(references)}건)", expanded=False):
                        _render_references(references)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "references": references,
                })

        except Exception as e:
            error_msg = f"⚠️ 오류가 발생했습니다: {str(e)}"
            st.error(error_msg)
            st.info("💡 백엔드 서버가 실행 중인지 확인해주세요. (`uvicorn app.main:app`)")
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })
