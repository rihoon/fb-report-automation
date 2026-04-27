# 네이버 커머스 API 자격증명 정리

> 이미 발급받으셨다고 하셨으니 **확인 + 정리**만 하면 됩니다.

---

## 필요한 정보 4가지

```
NAVER_CLIENT_ID=xxx
NAVER_CLIENT_SECRET=xxx
NAVER_ACCOUNT_ID=xxx (스마트스토어 판매자 ID)
NAVER_API_VERSION=v1 (보통 v1)
```

---

## 확인 방법

### 1. 네이버 커머스 솔루션 마켓 접속
https://apicenter.commerce.naver.com/

### 2. 마이 → 애플리케이션 관리
- 등록한 앱이 있으면 → 클릭
- 없으면 **"새 애플리케이션 등록"**

### 3. 자격증명 확인
- **Client ID** / **Client Secret** 복사
- 권한 범위 확인:
  - ☑ 상품 조회
  - ☑ **주문 조회** (필수!)
  - ☑ 주문 상태 변경 (선택)
  - ☑ 정산 조회 (선택)

### 4. 판매자 ID 확인
- 스마트스토어 센터 → 마이페이지 → 판매자 정보
- 또는 API 호출로 확인 가능

---

## 🔍 사용할 API 엔드포인트 (참고용)

| 용도 | 엔드포인트 |
|------|------------|
| 인증 토큰 발급 | `POST /external/v1/oauth2/token` |
| **주문 조회** | `GET /external/v1/pay-order/seller/product-orders` |
| 주문 상세 | `GET /external/v1/pay-order/seller/product-orders/{id}` |
| 클레임(환불/교환) 조회 | `GET /external/v1/pay-order/seller/claims` |

> 환불·교환 정보도 가져와야 하니 **클레임 API**도 권한 확인 필요

---

## ✅ Claude에게 전달

위 4가지 + 권한 범위가 맞는지 확인 후 알려주세요.
키는 나중에 Streamlit Secrets에 직접 입력하시면 됩니다.
