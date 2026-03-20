import streamlit as st
from google import genai
from google.genai import types
import os
import pandas as pd
from datetime import datetime

# ── 설정 및 로깅 기능 ───────────────────────────────────────────
LOG_FILE = "usage_log.csv"

def log_data(input_text, output_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = pd.DataFrame({
        'timestamp': [timestamp],
        'input': [input_text],
        'output': [output_text]
    })
    
    if not os.path.exists(LOG_FILE):
        new_data.to_csv(LOG_FILE, index=False, mode='w', encoding='utf-8-sig')
    else:
        new_data.to_csv(LOG_FILE, index=False, mode='a', header=False, encoding='utf-8-sig')

# 💡 1. layout을 "centered"로 변경 (PC에서 중앙에 예쁘게 모임)
st.set_page_config(
    page_title="과제 공지 분석기",
    page_icon="📋",
    layout="centered", 
)

# 💡 2. 억지로 확대하던 zoom 관련 CSS 삭제 및 최적화
st.markdown("""
<style>
    /* 상단 툴바 숨기기 */
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* 전체 배경 */
    .stApp {
        background: linear-gradient(135deg, #f0f2f8 0%, #e4e8f0 100%);
    }

    /* 다크모드 충돌 방지: 글자색 강제 고정 */
    p, li, h1, h2, h3, h4, h5, h6, label, div[data-testid="stSpinner"] * {
        color: #1a1a2e !important;
    }

    /* 텍스트 입력창 스타일 */
    textarea {
        font-size: 16px !important;
        color: #1a1a1a !important;
        background: #ffffff !important;
        line-height: 1.6 !important;
        border-radius: 12px !important;
        border: 1px solid #dde1f0 !important;
    }

    /* 버튼 스타일 */
    div.stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: 800 !important;
        padding: 0.8rem 2rem !important;
        border: none !important;
        border-radius: 14px !important;
        box-shadow: 0 6px 20px rgba(102,126,234,0.4) !important;
        transition: all 0.2s ease !important;
        width: 100% !important;
    }
    div.stButton > button:hover {
        opacity: 0.88 !important;
        transform: translateY(-1px) !important;
    }

    /* 경고 박스 */
    .warn-box {
        background: #fff8e1;
        border: 1px solid #ffe082;
        border-radius: 12px;
        padding: 1rem 1.4rem;
        font-size: 14px;
        margin-bottom: 1.2rem;
    }
    .warn-box * { color: #795548 !important; }
</style>
""", unsafe_allow_html=True)

# (이 아래부터는 기존 GEMINI_API_KEY 선언 등등 똑같이 유지)

# ── API 키 & 시스템 프롬프트 ─────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 💡 마크다운 문법을 잘 지켜달라고 프롬프트를 조금 더 보강했어.
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
- 없는 정보는 추측하지 말고 "공지 확인 필요"라고 쓰세요
- 대학생 눈높이에 맞게 친근하게 써주세요
- 마크다운 문법을 정확히 지켜서 출력하세요"""

# ── 헤더 ───────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            padding:40px 48px; border-radius:20px; margin-bottom:28px;
            text-align:center; box-shadow:0 10px 40px rgba(102,126,234,0.35);">
  <div style="font-size:48px; font-weight:900; color:white; letter-spacing:-1px;">
    📋 과제 공지 분석기
  </div>
  <div style="font-size:20px; color:rgba(255,255,255,0.92); margin-top:10px;">
    과제 공지문을 붙여넣으면 핵심 내용을 정리해 드려요
  </div>
</div>
""", unsafe_allow_html=True)

# ── API 키 경고 ──────────────────────────────────────────────
if not GEMINI_API_KEY:
    st.markdown("""
<div class="warn-box">
⚠️ <strong>GEMINI_API_KEY</strong> 환경변수가 설정되지 않았습니다.<br>
로컬이라면 터미널에서 아래 명령어로 설정하거나 코드 상단에 직접 API 키를 넣으세요.<br>
<code>set GEMINI_API_KEY=여기에_API키_입력</code><br>
Streamlit Cloud 배포 시에는 Advanced Settings에서 넣어주어야 합니다.
</div>
""", unsafe_allow_html=True)

# ── 입력 섹션 ────────────────────────────────────────────────
st.markdown("""
<div style="font-size:20px; font-weight:700; color:#2d2d2d; margin-bottom:8px;">
  📝 과제 공지문 붙여넣기
</div>
""", unsafe_allow_html=True)

notice_text = st.text_area(
    label="과제 공지문 입력",
    placeholder="여기에 과제 공지문을 붙여넣으세요...\n\n예) 교수님이 올린 공지, 카카오톡 메시지, 강의계획서의 과제 안내 등",
    height=300,
    label_visibility="collapsed",
)

st.markdown("<br>", unsafe_allow_html=True)

# ── 분석 버튼 ────────────────────────────────────────────────
analyze_clicked = st.button("🔍 분석하기", use_container_width=True)

# ── 분석 실행 및 결과 출력 ────────────────────────────────────────────────
if analyze_clicked:
    if not GEMINI_API_KEY:
        st.error("API 키가 없습니다. 환경변수 GEMINI_API_KEY를 설정해 주세요.")
    elif not notice_text.strip():
        st.warning("과제 공지문을 입력해 주세요.")
    else:
        with st.spinner("✨ Gemini가 분석 중입니다..."):
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

                # 💡 [CEO 피드백 반영] 마크다운 버그 수정: HTML 억지 삽입 대신 st.markdown 사용
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Streamlit의 container(border=True)를 써서 깔끔하게 박스로 감싸고 마크다운 렌더링
                result_container = st.container(border=True)
                with result_container:
                    st.markdown("### ✅ 분석 결과")
                    st.markdown(result_text) # Gemini가 준 마크다운이 그대로 적용됨

                # 💡 [CEO 피드백 반영] 데이터 수집용 로깅 추가
                log_data(notice_text, result_text)

                st.markdown("<br>", unsafe_allow_html=True)
                # 원본 텍스트 복사용 expander는 유지
                with st.expander("📄 텍스트 원본 보기 / 복사"):
                    st.code(result_text, language=None)

            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

# ── 푸터 ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#999; font-size:14px;'>"
    "Powered by Gemini 2.5 Flash · 환경변수 GEMINI_API_KEY 필요"
    "</p>",
    unsafe_allow_html=True,
)