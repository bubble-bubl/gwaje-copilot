import streamlit as st
from google import genai
from google.genai import types
from supabase import create_client
import os
import base64

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

def log_data(input_text, output_text):
    if supabase:
        try:
            supabase.table("usage_logs").insert({
                "input": input_text,
                "output": output_text
            }).execute()
        except Exception as e:
            print(f"DB 오류: {e}")

# ── 시스템 프롬프트 ──────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국 대학생 전용 과제 해결 AI입니다.

[역할]
교수님의 과제 공지문을 분석하고, 학생이 과제를 실제로 완성할 수 있도록 도와줍니다.
텍스트 또는 이미지로 입력된 과제 공지를 분석하세요.

[출력 형식 - 반드시 아래 마크다운 구조로만 답하세요]

### 📌 과제 요약
- **과제명:**
- **마감일:**
- **제출 형식:**
- **분량:**

### 🔍 교수 요구사항 정리
교수님이 이 과제에서 진짜 원하는 것을 핵심만 뽑아서 정리하세요.
- 
- 
- 

### 📝 목차 및 초안

**목차**
1. 서론
2. 
3. 결론

**초안**
(각 목차에 맞게 실제 내용을 작성하세요. 대학생이 직접 쓴 것처럼 자연스럽게 작성하되,
너무 완벽하거나 AI스럽지 않게, 구어체와 문어체를 적절히 섞어서 작성하세요.)

### 🎯 답안 전략 및 공부법

**답안 전략**
- 이 과제에서 높은 점수를 받으려면:
- 

**공부법 및 참고자료**
- 이 과제를 하기 위해 알아야 할 개념:
- 참고하면 좋은 자료:
- 

[주의사항]
- 한국어로만 답하세요
- 없는 정보는 추측하지 말고 공지 확인 필요라고 쓰세요
- 분석 결과만 출력하세요. 인사말이나 감탄사는 절대 포함하지 마세요
- 초안은 대학생이 직접 쓴 것처럼 자연스럽게 작성하세요
- 마크다운 문법을 정확히 지켜서 출력하세요"""

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="과제 공지 분석기",
    page_icon="📋",
    layout="centered",
)

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
</style>
""", unsafe_allow_html=True)

# ── 헤더 ────────────────────────────────────────────────────
st.markdown("""
<style>
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

@media (max-width: 768px) {
    .hero-box {
        padding: 28px 20px;
    }
    .hero-title {
        font-size: 28px;
    }
    .hero-sub {
        font-size: 15px;
    }
}
</style>

<div class="hero-box">
  <div class="hero-title">📋 과제 공지 분석기</div>
  <div class="hero-sub">과제 공지문을 붙여넣거나 캡처 이미지를 올려주세요</div>
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
        height=300,
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
        with st.spinner("✨ 분석 중입니다..."):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)

                # 이미지 입력 처리
                if input_type == "📷 이미지로 업로드" and uploaded_image:
                    image_bytes = uploaded_image.read()
                    image_b64 = base64.b64encode(image_bytes).decode()
                    mime_type = uploaded_image.type

                    contents = [
                        types.Part.from_bytes(
                            data=base64.b64decode(image_b64),
                            mime_type=mime_type
                        ),
                        types.Part.from_text(
                            text="위 이미지는 과제 공지입니다. 분석해주세요."
                        )
                    ]
                    log_input = "이미지 업로드"
                else:
                    contents = notice_text
                    log_input = notice_text

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=4096,
                        temperature=0.3,
                    ),
                )
                result_text = response.text

                st.markdown("<br>", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown("### ✅ 분석 결과")
                    st.markdown(result_text)

                log_data(log_input, result_text)

                with st.expander("📄 텍스트 원본 보기 / 복사"):
                    st.code(result_text, language=None)

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