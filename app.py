import streamlit as st
from google import genai
from google.genai import types
from supabase import create_client
import os
import html
import uuid
import json
import re

# ── API 키 설정 ──────────────────────────────────────────────
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ── Supabase 연결 ────────────────────────────────────────────
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def log_data(input_text, output_text, input_type="text", parsed_json=None):
    if supabase:
        try:
            payload = {
                "input": input_text,
                "output": output_text,
                "input_type": input_type,
            }

            # usage_logs 테이블에 parsed_json 컬럼이 없을 수도 있으므로
            # 일단 안전하게 optional 형태로만 시도
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

    # 코드블록 제거
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # 앞뒤 설명 제거
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    # 스마트 따옴표 치환
    cleaned = cleaned.replace("“", "\"").replace("”", "\"")
    cleaned = cleaned.replace("‘", "'").replace("’", "'")

    try:
        return json.loads(cleaned)
    except Exception as e:
        print("JSON 파싱 실패 원문:", cleaned)
        print("JSON 파싱 에러:", e)
        return None


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

def copy_block(value, height=220):
    text_value = value if value else "공지 확인 필요"
    element_id = f"copy_area_{uuid.uuid4().hex}"

    escaped_value = html.escape(text_value)

    st.markdown(
        f"""
        <div style="margin-bottom: 8px;">
            <textarea id="{element_id}"
                style="
                    width: 100%;
                    height: {height}px;
                    padding: 14px;
                    font-size: 15px;
                    line-height: 1.6;
                    color: #1a1a2e;
                    background: #ffffff;
                    border: 1px solid #d9dce8;
                    border-radius: 12px;
                    resize: vertical;
                    box-sizing: border-box;
                "
                readonly>{escaped_value}</textarea>
        </div>

        <button onclick="
            navigator.clipboard.writeText(document.getElementById('{element_id}').value);
            this.innerText='복사 완료';
            setTimeout(() => this.innerText='복사하기', 1200);
        "
        style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            margin-bottom: 8px;
            width: 100%;
        ">
            복사하기
        </button>
        """,
        unsafe_allow_html=True
    )

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="과제 공지 분석기",
    page_icon="📋",
    layout="centered",
)

# ── 스타일 ──────────────────────────────────────────────────
st.markdown("""
<style>
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        word-break: keep-all !important;
        overflow-wrap: break-word !important;
        line-height: 1.8 !important;
    }

    .stTextArea textarea {
        font-size: 16px !important;
        background: #ffffff !important;
        color: #1a1a1a !important;
        border-radius: 12px !important;
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

    div.stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: 800 !important;
        padding: 0.8rem 2rem !important;
        border: none !important;
        border-radius: 14px !important;
        width: 100% !important;
    }

    .hero-box {
        background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
        padding: 40px 48px;
        border-radius: 20px;
        margin-bottom: 28px;
        text-align: center;
        box-shadow: 0 10px 40px rgba(102,126,234,0.35);
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
        line-height: 1.55;
        text-align: center;
    }

    .section-card {
        background: rgba(255,255,255,0.88);
        border-radius: 18px;
        padding: 18px 18px;
        border: 1px solid rgba(102,126,234,0.12);
        box-shadow: 0 4px 18px rgba(0,0,0,0.04);
        margin-bottom: 14px;
    }

    div[data-testid="stExpander"] details summary {
        color: #1a1a2e !important;
        background: white !important;
        border-radius: 12px !important;
    }

    div[data-testid="stExpander"] details[open] summary {
        color: #1a1a2e !important;
        background: white !important;
    }

    div[data-testid="stExpander"] details summary:hover {
        color: #1a1a2e !important;
        background: #f8f9ff !important;
    }

    div[data-testid="stExpander"] details summary p {
        color: #1a1a2e !important;
        font-weight: 700 !important;
    }

    .stTextArea textarea {
        font-size: 15px !important;
        line-height: 1.6 !important;
        background: #ffffff !important;
        color: #1a1a2e !important;
        border-radius: 12px !important;
    }

    @media (max-width: 768px) {
        .hero-box {
            padding: 28px 20px;
            border-radius: 18px;
        }
        .hero-title {
            font-size: 28px;
        }
        .hero-sub {
            font-size: 14px;
            line-height: 1.5;
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

# ── 버튼 ────────────────────────────────────────────────────
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

                # 이미지 입력 처리
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

                    st.markdown("<br>", unsafe_allow_html=True)
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
                        copy_block(ai_prompt, height=320)

                    with st.expander("🗓️ 일정 등록용 문구", expanded=False):
                        copy_block(calendar_text, height=120)

                    log_data(
                        log_input,
                        json.dumps(parsed, ensure_ascii=False),
                        input_type=input_type_for_db,
                        parsed_json=parsed
                    )

                    with st.expander("📄 원본 JSON 보기"):
                        st.code(json.dumps(parsed, ensure_ascii=False, indent=2), language="json")

            except Exception as e:
                st.error(f"오류: {e}")

st.markdown("---")
st.markdown("## 🕘 최근 분석 보기")

recent_logs = get_recent_logs(limit=5)

if not recent_logs:
    st.caption("아직 저장된 분석 기록이 없습니다.")
else:
    for idx, row in enumerate(recent_logs, start=1):
        parsed = row.get("parsed_json") or {}
        created_at = row.get("created_at", "")
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