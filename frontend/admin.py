"""관리자 UI: 헬스, 크롤링, 세션, Qdrant 저장 내용 조회."""
import streamlit as st

from api_client import (
    admin_crawl_history,
    admin_crawl_status,
    admin_crawl_trigger,
    admin_health,
    admin_qdrant_documents,
    admin_qdrant_stats,
    delete_session,
    get_session,
    list_sessions,
)

st.set_page_config(
    page_title="관리자",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.stApp { background: linear-gradient(180deg, #0e1117 0%, #1a1d24 100%); }
section[data-testid="stSidebar"] { background: #1e1e2e; }
</style>
""", unsafe_allow_html=True)

st.title("🍁 메이플 챗봇 — 관리자")

tab1, tab2, tab3, tab4 = st.tabs([
    "대시보드",
    "크롤링",
    "채팅 사용자(세션)",
    "Qdrant 저장 내용",
])

# ── 대시보드 ─────────────────────────────────────────
with tab1:
    st.header("헬스 & Qdrant 요약")
    col1, col2 = st.columns(2)
    with col1:
        try:
            health = admin_health()
            status = health.get("status", "?")
            qdrant = health.get("qdrant_status", "?")
            count = health.get("document_count", 0)
            st.metric("API 상태", status)
            st.metric("Qdrant", qdrant)
            st.metric("문서 수", count)
        except Exception as e:
            st.error(f"헬스 조회 실패: {e}")
    with col2:
        try:
            stats = admin_qdrant_stats()
            st.metric("전체 포인트 수", stats.get("points_count", 0))
            jobs = stats.get("jobs", {})
            groups = stats.get("groups", {})
            st.caption("직업군 수: %d | 직업 수: %d" % (len(groups), len(jobs)))
        except Exception as e:
            st.warning(f"Qdrant 통계 실패: {e}")

# ── 크롤링 ───────────────────────────────────────────
with tab2:
    st.header("크롤링 상태 & 수동 실행")
    try:
        status = admin_crawl_status()
        st.write("**스케줄러:**", "실행 중" if status.get("scheduler_running") else "중지")
        st.write("**현재 크롤링:**", "진행 중" if status.get("is_crawling") else "대기 중")
        st.write("**마지막 실행:**", status.get("last_run_at") or "-")
        st.write("**다음 실행:**", status.get("next_run_at") or "-")
        if status.get("last_result"):
            r = status["last_result"]
            st.write("**마지막 결과:** 크롤링 %d → 적재 %d, 에러 %d (%.1f초)" % (
                r.get("crawled", 0), r.get("upserted", 0), r.get("errors", 0), r.get("elapsed_seconds", 0)
            ))
    except Exception as e:
        st.error(str(e))

    st.subheader("수동 크롤링 실행")
    with st.form("crawl_form"):
        max_jobs = st.number_input("직업군당 최대 직업 수 (0=전체)", min_value=0, max_value=50, value=3)
        max_pages = st.number_input("직업별 페이지 수", min_value=1, max_value=10, value=1)
        max_posts = st.number_input("페이지당 최대 게시글 수", min_value=1, max_value=50, value=10)
        submitted = st.form_submit_button("크롤링 실행")
    if submitted:
        if status.get("is_crawling"):
            st.warning("이미 크롤링이 진행 중입니다.")
        else:
            with st.spinner("크롤링 실행 중..."):
                try:
                    result = admin_crawl_trigger(
                        max_jobs_per_group=None if max_jobs == 0 else max_jobs,
                        max_pages=max_pages,
                        max_posts_per_page=max_posts,
                    )
                    st.success("완료: 크롤링 %d → 적재 %d, 에러 %d (%.1f초)" % (
                        result.get("crawled", 0), result.get("upserted", 0),
                        result.get("errors", 0), result.get("elapsed_seconds", 0)
                    ))
                except Exception as e:
                    st.error(str(e))

    st.subheader("최근 크롤링 이력")
    try:
        history = admin_crawl_history()
        if history:
            st.dataframe(history, use_container_width=True)
        else:
            st.caption("이력 없음")
    except Exception as e:
        st.error(str(e))

# ── 채팅 사용자(세션) ─────────────────────────────────
with tab3:
    st.header("세션 목록 (채팅 사용자)")
    page_size = 50
    offset = st.number_input("오프셋 (0부터)", min_value=0, value=0, key="sess_offset")
    if st.button("새로고침"):
        st.rerun()
    try:
        sessions = list_sessions(limit=page_size, offset=offset)
        if not sessions:
            st.info("세션이 없습니다.")
        else:
            for s in sessions:
                with st.expander("[%s] %s — %d 메시지" % (s.get("id", "")[:8], s.get("title", ""), s.get("message_count", 0))):
                    st.write("생성:", s.get("created_at"), "| 수정:", s.get("updated_at"))
                    if st.button("상세 보기", key="detail_" + s.get("id", "")):
                        detail = get_session(s.get("id", ""))
                        if detail:
                            for m in detail.get("messages", []):
                                st.markdown("**%s:** %s" % (m.get("role", ""), (m.get("content", ""))[:200]))
                    if st.button("삭제", key="del_" + s.get("id", "")):
                        delete_session(s.get("id", ""))
                        st.success("삭제됨")
                        st.rerun()
    except Exception as e:
        st.error(str(e))

# ── Qdrant 저장 내용 조회 ─────────────────────────────
with tab4:
    st.header("Qdrant 저장 문서 조회")
    col1, col2, col3 = st.columns(3)
    with col1:
        job_filter = st.text_input("직업 필터 (비우면 전체)", key="job_f")
    with col2:
        group_filter = st.text_input("직업군 필터 (비우면 전체)", key="group_f")
    with col3:
        doc_limit = st.number_input("건수", min_value=1, max_value=100, value=20)
    if "qdrant_next_offset" not in st.session_state:
        st.session_state.qdrant_next_offset = None
    do_query = st.button("조회")
    if do_query:
        st.session_state.qdrant_next_offset = None
        st.rerun()
    try:
        data = admin_qdrant_documents(
            job=job_filter or None,
            job_group=group_filter or None,
            limit=doc_limit,
            offset=str(st.session_state.qdrant_next_offset) if st.session_state.qdrant_next_offset is not None else None,
        )
        items = data.get("items", [])
        next_offset = data.get("next_offset")
        if items:
            rows = []
            for it in items:
                body = it.get("본문", "") or ""
                rows.append({
                    "id": it.get("id"),
                    "직업": it.get("직업", ""),
                    "직업군": it.get("직업군", ""),
                    "제목": ((it.get("제목", ""))[:60] + "…") if len(it.get("제목", "")) > 60 else it.get("제목", ""),
                    "본문 미리보기": (body[:80] + "…") if len(body) > 80 else body,
                })
            st.dataframe(rows, use_container_width=True)
            if next_offset is not None:
                if st.button("다음 페이지"):
                    st.session_state.qdrant_next_offset = next_offset
                    st.rerun()
        else:
            st.info("조건에 맞는 문서가 없습니다.")
    except Exception as e:
        st.error(str(e))
