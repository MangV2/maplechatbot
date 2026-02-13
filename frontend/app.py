"""메이플스토리 RAG 챗봇 — Streamlit UI."""
import streamlit as st

from api_client import (
    chat,
    chat_stream,
    create_session,
    delete_session,
    get_session,
    health_check,
    list_sessions,
    save_message,
)

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

/* ── 사이드바 ─────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #1e1e2e;
    border-right: 1px solid #30363d;
}

/* 새 채팅 버튼: 아이콘+텍스트 스타일 */
section[data-testid="stSidebar"] .new-chat-btn button {
    background: transparent !important;
    border: 1px solid #444 !important;
    border-radius: 24px !important;
    color: #e0e0e0 !important;
    font-size: 0.92em !important;
    padding: 8px 18px !important;
    transition: background 0.2s;
}
section[data-testid="stSidebar"] .new-chat-btn button:hover {
    background: #2a2a3e !important;
    border-color: #666 !important;
}

/* 세션 행: 기본 상태 — 삭제 버튼 숨김 */
.session-row {
    display: flex;
    align-items: center;
    border-radius: 8px;
    transition: background 0.15s;
    position: relative;
}

/* 사이드바 내부 columns 간격 줄이기 */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    gap: 0 !important;
}

/* 세션 선택 버튼: 투명 배경 */
section[data-testid="stSidebar"] .sess-btn button {
    background: transparent !important;
    border: none !important;
    color: #c9d1d9 !important;
    text-align: left !important;
    padding: 8px 12px !important;
    border-radius: 8px !important;
    font-size: 0.88em !important;
    transition: background 0.15s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
section[data-testid="stSidebar"] .sess-btn button:hover {
    background: #2a2a3e !important;
}
section[data-testid="stSidebar"] .sess-btn button:disabled {
    background: #2d3555 !important;
    color: #e0e0e0 !important;
    opacity: 1 !important;
}

/* 삭제(⋮) 버튼: 기본 숨김, 행 호버 시 표시 */
section[data-testid="stSidebar"] .del-btn {
    opacity: 0;
    transition: opacity 0.15s;
}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:hover .del-btn {
    opacity: 1;
}
section[data-testid="stSidebar"] .del-btn button {
    background: transparent !important;
    border: none !important;
    color: #8b949e !important;
    padding: 4px 6px !important;
    border-radius: 6px !important;
    font-size: 1em !important;
    min-width: 0 !important;
}
section[data-testid="stSidebar"] .del-btn button:hover {
    background: #3d2020 !important;
    color: #ff6b6b !important;
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

/* 웰컴 화면 */
.welcome-box {
    text-align: center;
    padding: 60px 20px;
    color: #8b949e;
}
.welcome-box h2 {
    color: #c9d1d9;
    margin-bottom: 10px;
}
.example-chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 20px;
}
.example-chip {
    background: #1c2333;
    border: 1px solid #30363d;
    border-radius: 20px;
    padding: 8px 16px;
    color: #c9d1d9;
    font-size: 0.85em;
}

/* 섹션 라벨 */
.sidebar-label {
    color: #8b949e;
    font-size: 0.78em;
    font-weight: 500;
    padding: 12px 12px 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
</style>
""", unsafe_allow_html=True)


# ── 헬퍼 함수 ──────────────────────────────────────────


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


def _ensure_session():
    """현재 세션이 없으면 생성."""
    if not st.session_state.get("current_session_id"):
        resp = create_session()
        st.session_state.current_session_id = resp["id"]
        st.session_state.messages = []


def _load_session(session_id: str):
    """서버에서 세션 데이터를 불러와 세션 상태에 설정."""
    data = get_session(session_id)
    if data:
        st.session_state.current_session_id = data["id"]
        st.session_state.messages = data.get("messages", [])
    else:
        st.session_state.current_session_id = None
        st.session_state.messages = []


def _start_new_chat():
    """새 대화 시작."""
    resp = create_session()
    st.session_state.current_session_id = resp["id"]
    st.session_state.messages = []


# ── 세션 상태 초기화 ──────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# ── 사이드바 ──────────────────────────────────────────

with st.sidebar:
    # ── 새 채팅 버튼 (Gemini 스타일: 둥근 아웃라인) ──
    with st.container():
        st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
        if st.button("✏️  새 채팅", width="stretch"):
            _start_new_chat()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")  # 여백

    # ── 이전 대화 목록 ──
    sessions = list_sessions()

    if sessions:
        st.markdown('<div class="sidebar-label">이전 대화</div>', unsafe_allow_html=True)

        for s in sessions:
            session_id = s["id"]
            title = s["title"]
            is_active = session_id == st.session_state.get("current_session_id")

            max_len = 20
            display_title = title if len(title) <= max_len else title[:max_len] + "..."

            col_title, col_menu = st.columns([6, 1])

            with col_title:
                st.markdown('<div class="sess-btn">', unsafe_allow_html=True)
                if st.button(
                    display_title,
                    key=f"sess_{session_id}",
                    width="stretch",
                    disabled=is_active,
                ):
                    _load_session(session_id)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            with col_menu:
                st.markdown('<div class="del-btn">', unsafe_allow_html=True)
                if st.button("⋮", key=f"menu_{session_id}", help="삭제"):
                    delete_session(session_id)
                    if session_id == st.session_state.get("current_session_id"):
                        st.session_state.current_session_id = None
                        st.session_state.messages = []
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.caption("아직 대화가 없습니다.")

    # ── 하단: 설정 ──
    st.markdown("---")
    with st.expander("⚙️ 설정", expanded=False):
        use_streaming = st.toggle("스트리밍 응답", value=True, help="답변을 실시간으로 표시")
        top_k = st.slider("참고 문서 수", min_value=1, max_value=10, value=5)
        use_cot = st.toggle("CoT 질문 분석", value=True, help="질문을 분석하여 관련 직업 필터링")

        st.divider()
        st.markdown("##### 📊 시스템 상태")
        if st.button("상태 확인", width="stretch"):
            status = health_check()
            if status.get("status") == "ok":
                st.success(f"✅ 연결됨 | 문서: {status.get('document_count', 0):,}개")
            else:
                st.error(f"❌ {status.get('qdrant_status', '연결 실패')}")

# ── 메인 화면 ──────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1>🍁 메이플 챗봇</h1>
    <p>메이플스토리 인벤 게시판 기반 AI 어드바이저</p>
</div>
""", unsafe_allow_html=True)

# ── 기존 대화 표시 ─────────────────────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🍁" if msg["role"] == "assistant" else "🧑"):
        st.markdown(msg["content"])
        if msg.get("references"):
            with st.expander(f"📚 참고 자료 ({len(msg['references'])}건)", expanded=False):
                _render_references(msg["references"])

# 대화가 비어있으면 웰컴 메시지
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-box">
        <h2>무엇이든 물어보세요!</h2>
        <p>메이플스토리 인벤 게시판의 최신 정보를 기반으로 답변합니다.</p>
        <div class="example-chips">
            <div class="example-chip">아크 보스 세팅 추천해줘</div>
            <div class="example-chip">제로 쿨뚝 필요한가요?</div>
            <div class="example-chip">메소 효율 좋은 직업은?</div>
            <div class="example-chip">보스 데미지 올리는 법</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── 채팅 입력 처리 ─────────────────────────────────────

if prompt := st.chat_input("메이플스토리에 대해 궁금한 것을 물어보세요!"):
    # 세션이 없으면 자동 생성
    _ensure_session()
    session_id = st.session_state.current_session_id

    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(session_id, "user", prompt)

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
                save_message(session_id, "assistant", full_answer, references or None)

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
                save_message(session_id, "assistant", result["answer"], references or None)

        except Exception as e:
            error_msg = f"⚠️ 오류가 발생했습니다: {str(e)}"
            st.error(error_msg)
            st.info("💡 백엔드 서버가 실행 중인지 확인해주세요.")
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })
