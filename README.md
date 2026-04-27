# 페북성과보고서 자동화

페이스북 광고와 네이버 스마트스토어 주문을 UTM 파라미터로 매칭해, 광고별 실제 매출과 ROAS를 자동 계산해주는 Streamlit 웹 보고서.

---

## 📦 빠른 시작 (Mock 모드, API 키 없이)

```bash
# 1. 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 2. 비번만 설정
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# secrets.toml 열어서 APP_PASSWORD = "테스트비번" 만 입력

# 3. 실행
streamlit run app.py
```

브라우저가 자동으로 열리면 비번 입력 → 사이드바의 **🧪 Mock 데이터 사용** 토글 ON → **🚀 보고서 생성**.

---

## 🔑 실제 API 연동 (배포 전)

`docs/` 폴더의 가이드 따라 키 발급:

1. [페북 마케팅 API 발급](docs/01_facebook_api_setup.md) (30~60분)
2. [네이버 커머스 API 확인](docs/02_naver_commerce_api_setup.md) (5분, 이미 발급됨)
3. [구글 Service Account 발급](docs/03_google_sheets_setup.md) (15분)

발급한 키를 `.streamlit/secrets.toml`에 입력 후, 사이드바 **Mock 데이터 사용** 토글을 OFF로.

---

## ☁️ Streamlit Cloud 배포

1. GitHub repo에 코드 push (단, `secrets.toml`은 커밋되지 않음)
2. https://share.streamlit.io/ 접속 → **New app**
3. repo / branch / `app.py` 선택
4. **Advanced settings** → **Secrets** 탭에 `secrets.toml` 내용 통째로 붙여넣기
5. **Deploy** 클릭 → 발급된 URL을 마케팅팀에 공유

---

## 📁 프로젝트 구조

```
페북성과보고서 자동화/
├── app.py                       ← Streamlit 메인
├── requirements.txt
├── .gitignore
├── .streamlit/
│   ├── config.toml              ← 테마
│   └── secrets.toml.example     ← 시크릿 템플릿
├── src/
│   ├── auth.py                  ← 비번 보호
│   ├── mock_data.py             ← 개발용 가짜 데이터
│   ├── matching.py              ← UTM 매칭
│   ├── aggregation.py           ← KPI/성과 집계
│   ├── comparison.py            ← 작년/지난주 비교
│   ├── validity.py              ← 유효 O/X 판정
│   ├── formatting.py            ← 조건부 서식 (화면)
│   ├── export.py                ← 엑셀 다운로드
│   ├── facebook_api.py          ← 페북 API
│   ├── naver_api.py             ← 네이버 API
│   └── google_sheets.py         ← 구글 시트 누적
├── docs/                        ← API 셋업 가이드
└── PRD.md                       ← 제품 요구 명세
```

---

## 🎯 핵심 기능

- **자동 데이터 수집**: 페북 마케팅 API + 네이버 커머스 API
- **UTM 매칭**: `utm_content` ↔ 페북 광고 이름 1:1
- **KPI 4종**: 광고비 / 매출 / ROAS / 전환수 (작년 동기 대비 ↑↓)
- **집계 사이클 자동**: 월=3일 / 수=2일 / 금=2일
- **유효 O/X 자동 판정**:
  - 5일간 매출 0 → X (`5일간 매출없음`)
  - 10일간 ROAS<100% → X (`10일간 ROAS 100% 미만`)
- **조건부 서식**: ≥100% 분홍 / <100% 푸른
- **수동 매칭 보정**: 매칭 실패 주문을 화면에서 직접 매칭
- **구글 시트 누적**: 매번 결과 자동 append (작년 비교용 누적)
- **엑셀 다운로드**: 조건부 서식 그대로 보존

---

## 🚦 운영 사이클 (월·수·금)

| 보고일 | 집계 기간 | KPI 계산 |
|--------|-----------|----------|
| 월요일 | 금·토·일 (3일) | 자동 |
| 수요일 | 월·화 (2일) | 자동 |
| 금요일 | 수·목 (2일) | 자동 |
| **7일 ROAS** | 보고일 기준 최근 7일 | 자동 |

---

## 🛠️ 트러블슈팅

### "비밀번호가 일치하지 않습니다"
- `.streamlit/secrets.toml`에 `APP_PASSWORD`가 설정되어 있는지 확인

### "데이터가 비어있어요"
- 사이드바 **🧪 Mock 데이터 사용**을 ON으로 → 가짜 데이터로 검증
- ON인데도 비면 콘솔 에러 확인 (`streamlit run app.py` 터미널)

### "페북 토큰 만료"
- 60일마다 토큰 갱신 필요. [docs/01_facebook_api_setup.md](docs/01_facebook_api_setup.md) 참고

### "구글 시트 권한 거부"
- Service Account 이메일에 시트 편집자 권한 줬는지 확인
- [docs/03_google_sheets_setup.md](docs/03_google_sheets_setup.md) 5단계 참고

---

## 📌 라이선스 & 작성

- 작성: 리훈
- 사용 대상: 마케팅팀 (3~5명, 비번 공유)
- 버전: v1.0 (Gold)
