"""관리자 UI: 헬스, 크롤링, 세션, Qdrant 저장 내용 조회."""
import time
import streamlit as st

from api_client import (
    admin_crawl_history,
    admin_crawl_status,
    admin_crawl_trigger,
    admin_delete_session,
    admin_get_session,
    admin_health,
    admin_list_sessions,
    admin_list_users,
    admin_qdrant_documents,
    admin_qdrant_filter_options,
    admin_qdrant_stats,
    admin_suggested_since_date,
    admin_user_count,
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
            try:
                user_count = admin_user_count()
                st.metric("가입 회원 수", user_count)
            except Exception:
                pass
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
        crawl_mode_sel = st.selectbox(
            "크롤링 대상",
            options=["all", "job_only", "flat_only"],
            format_func=lambda x: {"all": "전체", "job_only": "직업게시판만", "flat_only": "단일게시판만"}[x],
            index=0,
            help="직업게시판(전사/마법사/궁수/도적/해적), 단일게시판(실시간소식/팁과노하우/질문과답변)",
        )
        crawl_mode = crawl_mode_sel
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
                    since_date=since_date.strip() if since_date.strip() else None,
                    crawl_mode=crawl_mode,
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
    users = admin_list_users()
    user_options = [("전체", None), ("익명만", "__anonymous__")]
    user_options += [
        (f"{u['email']} ({u.get('main_character_name') or '-'})", u["id"])
        for u in users
    ]
    selected_idx = st.selectbox(
        "사용자별 필터",
        range(len(user_options)),
        format_func=lambda i: user_options[i][0],
        key="sess_user_filter",
    )
    selected_user_id = user_options[selected_idx][1]

    page_size = 50
    offset = st.number_input("오프셋 (0부터)", min_value=0, value=0, key="sess_offset")
    if st.button("새로고침", key="sess_refresh"):
        st.rerun()
    try:
        sessions = admin_list_sessions(
            limit=page_size, offset=offset, user_id=selected_user_id
        )
        user_map = {u["id"]: u["email"] for u in users}
        if not sessions:
            st.info("세션이 없습니다.")
        else:
            for s in sessions:
                uid = s.get("user_id")
                user_label = user_map.get(uid, uid[:8] + "…") if uid else "익명"
                with st.expander("[%s] %s — %d 메시지 | %s" % (s.get("id", "")[:8], s.get("title", ""), s.get("message_count", 0), user_label)):
                    st.write("생성:", s.get("created_at"), "| 수정:", s.get("updated_at"), "| 사용자:", user_label)
                    if st.button("상세 보기", key="detail_" + s.get("id", "")):
                        detail = admin_get_session(s.get("id", ""))
                        if detail:
                            for m in detail.get("messages", []):
                                st.markdown("**%s:** %s" % (m.get("role", ""), (m.get("content", ""))[:200]))
                    if st.button("삭제", key="del_" + s.get("id", "")):
                        admin_delete_session(s.get("id", ""))
                        st.success("삭제됨")
                        st.rerun()
    except Exception as e:
        st.error(str(e))

# ── Qdrant 저장 내용 조회 ─────────────────────────────
with tab4:
    st.header("Qdrant 저장 문서 조회")
    try:
        filter_opts = admin_qdrant_filter_options()
        job_board_options = filter_opts.get("job_boards", [])
        flat_board_options = filter_opts.get("flat_boards", [])
    except Exception:
        job_board_options = []
        flat_board_options = []

    board_type = st.selectbox(
        "게시판 유형",
        options=["전체", "직업게시판", "단일게시판"],
        index=0,
        key="qdrant_board_type",
    )

    sub_board_options = []
    job_filter_val = None
    group_filter_val = None

    if board_type == "직업게시판" and job_board_options:
        sub_board_options = [""] + job_board_options
        sel = st.selectbox(
            "세부 게시판 (직업)",
            options=sub_board_options,
            format_func=lambda x: "(전체)" if x == "" else x,
            key="qdrant_job_board_sel",
        )
        if sel:
            job_filter_val = sel
    elif board_type == "단일게시판" and flat_board_options:
        sub_board_options = [""] + flat_board_options
        sel = st.selectbox(
            "세부 게시판",
            options=sub_board_options,
            format_func=lambda x: "(전체)" if x == "" else x,
            key="qdrant_flat_board_sel",
        )
        group_filter_val = "정보공유"
        if sel:
            job_filter_val = sel

    doc_limit = st.number_input("건수", min_value=1, max_value=100, value=20, key="qdrant_doc_limit")

    if "qdrant_next_offset" not in st.session_state:
        st.session_state.qdrant_next_offset = None
    do_query = st.button("조회", key="qdrant_do_query")
    if do_query:
        st.session_state.qdrant_next_offset = None
        st.rerun()
    try:
        data = admin_qdrant_documents(
            job=job_filter_val,
            job_group=group_filter_val,
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
                if st.button("다음 페이지", key="qdrant_next_page"):
                    st.session_state.qdrant_next_offset = next_offset
                    st.rerun()
        else:
            st.info("조건에 맞는 문서가 없습니다.")
    except Exception as e:
        st.error(str(e))
