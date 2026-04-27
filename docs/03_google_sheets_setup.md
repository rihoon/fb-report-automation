# 구글 스프레드시트 Service Account 발급 가이드

> 예상 소요 시간: **15분**
> 무료 (Google Cloud Free Tier)

---

## 1단계: Google Cloud 프로젝트 생성 (3분)

1. https://console.cloud.google.com/ 접속
2. 상단 프로젝트 드롭다운 → **"새 프로젝트"**
3. 프로젝트 이름: `fb-report-automation` (자유)
4. **"만들기"** 클릭

---

## 2단계: Sheets API 활성화 (2분)

1. 좌측 메뉴 → **"API 및 서비스" → "라이브러리"**
2. 검색창에 `Google Sheets API` 입력
3. **"사용 설정(Enable)"** 클릭

---

## 3단계: Service Account 생성 (5분)

1. 좌측 메뉴 → **"API 및 서비스" → "사용자 인증 정보"**
2. 상단 **"+ 사용자 인증 정보 만들기" → "서비스 계정"**
3. 서비스 계정 이름: `sheets-writer`
4. **"만들고 계속하기"** → 역할: **"편집자(Editor)"** → **"완료"**

---

## 4단계: JSON 키 다운로드 (3분)

1. 방금 만든 서비스 계정 클릭
2. 상단 **"키" 탭** → **"키 추가" → "새 키 만들기"**
3. 키 유형: **JSON** 선택 → **"만들기"**
4. JSON 파일 자동 다운로드 됨
5. 파일 안전한 곳에 보관 (절대 Github 올리지 말기)

---

## 5단계: 구글 시트에 권한 부여 (2분)

1. JSON 파일 열어서 `client_email` 복사
   - 예: `sheets-writer@fb-report-automation.iam.gserviceaccount.com`
2. 사용할 구글 시트 열기 (없으면 새로 만들기)
3. 우측 상단 **"공유"** 클릭
4. 위에서 복사한 이메일 붙여넣기
5. 권한: **"편집자"** 선택
6. **"보내기"** 또는 **"공유"** 클릭

---

## 6단계: 시트 ID 확인

구글 시트 URL에서 ID 추출:
```
https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit
                                       ^^^^^^^^^^^^
                                       이 부분
```

---

## ✅ 최종 정보 정리

```
GOOGLE_SHEET_ID=1AbCdEfG... (시트 URL에서 추출)
GOOGLE_SERVICE_ACCOUNT_JSON=<JSON 파일 내용 전체>
```

JSON 파일 내용은 Streamlit Secrets에 통째로 붙여넣으면 됩니다 (개행 포함).

---

## 📋 시트 초기 구조 (Claude가 자동 생성)

처음 실행하면 Claude가 다음 시트들을 자동으로 만듭니다:

- `누적_보고서` — 매번 보고서 결과 append
- `매칭_실패_보정` — 수동 매칭 이력
- `광고_상태_변경` — 유효 X 권고 이력

별도로 시트를 미리 만들 필요는 없어요. 빈 스프레드시트 1개만 준비하시면 됩니다.

---

## 🚨 트러블슈팅

### "권한 거부" 오류
- 5단계에서 Service Account 이메일에 편집자 권한 줬는지 확인
- JSON의 `client_email`과 시트 공유 이메일이 일치하는지 확인

### "API 사용 안 함" 오류
- 2단계 Sheets API 활성화 다시 확인
- Drive API도 필요할 수 있음 (`Google Drive API` 검색해서 활성화)
