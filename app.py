import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from supabase import create_client
import os
import json
import re
from datetime import datetime


# ── API 키 설정 ──────────────────────────────────────────────
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


# ── Supabase 연결 ────────────────────────────────────────────
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── 세션 상태 초기화 ─────────────────────────────────────────
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


# ── DB 함수 ─────────────────────────────────────────────────
def log_data(input_text, output_text, input_type="text", parsed_json=None):
    if supabase:
        try:
            payload = {
                "input": input_text,
                "output": output_text,
                "input_type": input_type,
            }

            if parsed_json is not None:
                payload["parsed_json"] = parsed_json

            supabase.table("usage_logs").insert(payload).execute()
        except Exception as e:
            print(f"DB 오류: {e}")


def get_recent_logs(limit=5):
    if not supabase:
        return []

    try:
        response = (
            supabase.table("usage_logs")
            .select("id, created_at, parsed_json")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response.data else []
    except Exception as e:
        print(f"최근 기록 조회 오류: {e}")
        return []


def format_kst_datetime(dt_str):
    if not dt_str:
        return "-"

    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str


# ── 프롬프트 팩 생성 ─────────────────────────────────────────
def build_prompt_pack(summary, due_date, tasks, deliverables, warnings):
    tasks_text = "\n".join([f"- {x}" for x in tasks]) if tasks else "- 공지 확인 필요"
    deliverables_text = "\n".join([f"- {x}" for x in deliverables]) if deliverables else "- 공지 확인 필요"
    warnings_text = "\n".join([f"- {x}" for x in warnings]) if warnings else "- 공지 확인 필요"

    detail_prompt = f"""아래 대학 과제 공지를 바탕으로 내가 실제로 해야 할 일을 초보 대학생도 이해할 수 있게 자세히 설명해줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 이 과제의 목적
2. 내가 실제로 해야 할 일 순서
3. 제출 전에 체크할 것
4. 실수하기 쉬운 부분
"""

    report_prompt = f"""아래 과제 공지를 바탕으로 보고서/과제 초안을 준비하려고 해.
교수 공지 내용을 반영해서 실전적으로 도와줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 과제 수행 순서
2. 보고서 또는 과제 결과물의 추천 목차
3. 각 목차에 들어갈 핵심 내용
4. 지금 바로 시작할 수 있는 초안
"""

    presentation_prompt = f"""아래 대학 과제 공지를 바탕으로 발표 준비를 도와줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 발표 준비 순서
2. PPT 구성안
3. 발표 대본 개요
4. 발표 때 강조해야 할 핵심 포인트
"""

    team_prompt = f"""아래 대학 과제 공지를 바탕으로 팀플 역할분담안을 짜줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 팀플 진행 순서
2. 역할 분담안
3. 팀원별 할 일 예시
4. 마감 전까지 일정표 초안
"""

    return {
        "자세한 설명용": detail_prompt,
        "보고서/과제 초안용": report_prompt,
        "발표 준비용": presentation_prompt,
        "팀플 역할분담용": team_prompt,
    }


# ── 시스템 프롬프트 ──────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국 대학생 전용 '과제 공지 워크플로우 정리 AI'입니다.

[목표]
교수님의 공지문이나 과제 안내문을 분석해서,
학생이 바로 행동할 수 있도록 핵심 정보만 구조화하세요.

[중요 원칙]
- 한국어로만 답하세요.
- 없는 정보는 절대 추측하지 말고 "공지 확인 필요"라고 쓰세요.
- 장황한 설명, 인사말, 감탄문 금지
- 반드시 JSON 하나만 출력하세요.
- 코드블록(```json)로 감싸지 마세요.
- JSON 바깥의 텍스트를 절대 추가하지 마세요.

[출력 JSON 형식]
{
  "summary": "과제명까지 자연스럽게 포함한 공지 핵심 요약 2~3문장",
  "due_date": "마감일/제출일/발표일. 없으면 공지 확인 필요",
  "tasks": [
    "학생이 해야 할 행동 1",
    "학생이 해야 할 행동 2"
  ],
  "deliverables": [
    "제출해야 하는 결과물 1",
    "제출해야 하는 결과물 2",
    "제출 형식: PDF 업로드"
  ],
  "warnings": [
    "주의사항 1",
    "주의사항 2"
  ],
  "ai_prompt": "이 공지를 바탕으로 ChatGPT나 Gemini에 바로 넣을 실용적인 프롬프트",
  "calendar_text": "캘린더에 넣기 쉬운 한 줄 일정 문구"
}

[작성 규칙]
- summary에는 가능하면 과제명/발표명을 자연스럽게 포함하세요.
- tasks는 실제 행동 단위로 작성
- deliverables에는 제출 형식이 있으면 함께 포함
- warnings는 감점/형식/마감 관련 리스크 위주
- ai_prompt는 범용 AI에 바로 붙여넣기 좋게 작성
- calendar_text는 다음 느낌으로 작성:
  "3월 28일 23:59 / 운영체제 과제 2 제출 / PDF 업로드"
"""


# ── 유틸 함수 ────────────────────────────────────────────────
def safe_json_parse(text: str):
    if not text:
        return None

    cleaned = text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    cleaned = cleaned.replace("“", "\"").replace("”", "\"")
    cleaned = cleaned.replace("‘", "'").replace("’", "'")

    try:
        return json.loads(cleaned)
    except Exception as e:
        print("JSON 파싱 실패 원문:", cleaned)
        print("JSON 파싱 에러:", e)
        return None


def parse_korean_due_date(due_date_str):
    if not due_date_str or "확인" in due_date_str or "없" in due_date_str:
        return None

    from datetime import timedelta

    try:
        is_pm = "오후" in due_date_str
        is_am = "오전" in due_date_str

        # ── 시간 파싱 헬퍼 ──────────────────────────────────────
        def extract_time(text):
            """문자열에서 시간 추출. '21시', '21:30', '오후 6:00' 형태 처리."""
            t = re.search(r"(\d{1,2}):(\d{2})", text)
            if t:
                h, m = int(t.group(1)), int(t.group(2))
            else:
                t2 = re.search(r"(\d{1,2})\s*시", text)
                h, m = (int(t2.group(1)), 0) if t2 else (23, 59)
            if is_pm and h != 12:
                h += 12
            elif is_am and h == 12:
                h = 0
            return h, m

        # ── 1) 요일 표현 처리 ("수요일 21시", "다음 주 금요일") ──
        WEEKDAY_KR = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
        weekday_m = re.search(r"([월화수목금토일])요일", due_date_str)
        if weekday_m:
            target_wd = WEEKDAY_KR[weekday_m.group(1)]
            today = datetime.now()
            days_ahead = target_wd - today.weekday()
            # "다음 주" 명시 → 무조건 다음 주
            if "다음" in due_date_str:
                if days_ahead <= 0:
                    days_ahead += 7
            else:
                # 이미 지난 요일이면 다음 주로
                if days_ahead < 0:
                    days_ahead += 7
            target_date = today + timedelta(days=days_ahead)
            hour, minute = extract_time(due_date_str)
            return datetime(target_date.year, target_date.month, target_date.day, hour, minute)

        # ── 2) 날짜 직접 표기 처리 ("6월 22일", "2026.6.22", 등) ──
        pattern = r"(\d{4})?\s*[년.]?\s*(\d{1,2})\s*[월/.]\s*(\d{1,2})\s*[일.]?"
        m = re.search(pattern, due_date_str)
        if not m:
            return None

        year = int(m.group(1)) if m.group(1) else datetime.now().year
        month = int(m.group(2))
        day = int(m.group(3))
        hour, minute = extract_time(due_date_str)  # 시간은 헬퍼로 통일

        dt = datetime(year, month, day, hour, minute)

        # 연도 생략 시 6개월 이상 과거면 다음 해로 보정
        if not m.group(1):
            if datetime.now() - dt > timedelta(days=180):
                dt = dt.replace(year=dt.year + 1)

        return dt
    except Exception:
        return None


def generate_ics(event_dt, title, description):
    from datetime import timedelta

    def ics_escape(text):
        return (
            text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    dtstart = event_dt.strftime("%Y%m%dT%H%M%S")
    dtend = (event_dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    uid = f"{event_dt.strftime('%Y%m%d%H%M')}-gwaje@copilot"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GwajeCopilot//KR",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;TZID=Asia/Seoul:{dtstart}",
        f"DTEND;TZID=Asia/Seoul:{dtend}",
        f"SUMMARY:{ics_escape(title)}",
        f"DESCRIPTION:{ics_escape(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines).encode("utf-8")


def build_google_calendar_url(event_dt, title, description):
    from datetime import timedelta
    import urllib.parse

    dtstart = event_dt.strftime("%Y%m%dT%H%M%S")
    dtend = (event_dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{dtstart}/{dtend}",
        "details": description,
        "ctz": "Asia/Seoul",
    }
    return "https://www.google.com/calendar/render?" + urllib.parse.urlencode(params)


def normalize_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def get_value(data, key, default="공지 확인 필요"):
    value = data.get(key, default)
    if isinstance(value, str):
        return value.strip() if value.strip() else default
    return value if value else default


def read_only_box(value, height=220, key_suffix="default"):
    text_value = value if value else "공지 확인 필요"
    text_id = f"text_{key_suffix}".replace(" ", "_").replace("/", "_")

    escaped = (
        text_value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    html_code = f"""
    <div style="margin-top: 8px; margin-bottom: 8px;">
        <textarea id="{text_id}"
            style="
                width: 100%;
                height: {height}px;
                padding: 14px;
                font-size: 15px;
                line-height: 1.7;
                color: #1a1a2e;
                background: #ffffff;
                border: 1px solid rgba(102,126,234,0.25);
                border-radius: 12px;
                resize: vertical;
                box-sizing: border-box;
                box-shadow: inset 0 2px 6px rgba(0,0,0,0.05), 0 1px 4px rgba(102,126,234,0.08);
            ">{escaped}</textarea>
    </div>

    <button
        onclick="
            const text = document.getElementById('{text_id}').value;
            navigator.clipboard.writeText(text).then(() => {{
                this.innerText = '복사 완료';
                setTimeout(() => this.innerText = '복사하기', 1200);
            }}).catch(() => {{
                this.innerText = '복사 실패';
                setTimeout(() => this.innerText = '복사하기', 1200);
            }});
        "
        onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 6px 18px rgba(102,126,234,0.48)';"
        onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 14px rgba(102,126,234,0.38), 0 1px 3px rgba(0,0,0,0.10)';"
        style="
            width: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-bottom: 2px solid rgba(80,40,140,0.25);
            border-radius: 10px;
            padding: 11px 16px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            margin-top: 6px;
            margin-bottom: 6px;
            box-shadow: 0 4px 14px rgba(102,126,234,0.38), 0 1px 3px rgba(0,0,0,0.10);
            transition: transform 0.12s ease, box-shadow 0.12s ease;
        "
    >
        복사하기
    </button>
    """

    components.html(html_code, height=height + 80, scrolling=False)

def build_prompt_pack(summary, due_date, tasks, deliverables, warnings):
    tasks_text = "\n".join([f"- {x}" for x in tasks]) if tasks else "- 공지 확인 필요"
    deliverables_text = "\n".join([f"- {x}" for x in deliverables]) if deliverables else "- 공지 확인 필요"
    warnings_text = "\n".join([f"- {x}" for x in warnings]) if warnings else "- 공지 확인 필요"

    detail_prompt = f"""너는 대학 과제를 처음 해보는 학생에게 설명해주는 조교 역할이다.

아래 과제 공지를 바탕으로 내가 실제로 무엇을 해야 하는지 아주 쉽게 설명해줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 이 과제가 뭔지 쉽게 설명
2. 내가 해야 할 일 순서대로 정리
3. 제출 직전 체크리스트
4. 실수하기 쉬운 부분
"""

    report_prompt = f"""너는 대학 과제 작성 코치를 맡은 AI다.

아래 과제 공지를 바탕으로 보고서나 과제 초안을 바로 시작할 수 있게 도와줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 과제 수행 순서
2. 추천 목차
3. 각 목차에 들어갈 핵심 내용
4. 바로 제출 초안으로 이어질 수 있는 예시 문단
"""

    presentation_prompt = f"""너는 대학 발표 준비를 도와주는 발표 코치 AI다.

아래 과제 공지를 바탕으로 발표 준비에 필요한 내용을 정리해줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 발표 준비 순서
2. PPT 슬라이드 구성안
3. 발표 대본 개요
4. 발표 때 강조할 핵심 포인트
"""

    team_prompt = f"""너는 대학 팀플 진행을 관리해주는 팀플 매니저 AI다.

아래 과제 공지를 바탕으로 팀플 역할분담과 일정표 초안을 짜줘.

[공지 핵심 요약]
{summary}

[마감일]
{due_date}

[해야 할 일]
{tasks_text}

[제출물]
{deliverables_text}

[주의사항]
{warnings_text}

다음 형식으로 답해줘.
1. 팀플 진행 순서
2. 역할 분담안
3. 팀원별 할 일 예시
4. 마감 전까지 일정표 초안
"""

    return {
        "자세한 설명용": detail_prompt,
        "보고서/과제 초안용": report_prompt,
        "발표 준비용": presentation_prompt,
        "팀플 역할분담용": team_prompt,
    }   

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="과제 공지 분석기",
    page_icon="📋",
    layout="centered",
)

# ── 스타일 ──────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── 텍스트 기본 ── */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        word-break: keep-all !important;
        overflow-wrap: break-word !important;
        line-height: 1.85 !important;
    }

    /* ── 텍스트 영역: 안쪽 깊이감 ── */
    .stTextArea textarea {
        font-size: 16px !important;
        line-height: 1.7 !important;
        background: #ffffff !important;
        color: #1a1a2e !important;
        border-radius: 12px !important;
        border: 1px solid rgba(102,126,234,0.25) !important;
        box-shadow: inset 0 2px 6px rgba(0,0,0,0.05),
                    0 1px 4px rgba(102,126,234,0.08) !important;
    }

    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    .stApp {
        background: linear-gradient(135deg, #f0f2f8 0%, #e4e8f0 100%);
    }

    p, li, h1, h2, h3, h4, h5, h6, label {
        color: #1a1a2e !important;
    }

    /* ── 분석 버튼: 살짝 떠 있는 깊이감 ── */
    div.stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: 800 !important;
        padding: 0.85rem 2rem !important;
        border: none !important;
        border-radius: 14px !important;
        width: 100% !important;
        box-shadow: 0 4px 16px rgba(102,126,234,0.38),
                    0 1px 4px rgba(0,0,0,0.10) !important;
        border-bottom: 2px solid rgba(80,40,140,0.25) !important;
        transition: transform 0.12s ease, box-shadow 0.12s ease !important;
    }

    div.stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 22px rgba(102,126,234,0.48),
                    0 2px 6px rgba(0,0,0,0.12) !important;
    }

    div.stButton > button:active {
        transform: translateY(0px) !important;
        box-shadow: 0 2px 8px rgba(102,126,234,0.28) !important;
    }

    /* ── 히어로 박스: 아래 테두리로 두께감 ── */
    .hero-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 40px 48px;
        border-radius: 20px;
        margin-bottom: 28px;
        text-align: center;
        box-shadow: 0 8px 32px rgba(102,126,234,0.38),
                    0 2px 8px rgba(0,0,0,0.10);
        border-bottom: 3px solid rgba(80,40,140,0.30);
    }

    .hero-title {
        font-size: 42px;
        font-weight: 900;
        color: white;
        white-space: nowrap;
        line-height: 1.2;
    }

    .hero-sub {
        font-size: 17px;
        color: rgba(255,255,255,0.92);
        margin-top: 10px;
        line-height: 1.6;
        text-align: center;
    }

    /* ── Expander: 카드처럼 한 층 올라온 느낌 ── */
    div[data-testid="stExpander"] {
        box-shadow: 0 2px 10px rgba(102,126,234,0.12),
                    0 1px 3px rgba(0,0,0,0.06) !important;
        border-radius: 14px !important;
        border: 1px solid rgba(102,126,234,0.16) !important;
        margin-bottom: 10px !important;
        background: white !important;
        overflow: hidden !important;
    }

    div[data-testid="stExpander"] details summary {
        color: #1a1a2e !important;
        background: white !important;
        border-radius: 12px !important;
        padding: 14px 16px !important;
    }

    div[data-testid="stExpander"] details[open] summary {
        color: #1a1a2e !important;
        background: white !important;
        border-bottom: 1px solid rgba(102,126,234,0.12) !important;
        border-radius: 12px 12px 0 0 !important;
    }

    div[data-testid="stExpander"] details summary:hover {
        color: #1a1a2e !important;
        background: #f6f7ff !important;
    }

    div[data-testid="stExpander"] details summary p {
        color: #1a1a2e !important;
        font-weight: 700 !important;
    }

    /* ── Expander 내부 패딩 ── */
    div[data-testid="stExpander"] details > div {
        padding: 12px 16px !important;
    }

    /* ── 셀렉트박스 ── */
    div[data-baseweb="select"] > div {
        background: white !important;
        color: #1a1a2e !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 4px rgba(102,126,234,0.10) !important;
        border: 1px solid rgba(102,126,234,0.20) !important;
    }

    div[data-baseweb="select"] span {
        color: #1a1a2e !important;
    }

    div[data-baseweb="popover"] * {
        color: #1a1a2e !important;
        background: white !important;
    }

    /* ── 구분선 정돈 ── */
    hr {
        border: none !important;
        border-top: 1px solid rgba(102,126,234,0.15) !important;
        margin: 24px 0 !important;
    }

    /* ── 모바일 최적화 ── */
    @media (max-width: 768px) {
        .hero-box {
            padding: 26px 18px;
            border-radius: 18px;
        }
        .hero-title {
            font-size: 26px;
        }
        .hero-sub {
            font-size: 14px;
            line-height: 1.55;
        }
        .stMarkdown p, .stMarkdown li {
            font-size: 15px !important;
            line-height: 1.8 !important;
        }
        div[data-testid="stExpander"] details > div {
            padding: 10px 12px !important;
        }
        div.stButton > button {
            font-size: 16px !important;
            padding: 0.75rem 1.5rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ── 헤더 ────────────────────────────────────────────────────
st.markdown("""
<div class="hero-box">
  <div class="hero-title">📋 과제 공지 분석기</div>
  <div class="hero-sub">
    공지 핵심 정리부터<br>
    AI 프롬프트·일정 문구 생성까지
  </div>
</div>
""", unsafe_allow_html=True)

# ── 입력 방식 선택 ───────────────────────────────────────────
input_type = st.radio(
    "입력 방식 선택",
    ["✏️ 텍스트로 입력", "📷 이미지로 업로드"],
    horizontal=True,
    label_visibility="collapsed"
)

notice_text = ""
uploaded_image = None

if input_type == "✏️ 텍스트로 입력":
    notice_text = st.text_area(
        label="과제 공지문 입력",
        placeholder="여기에 과제 공지문을 붙여넣으세요...",
        height=280,
        label_visibility="collapsed",
    )
else:
    uploaded_image = st.file_uploader(
        "과제 공지 캡처 이미지 업로드",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed"
    )
    if uploaded_image:
        st.image(uploaded_image, caption="업로드된 이미지", use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 분석 버튼 ────────────────────────────────────────────────
if st.button("🔍 분석하기", use_container_width=True):
    if not GEMINI_API_KEY:
        st.error("API 키가 없습니다.")
    elif input_type == "✏️ 텍스트로 입력" and not notice_text.strip():
        st.warning("과제 공지문을 입력해 주세요.")
    elif input_type == "📷 이미지로 업로드" and not uploaded_image:
        st.warning("이미지를 업로드해 주세요.")
    else:
        with st.spinner("✨ 공지를 정리하는 중입니다..."):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)

                if input_type == "📷 이미지로 업로드" and uploaded_image:
                    image_bytes = uploaded_image.read()
                    mime_type = uploaded_image.type

                    contents = [
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=mime_type
                        ),
                        types.Part.from_text(
                            text="위 이미지는 대학 과제 또는 공지 이미지입니다. JSON 형식으로 구조화해주세요."
                        )
                    ]
                    log_input = "이미지 업로드"
                    input_type_for_db = "image"
                else:
                    contents = notice_text
                    log_input = notice_text
                    input_type_for_db = "text"

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=2200,
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                )

                raw_text = response.text
                parsed = safe_json_parse(raw_text)

                if not parsed:
                    st.error("응답 파싱에 실패했습니다. 다시 시도해 주세요.")
                    st.markdown("### 디버깅용 원본 응답")
                    st.code(raw_text, language=None)
                    log_data(log_input, raw_text, input_type=input_type_for_db)
                else:
                    summary = get_value(parsed, "summary")
                    due_date = get_value(parsed, "due_date")
                    tasks = normalize_list(parsed.get("tasks"))
                    deliverables = normalize_list(parsed.get("deliverables"))
                    warnings = normalize_list(parsed.get("warnings"))
                    ai_prompt = get_value(parsed, "ai_prompt")
                    calendar_text = get_value(parsed, "calendar_text")

                    st.session_state.analysis_result = {
                        "summary": summary,
                        "due_date": due_date,
                        "tasks": tasks,
                        "deliverables": deliverables,
                        "warnings": warnings,
                        "ai_prompt": ai_prompt,
                        "calendar_text": calendar_text,
                        "raw_json": parsed,
                    }

                    log_data(
                        log_input,
                        json.dumps(parsed, ensure_ascii=False),
                        input_type=input_type_for_db,
                        parsed_json=parsed
                    )

            except Exception as e:
                st.error(f"오류: {e}")

# ── 결과 표시 (버튼 바깥) ─────────────────────────────────────
if st.session_state.analysis_result:
    result = st.session_state.analysis_result

    summary = result["summary"]
    due_date = result["due_date"]
    tasks = result["tasks"]
    deliverables = result["deliverables"]
    warnings = result["warnings"]
    ai_prompt = result["ai_prompt"]
    calendar_text = result["calendar_text"]
    raw_json = result["raw_json"]

    prompt_pack = build_prompt_pack(summary, due_date, tasks, deliverables, warnings)

    st.markdown("## ✅ 분석 결과")

    with st.expander("📌 핵심 요약", expanded=True):
        st.markdown(summary)

    with st.expander("⏰ 마감일", expanded=False):
        st.markdown(due_date)

    with st.expander("✅ 해야 할 일", expanded=False):
        if tasks:
            for item in tasks:
                st.markdown(f"- {item}")
        else:
            st.markdown("- 공지 확인 필요")

    with st.expander("📦 제출물", expanded=False):
        if deliverables:
            for item in deliverables:
                st.markdown(f"- {item}")
        else:
            st.markdown("- 공지 확인 필요")

    with st.expander("⚠️ 주의사항", expanded=False):
        if warnings:
            for item in warnings:
                st.markdown(f"- {item}")
        else:
            st.markdown("- 공지 확인 필요")

    with st.expander("🤖 AI용 프롬프트", expanded=False):
        prompt_type = st.selectbox(
            "프롬프트 종류 선택",
            list(prompt_pack.keys()),
            key="prompt_type_select"
        )

        selected_prompt = prompt_pack[prompt_type]
        read_only_box(selected_prompt, height=320, key_suffix=prompt_type)

    with st.expander("🗓️ 일정 등록용 문구", expanded=False):
        read_only_box(calendar_text, height=120, key_suffix="calendar")

        parsed_dt = parse_korean_due_date(due_date)
        if parsed_dt:
            desc_parts = [f"[요약] {summary}"]
            if tasks:
                desc_parts.append("[할 일] " + ", ".join(tasks))
            if deliverables:
                desc_parts.append("[제출물] " + ", ".join(deliverables))
            if warnings:
                desc_parts.append("[주의] " + ", ".join(warnings))
            ics_description = "\n".join(desc_parts)

            ics_data = generate_ics(parsed_dt, calendar_text, ics_description)
            filename = f"과제_{parsed_dt.strftime('%m%d')}.ics"
            gcal_url = build_google_calendar_url(parsed_dt, calendar_text, ics_description)

            import base64
            ics_b64 = base64.b64encode(ics_data if isinstance(ics_data, bytes) else ics_data.encode()).decode()
            btn_html = f"""
<style>
  .cal-btn-wrap {{
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }}
  .cal-btn {{
    flex: 1;
    display: inline-block;
    padding: 10px 0;
    text-align: center;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none !important;
    color: #ffffff !important;
    background: linear-gradient(135deg, #667eea, #764ba2);
    cursor: pointer;
    word-break: keep-all;
    overflow-wrap: break-word;
  }}
  .cal-btn:hover {{
    opacity: 0.88;
  }}
</style>
<div class="cal-btn-wrap">
  <a class="cal-btn"
     href="data:text/calendar;base64,{ics_b64}"
     download="{filename}">📥 캘린더 파일 (.ics)</a>
  <a class="cal-btn"
     href="{gcal_url}"
     target="_blank"
     rel="noopener noreferrer">📅 구글 캘린더에 추가</a>
</div>
"""
            components.html(btn_html, height=60)
        else:
            st.caption("⚠️ 마감일을 인식할 수 없어 캘린더 파일을 생성할 수 없습니다.")

    with st.expander("📄 원본 JSON 보기", expanded=False):
        st.code(json.dumps(raw_json, ensure_ascii=False, indent=2), language="json")

# ── 최근 분석 보기 ───────────────────────────────────────────
st.markdown("---")
st.markdown("## 🕘 최근 분석 보기")

recent_logs = get_recent_logs(limit=5)

if not recent_logs:
    st.caption("아직 저장된 분석 기록이 없습니다.")
else:
    for idx, row in enumerate(recent_logs, start=1):
        parsed = row.get("parsed_json") or {}
        created_at = format_kst_datetime(row.get("created_at", ""))
        summary = parsed.get("summary", "요약 없음")
        due_date = parsed.get("due_date", "공지 확인 필요")

        title_preview = summary.strip()
        if len(title_preview) > 60:
            title_preview = title_preview[:60] + "..."

        with st.expander(f"{idx}. {title_preview}"):
            st.markdown(f"**저장 시각:** {created_at}")
            st.markdown(f"**마감일:** {due_date}")

            st.markdown("### 핵심 요약")
            st.markdown(summary)

            with st.expander("원본 JSON 보기"):
                st.code(
                    json.dumps(parsed, ensure_ascii=False, indent=2),
                    language="json"
                )

# ── 푸터 ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#999; font-size:13px;'>"
    "Powered by Gemini 2.5 Flash"
    "</p>",
    unsafe_allow_html=True,
)