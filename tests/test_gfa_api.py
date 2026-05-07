"""GFA API 단위 테스트.

실제 API 호출 없이:
1. HMAC-SHA256 시그니처 생성 검증
2. Mock 데이터 생성 검증
3. fetch_gfa_ads(use_mock=True) 동작 검증
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gfa_api import (
    _generate_signature,
    _build_auth_headers,
    discover_gfa_ad_account,
    fetch_gfa_ads,
    get_last_debug_info,
    GFA_API_BASE,
)
from src.mock_data import GFAAd, generate_gfa_ads


# ────────────────────── 1. 서명 검증 ──────────────────────

def test_signature_format():
    """HMAC-SHA256 서명이 base64 형식으로 반환되는지."""
    sig = _generate_signature(
        secret_key="my-secret-key",
        timestamp_ms=1700000000000,
        method="GET",
        uri_path="/gfa/v1/campaigns",
    )
    assert isinstance(sig, str)
    assert len(sig) > 0
    # base64는 = 패딩으로 끝날 수 있음, 순수 base64 문자만 허용
    import string
    valid_chars = set(string.ascii_letters + string.digits + "+/=")
    assert all(c in valid_chars for c in sig), f"비-base64 문자 포함: {sig}"


def test_signature_deterministic():
    """같은 입력 → 같은 서명 (재현 가능)."""
    args = ("secret", 1700000000000, "POST", "/gfa/v1/stats")
    sig1 = _generate_signature(*args)
    sig2 = _generate_signature(*args)
    assert sig1 == sig2


def test_signature_method_case_insensitive():
    """HTTP 메서드 대소문자 무관 (내부에서 upper)."""
    sig_upper = _generate_signature("secret", 1700000000000, "GET", "/path")
    sig_lower = _generate_signature("secret", 1700000000000, "get", "/path")
    assert sig_upper == sig_lower


def test_signature_changes_with_timestamp():
    """타임스탬프 다르면 서명도 달라야 함."""
    sig1 = _generate_signature("secret", 1700000000000, "GET", "/path")
    sig2 = _generate_signature("secret", 1700000000001, "GET", "/path")
    assert sig1 != sig2


# ────────────────────── 2. 인증 헤더 검증 ──────────────────────

def test_auth_headers_complete():
    """4개 인증 헤더가 모두 포함되는지."""
    headers = _build_auth_headers(
        access_key="ACCESS_KEY_ABC",
        secret_key="SECRET_XYZ",
        customer_id="123456",
        method="GET",
        uri_path="/gfa/v1/campaigns",
    )
    assert "X-Timestamp" in headers
    assert "X-API-KEY" in headers
    assert "X-Customer" in headers
    assert "X-Signature" in headers
    assert headers["X-API-KEY"] == "ACCESS_KEY_ABC"
    assert headers["X-Customer"] == "123456"
    assert headers["X-Timestamp"].isdigit()  # ms 타임스탬프


# ────────────────────── 3. Mock 데이터 검증 ──────────────────────

def test_mock_generates_correct_count():
    """요청한 n_ads 개수만큼 생성되는지."""
    ads = generate_gfa_ads(n_ads=10, seed=42)
    assert len(ads) == 10


def test_mock_returns_gfaad_instances():
    """모든 결과가 GFAAd dataclass 인스턴스인지."""
    ads = generate_gfa_ads(n_ads=5, seed=42)
    for ad in ads:
        assert isinstance(ad, GFAAd)


def test_mock_data_realistic():
    """Mock 데이터가 합리적인 범위인지."""
    ads = generate_gfa_ads(n_ads=20, seed=42)
    for ad in ads:
        assert ad.impressions > 0
        assert ad.clicks >= 0
        assert ad.spend >= 0
        assert ad.revenue >= 0
        assert ad.conversion_count >= 0
        # 클릭 ≤ 노출
        assert ad.clicks <= ad.impressions


def test_gfaad_ctr_calculation():
    """CTR 계산 정확."""
    ad = GFAAd(
        campaign_name="test",
        adgroup_name="test",
        creative_name="test",
        impressions=1000,
        clicks=50,
    )
    assert ad.ctr == 5.0


def test_gfaad_roas_calculation():
    """ROAS 계산 정확."""
    ad = GFAAd(
        campaign_name="test",
        adgroup_name="test",
        creative_name="test",
        spend=10000,
        revenue=30000,
    )
    assert ad.roas == 300.0


def test_gfaad_zero_impressions_ctr():
    """노출 0이어도 ZeroDivisionError 안 나야."""
    ad = GFAAd(
        campaign_name="test",
        adgroup_name="test",
        creative_name="test",
        impressions=0,
        clicks=0,
    )
    assert ad.ctr == 0.0


def test_gfaad_zero_spend_roas():
    """광고비 0이어도 ZeroDivisionError 안 나야."""
    ad = GFAAd(
        campaign_name="test",
        adgroup_name="test",
        creative_name="test",
        spend=0,
        revenue=10000,
    )
    assert ad.roas == 0.0


# ────────────────────── 4. fetch_gfa_ads (Mock 모드) ──────────────────────

def test_fetch_gfa_ads_mock_mode():
    """use_mock=True 시 mock 데이터 반환."""
    end = datetime.now()
    start = end - timedelta(days=2)
    ads = fetch_gfa_ads(start, end, use_mock=True)
    assert isinstance(ads, list)
    assert len(ads) > 0
    assert all(isinstance(a, GFAAd) for a in ads)


def test_base_url_is_searchad_domain():
    """실측 검증: GFA는 검색광고와 동일 도메인 사용."""
    assert GFA_API_BASE == "https://api.searchad.naver.com"


def test_discover_gfa_ad_account_signature():
    """함수 시그니처 검증 (실 호출 X — 시크릿 없으면 None 반환)."""
    # 잘못된 키로 호출 → 인증 실패 → None
    result = discover_gfa_ad_account(
        access_key="invalid",
        secret_key="invalid",
        customer_id="000000",
    )
    assert result is None or isinstance(result, int)


# ────────────────────── 5. 통합 테스트 (실제 API 호출) ──────────────────────

def test_real_api_ad_accounts_discovery():
    """실제 API로 GFA adAccountNo 검출 (시크릿 있을 때만 동작).

    secrets.toml에서 직접 읽음 — 없으면 skip.
    """
    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".streamlit", "secrets.toml",
    )
    if not os.path.exists(secrets_path):
        print("  SKIP (secrets.toml 없음)")
        return

    # 단순 파싱 (toml 라이브러리 없이)
    cfg = {}
    in_section = False
    with open(secrets_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[naver_gfa]"):
                in_section = True
                continue
            if in_section:
                if line.startswith("["):
                    break
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")

    if not all(cfg.get(k) for k in ("ACCESS_KEY", "SECRET_KEY", "CUSTOMER_ID")):
        print("  SKIP (naver_gfa 시크릿 없음)")
        return

    no = discover_gfa_ad_account(
        cfg["ACCESS_KEY"], cfg["SECRET_KEY"], cfg["CUSTOMER_ID"],
    )
    assert no is not None and no > 0, "GFA 계정 자동 검출 실패"
    print(f"  → 발견된 GFA adAccountNo: {no}")


# ────────────────────── 메인 ──────────────────────

if __name__ == "__main__":
    tests = [
        test_signature_format,
        test_signature_deterministic,
        test_signature_method_case_insensitive,
        test_signature_changes_with_timestamp,
        test_auth_headers_complete,
        test_mock_generates_correct_count,
        test_mock_returns_gfaad_instances,
        test_mock_data_realistic,
        test_gfaad_ctr_calculation,
        test_gfaad_roas_calculation,
        test_gfaad_zero_impressions_ctr,
        test_gfaad_zero_spend_roas,
        test_fetch_gfa_ads_mock_mode,
        test_base_url_is_searchad_domain,
        test_discover_gfa_ad_account_signature,
        test_real_api_ad_accounts_discovery,
    ]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{'='*40}")
    print(f"Total: {len(tests)} | Passed: {len(tests) - len(failed)} | Failed: {len(failed)}")
    if failed:
        sys.exit(1)
