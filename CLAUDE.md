# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개발 명령어

```bash
# 로컬 실행
streamlit run app.py

# 의존성 설치
pip install -r requirements.txt
```

테스트 프레임워크 없음. 변경 후 로컬 실행으로 직접 확인.

## 시크릿 설정

로컬 개발 시 `.streamlit/secrets.toml`에 설정:
```toml
GEMINI_API_KEY = "..."
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
```
배포(Streamlit Cloud)에서는 앱 설정 → Secrets에 동일 키 등록.

## 아키텍처

`app.py` 단일 파일 구조. 위에서 아래로 순서대로 실행되는 Streamlit 앱.

**데이터 흐름:**
1. 사용자 입력 (텍스트 or 이미지) → Gemini 2.5 Flash API 호출 (`response_mime_type="application/json"`, `temperature=0.1`)
2. `safe_json_parse()` → JSON 파싱 (코드블록 제거, 괄호 추출, 유니코드 따옴표 정규화)
3. `st.session_state.analysis_result`에 저장 → 결과 렌더링 (버튼 바깥에서 상태 기반으로 표시)
4. `log_data()` → Supabase `usage_logs` 테이블에 저장

**주요 설계 결정:**
- 분석 결과를 `session_state`에 보관해 페이지 재렌더링 후에도 결과 유지. `st.rerun()` 없이 selectbox 변경이 가능한 이유.
- `read_only_box()`: Streamlit 네이티브 컴포넌트로는 읽기 전용 + 복사 버튼을 동시에 구현할 수 없어 `components.html()`로 직접 HTML/JS 렌더링.
- `build_prompt_pack()` 함수가 파일에 두 번 정의되어 있음 (81번째 줄, 341번째 줄). 실제 사용되는 것은 두 번째(341번째). 첫 번째는 미사용 잔여 코드.

**Supabase 테이블 스키마 (`usage_logs`):**
- `id`, `created_at`, `input`, `output`, `input_type` (text|image), `parsed_json` (JSONB)

## 개발 단계 현황

- 1단계: 최근 분석 보기 ✅
- 2단계: AI 프롬프트 종류 선택 (자세한 설명용 / 보고서·과제 초안용 / 발표 준비용 / 팀플 역할분담용) ✅
- **3단계: ICS 일정 다운로드 (다음 작업)** — `calendar_text` / `due_date`에서 날짜 파싱 후 `.ics` 파일 생성 + `st.download_button` 제공
- 4단계: Google Calendar 링크 연동

## 개발 규칙

- 기능 개발과 UI 수정은 작업을 분리할 것 (같은 PR에 혼용 금지)
- 이미 동작하는 구조를 갈아엎지 말고 기존 코드를 확장하는 방식으로 추가
- `build_prompt_pack()` 중복 정의 문제: 기능 추가 시 두 번째(341번째) 함수만 수정, 첫 번째는 추후 삭제 대상
- 모바일 가독성 우선 — `word-break: keep-all`, `overflow-wrap: break-word` 유지 필수
- 색상 팔레트: 보라/블루 계열 (`#667eea` ~ `#764ba2`) 고정. 다른 톤 제안 금지
