import streamlit as st
from google import genai
from google.genai import types
from supabase import create_client
import os

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
SYSTEM_PROMPT = """당신은 한국 대학생 전용 과제 분석 AI입니다.

[역할]
교수님의 과제 공지문을 분석해서 학생이 바로 실행할 수 있는 형태로 정리해줍니다.

[출력 형식 - 반드시 아래 마크다운 구조로만 답하세요]

### 📌 과제 요약
- **과제명:**
- **마감일:**
- **제출 형식:**
- **분량:**

### ✅ 해야 할 일 (우선순위 순)
1. 
2. 
3. 

### 📅 역산 일정표
- **D-7:**
- **D-3:**
- **D-1:**
- **당일:**

### 📋 보고서 목차 (해당되는 경우)
1. 서론
2. 본론
3. 결론

### 👥 조별과제 역할 분담 (조별과제인 경우만)
- **팀장:**
- **자료조사 담당:**
- **작성 담당:**
- **발표 담당:**

---
### ⏱️ 예상 소요 시간: 약 OO시간

[주의사항]
- 한국어로만 답하세요
- 없는 정보는 추측하지 말고 공지 확인 필요라고 쓰세요
- 분석 결과만 출력하세요. 인사말이나 감탄사는 절대 포함하지 마세요
- 마크다운 문법을 정확히 지켜서 출력하세요"""

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="과제 공지 분석기",
    page_icon="📋",
    layout="centered",
)

st.markdown("""
<style>
    /* 📱 모바일 한국어 텍스트 줄바꿈 및 가독성 최적화 */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        word-break: keep-all !important; /* 단어가 중간에 안 끊기고 통째로 내려가게 함 */
        overflow-wrap: break-word !important;
        line-height: 1.8 !important; /* 줄 간격을 넓혀서 모바일에서 읽기 편하게 */
    }
    textarea {
        font-size: 16px !important;
        background: #ffffff !important;
        color: #1a1a1a !important;
        border-radius: 12px !important;
    }
    /* 입력창 내부 글씨 색상 강제 고정 */
    .stTextArea textarea {
        color: #1a1a1a !important;
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
    textarea {
        font-size: 16px !important;
        background: #ffffff !important;
        border-radius: 12px !important;
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
<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            padding:40px 48px; border-radius:20px; margin-bottom:28px;
            text-align:center; box-shadow:0 10px 40px rgba(102,126,234,0.35);">
  <div style="font-size:42px; font-weight:900; color:white;">
    📋 과제 공지 분석기
  </div>
  <div style="font-size:18px; color:rgba(255,255,255,0.92); margin-top:10px;">
    과제 공지문을 붙여넣으면 핵심 내용을 정리해 드려요
  </div>
</div>
""", unsafe_allow_html=True)

# ── 입력 ────────────────────────────────────────────────────
notice_text = st.text_area(
    label="과제 공지문 입력",
    placeholder="여기에 과제 공지문을 붙여넣으세요...",
    height=300,
    label_visibility="collapsed",
)

st.markdown("<br>", unsafe_allow_html=True)

# ── 버튼 ────────────────────────────────────────────────────
if st.button("🔍 분석하기", use_container_width=True):
    if not GEMINI_API_KEY:
        st.error("API 키가 없습니다.")
    elif not notice_text.strip():
        st.warning("과제 공지문을 입력해 주세요.")
    else:
        with st.spinner("✨ 분석 중입니다..."):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=notice_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=2048,
                        temperature=0.3,
                    ),
                )
                result_text = response.text

                st.markdown("<br>", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown("### ✅ 분석 결과")
                    st.markdown(result_text)

                log_data(notice_text, result_text)

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