# 페이스북 마케팅 API 발급 가이드

> 예상 소요 시간: **30분 ~ 1시간**
> 권한: 페북 비즈니스 매니저 + 광고 계정 관리자 권한 필요

---

## 1단계: Meta for Developers 가입 (5분)

1. https://developers.facebook.com/ 접속
2. 우측 상단 **"시작하기(Get Started)"** 클릭
3. 본인 페이스북 계정으로 로그인
4. 개발자 등록 완료 (전화번호 인증)

---

## 2단계: 앱 생성 (10분)

1. https://developers.facebook.com/apps/ 접속
2. **"앱 만들기(Create App)"** 클릭
3. 앱 유형 선택: **"비즈니스(Business)"**
4. 앱 이름: `페북성과보고서` (자유)
5. 비즈니스 계정 연결 (드롭다운에서 본인 비즈니스 선택)
6. **"앱 만들기"** 클릭

---

## 3단계: Marketing API 추가 (5분)

1. 앱 대시보드에서 **"제품 추가(Add Product)"** 섹션
2. **"마케팅 API"** 찾아서 **"설정(Set up)"** 클릭
3. 좌측 메뉴에서 **마케팅 API → 도구(Tools)** 클릭

---

## 4단계: System User Access Token 발급 (15분)

> 일반 토큰은 1~2시간 만료, **시스템 사용자 토큰은 만료 없음** (혹은 60일)

1. https://business.facebook.com/settings/system-users 접속
2. **"시스템 사용자 추가"** 클릭
3. 이름: `report-automation`
4. 역할: **관리자(Admin)**
5. 생성 후 → 해당 시스템 사용자 클릭
6. **"자산 추가(Add Assets)"** → **광고 계정** 선택 → 권한: **"광고 계정 관리"**
7. **"새 토큰 생성(Generate New Token)"** 클릭
8. 앱 선택 (3단계에서 만든 앱)
9. 권한 체크:
   - ☑ `ads_read`
   - ☑ `ads_management`
   - ☑ `business_management`
10. **"토큰 생성"** → 토큰 복사 (한 번만 표시됨!)

---

## 5단계: 광고 계정 ID 확인 (2분)

1. https://business.facebook.com/settings/ad-accounts 접속
2. 사용할 광고 계정 클릭
3. URL 또는 상세 정보에서 ID 복사
   - 형식: `act_1234567890` (앞에 `act_` 붙음)

---

## ✅ 발급 완료 후 Claude에게 전달할 정보

```
FACEBOOK_ACCESS_TOKEN=EAAxxx... (4단계에서 복사한 토큰)
FACEBOOK_AD_ACCOUNT_ID=act_1234567890 (5단계 광고 계정 ID)
FACEBOOK_APP_ID=123456789 (앱 대시보드 좌상단)
FACEBOOK_APP_SECRET=abc123... (앱 설정 → 기본 설정에서 확인)
```

⚠️ **절대 GitHub에 올리거나 채팅에 그대로 붙여넣지 마세요!**
→ Streamlit Secrets에 직접 입력하거나, `.env` 파일에만 저장

---

## 🚨 트러블슈팅

### "권한이 없습니다" 오류
- 비즈니스 매니저 → 사람 → 본인 → **광고 계정 관리자** 권한 확인
- 시스템 사용자에 광고 계정 자산 추가했는지 확인

### "유효하지 않은 토큰" 오류
- 토큰을 한 번에 복사했는지 확인 (잘림 자주 발생)
- 토큰 디버거: https://developers.facebook.com/tools/debug/accesstoken/

### App Review가 필요한 경우
- 본인 비즈니스 광고 계정만 조회한다면 **Review 불필요**
- 다른 광고주 계정 조회하려면 Review 필요
