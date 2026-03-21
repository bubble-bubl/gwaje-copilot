import streamlit as st
from google import genai
from google.genai import types
from supabase import create_client
import os
import base64
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
  "summary": "공지 핵심을 2~3문장으로 요약",
  "assignment_name": "과제명 또는 발표명",
  "due_date": "마감일/제출일/발표일. 없으면 공지 확인 필요",
  "submission_format": "제출 방식 또는 형식",
  "tasks": [
    "학생이 해야 할 행동 1",
    "학생이 해야 할 행동 2"
  ],
  "deliverables": [
    "제출해야 하는 결과물 1",
    "제출해야 하는 결과물 2"
  ],
  "materials": [
    "필요한 준비물 또는 참고 요소 1"
  ],
  "warnings": [
    "주의사항 1",
    "주의사항 2"
  ],
  "gpt_prompt": "이 공지를 바탕으로 ChatGPT에 바로 넣을 자세한 프롬프트",
  "gemini_prompt": "이 공지를 바탕으로 Gemini에 바로 넣을 짧고 실용적인 프롬프트",
  "calendar_text": "캘린더에 넣기 쉬운 한 줄 일정 문구"
}

[작성 규칙]
- summary는 짧고 명확하게
- tasks는 실제 행동 단위로 작성
- deliverables는 제출물 중심
- warnings는 감점/형식/마감 관련 리스크 위주
- gpt_prompt는 자세하고 구조적인 요청형
- gemini_prompt는 짧고 빠르게 쓸 수 있게 작성
- calendar_text는 다음 느낌으로 작성:
  "3월 28일 23:59 / 운영체제 과제 2 제출 / PDF 업로드"
"""

# ── 유틸 함수 ────────────────────────────────────────────────
def safe_json_parse(text: str):
    """
    Gemini가 드물게 코드블록이나 앞뒤 설명을 섞을 수 있으므로
    최대한 JSON 부분만 안전하게 추출한다.
    """
    if not text:
        return None

    cleaned = text.strip()

    # ```json ... ``` 제거
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # 첫 { 부터 마지막 } 까지 잘라보기
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    try:
        return json.loads(cleaned)
    except Exception:
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


def render_list_section(title, items, empty_text="공지 확인 필요"):
    st.markdown(f"### {title}")
    if items:
        for item in items:
            st.markdown(f"- {item}")
    else:
        st.markdown(f"- {empty_text}")


def copy_block(label, value):
    st.markdown(f"### {label}")
    st.code(value if value else "공지 확인 필요", language=None)


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
        font-size: 18px;
        color: rgba(255,255,255,0.92);
        margin-top: 10px;
    }

    .section-card {
        background: rgba(255,255,255,0.88);
        border-radius: 18px;
        padding: 18px 18px;
        border: 1px solid rgba(102,126,234,0.12);
        box-shadow: 0 4px 18px rgba(0,0,0,0.04);
        margin-bottom: 14px;
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
            font-size: 15px;
        }
    }
</style>
""", unsafe_allow_html=True)

# ── 헤더 ────────────────────────────────────────────────────
st.markdown("""
<div class="hero-box">
  <div class="hero-title">📋 과제 공지 분석기</div>
  <div class="hero-sub">공지 내용을 행동 단위로 정리하고 AI 프롬프트와 일정 문구까지 만들어줍니다</div>
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
                    with st.expander("디버깅용 원본 응답 보기"):
                        st.code(raw_text, language=None)
                    log_data(log_input, raw_text, input_type=input_type_for_db)
                else:
                    summary = get_value(parsed, "summary")
                    assignment_name = get_value(parsed, "assignment_name")
                    due_date = get_value(parsed, "due_date")
                    submission_format = get_value(parsed, "submission_format")

                    tasks = normalize_list(parsed.get("tasks"))
                    deliverables = normalize_list(parsed.get("deliverables"))
                    materials = normalize_list(parsed.get("materials"))
                    warnings = normalize_list(parsed.get("warnings"))

                    gpt_prompt = get_value(parsed, "gpt_prompt")
                    gemini_prompt = get_value(parsed, "gemini_prompt")
                    calendar_text = get_value(parsed, "calendar_text")

                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("## ✅ 분석 결과")

                    with st.container(border=True):
                        st.markdown("### 📌 핵심 요약")
                        st.markdown(summary)

                    col1, col2 = st.columns(2)
                    with col1:
                        with st.container(border=True):
                            st.markdown("### 🏷️ 과제명")
                            st.markdown(assignment_name)
                    with col2:
                        with st.container(border=True):
                            st.markdown("### ⏰ 마감일")
                            st.markdown(due_date)

                    with st.container(border=True):
                        st.markdown("### 📤 제출 형식")
                        st.markdown(submission_format)

                    with st.container(border=True):
                        render_list_section("✅ 해야 할 일", tasks)

                    with st.container(border=True):
                        render_list_section("📦 제출물", deliverables)

                    with st.container(border=True):
                        render_list_section("🧰 준비물 / 참고 요소", materials)

                    with st.container(border=True):
                        render_list_section("⚠️ 주의사항", warnings)

                    st.markdown("## 🤖 AI용 프롬프트")

                    tab1, tab2, tab3 = st.tabs(["ChatGPT용", "Gemini용", "일정 등록용"])

                    with tab1:
                        copy_block("ChatGPT에 바로 넣기", gpt_prompt)

                    with tab2:
                        copy_block("Gemini에 바로 넣기", gemini_prompt)

                    with tab3:
                        copy_block("캘린더/메모용 문구", calendar_text)

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

# ── 푸터 ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#999; font-size:13px;'>"
    "Powered by Gemini 2.5 Flash"
    "</p>",
    unsafe_allow_html=True,
)