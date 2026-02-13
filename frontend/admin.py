"""관리자 UI: 헬스, 크롤링, 세션, Qdrant 저장 내용 조회."""
import time
import streamlit as st

from api_client import (
    admin_crawl_history,
    admin_crawl_status,
    admin_crawl_trigger,
    admin_health,
    admin_qdrant_documents,
    admin_qdrant_stats,
    admin_suggested_since_date,
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
        prog = status.get("crawl_progress") or {}
        jobs_done, jobs_total = prog.get("jobs_done", 0), prog.get("jobs_total", 0)
        if status.get("is_crawling"):
            if jobs_total > 0:
                st.write("**현재 크롤링:**", f"진행 중 ({jobs_done}/{jobs_total} 직업·게시판)")
            else:
                st.write("**현재 크롤링:**", "진행 중")
            st.caption("진행 중일 때 아래 버튼으로 새로고침하면 진행 상황이 갱신됩니다.")
        else:
            st.write("**현재 크롤링:**", "대기 중")
        if st.button("상태 새로고침", key="refresh_crawl_status"):
            st.rerun()
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
    try:
        suggested = admin_suggested_since_date()
    except Exception as e:
        suggested = None
        st.warning(f"수집 시작일 API 호출 실패: {e}")
    if suggested:
        st.info(f"자동 제안된 수집 시작일: **{suggested}** (저장된 크롤 날짜 또는 Qdrant 최신 문서 기준)")
    else:
        st.caption("자동 제안 없음 — 아래에서 수집 시작일을 직접 입력해 주세요.")
    if st.button("제안 날짜 다시 불러오기", key="refresh_suggested"):
        st.rerun()
    with st.form("crawl_form"):
        max_jobs = st.number_input("직업군당 최대 직업 수 (0=전체)", min_value=0, max_value=50, value=0)
        max_pages = st.number_input("직업별 페이지 수", min_value=1, max_value=50, value=10)
        max_posts = st.number_input("페이지당 최대 게시글 수", min_value=1, max_value=200, value=100)
        if suggested:
            since_date_label = "수집 시작일 (YYYY-MM-DD) — 자동 제안됨"
            since_date_placeholder = ""
            since_date_help = "저장된 마지막 크롤 날짜 또는 Qdrant 최신 문서 날짜 기준으로 자동 채움."
        else:
            since_date_label = "수집 시작일 (YYYY-MM-DD)"
            since_date_placeholder = "정보없음 수동입력 필요"
            since_date_help = "자동 제안 없음. 위에 표시된 대로 날짜를 직접 입력해 주세요."
        since_date = st.text_input(
            since_date_label,
            value=suggested or "",
            placeholder=since_date_placeholder,
            help=since_date_help,
            key="since_date_input",
        )
        if not suggested and not since_date:
            st.caption("⚠️ 정보없음 — 수동입력 필요")
        submitted = st.form_submit_button("크롤링 실행")
    if submitted:
        if status.get("is_crawling"):
            st.warning("이미 크롤링이 진행 중입니다.")
        else:
            try:
                result = admin_crawl_trigger(
                    max_jobs_per_group=None if max_jobs == 0 else max_jobs,
                    max_pages=max_pages,
                    max_posts_per_page=max_posts,
                    since_date=since_date.strip() if since_date.strip() else None,
                    background=True,
                )
                # 202 = 백그라운드 시작 → 진행률·로그 폴링
                if result.get("crawled", 0) == 0 and result.get("message", "").find("백그라운드") != -1:
                    progress_placeholder = st.empty()
                    log_placeholder = st.empty()
                    while True:
                        s = admin_crawl_status()
                        prog = s.get("crawl_progress") or {}
                        jd, jt = prog.get("jobs_done", 0), prog.get("jobs_total", 0)
                        logs = s.get("recent_logs") or []
                        progress_placeholder.markdown(
                            "**○ 크롤링 실행 중...** " + (f"({jd}/{jt} 직업·게시판)" if jt > 0 else "")
                        )
                        with log_placeholder.container():
                            st.caption("진행 로그")
                            st.code("\n".join(logs) if logs else "(로그 대기 중...)", language="text")
                        if not s.get("is_crawling"):
                            break
                        time.sleep(2)
                    progress_placeholder.empty()
                    log_placeholder.empty()
                    r = s.get("last_result")
                    if r:
                        st.success("완료: 크롤링 %d → 적재 %d, 스킵 %d, 에러 %d (%.1f초)" % (
                            r.get("crawled", 0), r.get("upserted", 0),
                            r.get("skipped", 0), r.get("errors", 0),
                            r.get("elapsed_seconds", 0),
                        ))
                    st.rerun()
                else:
                    st.success("완료: 크롤링 %d → 적재 %d, 스킵 %d, 에러 %d (%.1f초)" % (
                        result.get("crawled", 0), result.get("upserted", 0),
                        result.get("skipped", 0), result.get("errors", 0),
                        result.get("elapsed_seconds", 0),
                    ))
            except Exception as e:
                st.error(str(e))

    st.subheader("최근 크롤링 이력")
    try:
        history = admin_crawl_history()
        if history:
            st.dataframe(history, width="stretch")
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
            st.dataframe(rows, width="stretch")
            if next_offset is not None:
                if st.button("다음 페이지"):
                    st.session_state.qdrant_next_offset = next_offset
                    st.rerun()
        else:
            st.info("조건에 맞는 문서가 없습니다.")
    except Exception as e:
        st.error(str(e))
