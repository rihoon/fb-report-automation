"""페이스북 마케팅 API 연동.

Mock 모드: 시크릿이 없거나 USE_MOCK=True면 Mock 데이터 반환.
실제 모드: facebook-business SDK로 광고 인사이트 + 광고 creative.link_url 조회.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlparse


def extract_nt_detail(url: str) -> str:
    """랜딩 URL에서 nt_detail 파라미터 추출 (호환용)."""
    return extract_nt_params(url).get("nt_detail", "")


def extract_nt_params(url: str) -> dict:
    """랜딩 URL에서 모든 nt_* 파라미터 추출 (매칭 키)."""
    if not url:
        return {}
    try:
        qs = parse_qs(urlparse(url).query)
        return {
            "nt_source": (qs.get("nt_source", [""])[0] or "").strip(),
            "nt_medium": (qs.get("nt_medium", [""])[0] or "").strip(),
            "nt_detail": (qs.get("nt_detail", [""])[0] or "").strip(),
            "nt_keyword": (qs.get("nt_keyword", [""])[0] or "").strip(),
        }
    except Exception:
        return {}


def fetch_facebook_ads(
    start_date: datetime,
    end_date: datetime,
    use_mock: bool = False,
) -> list:
    """페북 광고 인사이트 조회.

    Args:
        start_date: 조회 시작일.
        end_date: 조회 종료일.
        use_mock: True면 Mock 데이터 사용.

    Returns:
        FacebookAd 리스트.
    """
    if use_mock:
        return _fetch_mock(start_date, end_date)

    try:
        import streamlit as st
        cfg = st.secrets.get("facebook", {})
        access_token = cfg.get("ACCESS_TOKEN")
        ad_account_id = cfg.get("AD_ACCOUNT_ID")
        app_id = cfg.get("APP_ID")
        app_secret = cfg.get("APP_SECRET")
    except (ImportError, AttributeError, KeyError):
        return _fetch_mock(start_date, end_date)

    if not all([access_token, ad_account_id]):
        return _fetch_mock(start_date, end_date)

    return _fetch_real(start_date, end_date, access_token, ad_account_id, app_id, app_secret)


def _fetch_real(
    start_date: datetime,
    end_date: datetime,
    access_token: str,
    ad_account_id: str,
    app_id: str | None,
    app_secret: str | None,
) -> list:
    """실제 페북 API 호출. 광고별 link_url도 함께 조회 → nt_detail 추출."""
    from facebook_business.adobjects.ad import Ad
    from facebook_business.adobjects.adaccount import AdAccount
    from facebook_business.adobjects.adsinsights import AdsInsights
    from facebook_business.api import FacebookAdsApi

    from src.mock_data import FacebookAd

    FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
    account = AdAccount(ad_account_id)

    fields = [
        AdsInsights.Field.account_id,
        AdsInsights.Field.campaign_id,
        AdsInsights.Field.campaign_name,
        AdsInsights.Field.adset_id,
        AdsInsights.Field.adset_name,
        AdsInsights.Field.ad_id,
        AdsInsights.Field.ad_name,
        AdsInsights.Field.reach,
        AdsInsights.Field.impressions,
        AdsInsights.Field.clicks,
        AdsInsights.Field.spend,
        AdsInsights.Field.date_start,
        AdsInsights.Field.date_stop,
    ]
    params = {
        "level": "ad",
        "time_range": {
            "since": start_date.strftime("%Y-%m-%d"),
            "until": end_date.strftime("%Y-%m-%d"),
        },
        "limit": 500,
    }

    insights = list(account.get_insights(fields=fields, params=params))

    # ad_id별 link_url + 메타데이터(effective_status + created_time) 조회
    ad_ids = list({row.get("ad_id") for row in insights if row.get("ad_id")})
    link_url_by_ad_id = _fetch_ad_link_urls(ad_ids)
    metadata_by_ad_id = _fetch_ad_metadata(ad_ids)

    results = []
    for row in insights:
        ad_id = row.get("ad_id")
        link_url = link_url_by_ad_id.get(ad_id, "")
        nt_params = extract_nt_params(link_url)
        owner = infer_owner(
            nt_medium=nt_params.get("nt_medium", ""),
            campaign_name=row.get("campaign_name", ""),
        )

        meta = metadata_by_ad_id.get(ad_id, {"status": "ACTIVE", "created_time": None})
        # effective_status: ACTIVE만 active, 나머지(PAUSED/DELETED/ARCHIVED 등) inactive
        raw_status = meta.get("status", "ACTIVE")
        delivery_status = "active" if str(raw_status).upper() == "ACTIVE" else "inactive"

        results.append(
            FacebookAd(
                owner=owner,
                campaign_name=row.get("campaign_name", ""),
                adset_name=row.get("adset_name", ""),
                ad_name=row.get("ad_name", ""),
                delivery_status=delivery_status,
                reach=int(row.get("reach", 0)),
                clicks=int(row.get("clicks", 0)),
                impressions=int(row.get("impressions", 0)),
                spend=float(row.get("spend", 0)),
                date_start=datetime.strptime(row.get("date_start"), "%Y-%m-%d"),
                date_stop=datetime.strptime(row.get("date_stop"), "%Y-%m-%d"),
                link_url=link_url,
                nt_source=nt_params.get("nt_source", ""),
                nt_medium=nt_params.get("nt_medium", ""),
                nt_detail=nt_params.get("nt_detail", ""),
                nt_keyword=nt_params.get("nt_keyword", ""),
                created_time=meta.get("created_time"),
            )
        )
    return results


_link_url_debug: dict = {"errors": [], "samples": []}


def get_link_url_debug() -> dict:
    return _link_url_debug


def _fetch_ad_metadata(ad_ids: list[str]) -> dict[str, dict]:
    """ad_id별 effective_status + created_time 조회.

    ACTIVE → 켜진 광고
    PAUSED / DELETED / ARCHIVED / DISAPPROVED 등 → 꺼진 광고
    created_time → 광고 등록일 (ISO 8601 → datetime)

    실패하면 ACTIVE / None으로 fallback.
    """
    from facebook_business.adobjects.ad import Ad
    result: dict[str, dict] = {}
    for ad_id in ad_ids:
        try:
            ad = Ad(ad_id).api_get(fields=[Ad.Field.effective_status, Ad.Field.created_time])
            ct_str = ad.get("created_time")
            ct: datetime | None = None
            if ct_str:
                # 페북 포맷: "2024-10-15T05:23:01+0900" — 앞 19자만 파싱
                try:
                    ct = datetime.strptime(str(ct_str)[:19], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    ct = None
            result[ad_id] = {
                "status": str(ad.get("effective_status") or "ACTIVE"),
                "created_time": ct,
            }
        except Exception:
            result[ad_id] = {"status": "ACTIVE", "created_time": None}
    return result


def _fetch_ad_statuses(ad_ids: list[str]) -> dict[str, str]:
    """호환용 — 메타데이터에서 status만 추출."""
    metadata = _fetch_ad_metadata(ad_ids)
    return {k: v["status"] for k, v in metadata.items()}


def _fetch_ad_link_urls(ad_ids: list[str]) -> dict[str, str]:
    """광고 ID별 랜딩 URL 조회.

    페북 광고는 단일/캐러셀 등 형태에 따라 URL 위치가 달라서 여러 경로 시도:
    - creative.url_tags (URL 파라미터만 가지는 경우)
    - creative.template_url
    - creative.object_story_spec.link_data.link
    - creative.effective_object_story_id (페이지 게시물 ID로 조회)
    """
    from facebook_business.adobjects.ad import Ad
    from facebook_business.adobjects.adcreative import AdCreative

    _link_url_debug["errors"] = []
    _link_url_debug["samples"] = []
    result: dict[str, str] = {}

    for idx, ad_id in enumerate(ad_ids):
        try:
            ad = Ad(ad_id).api_get(fields=["creative{id,object_story_spec,effective_object_story_id,template_url,url_tags,object_url,asset_feed_spec}"])
            creative = ad.get("creative", {}) or {}

            url = (
                creative.get("template_url")
                or creative.get("object_url")
                or _extract_url_from_story_spec(creative.get("object_story_spec", {}))
                or _extract_url_from_asset_feed(creative.get("asset_feed_spec", {}))
            )

            # url_tags 같은 형태 (?nt_source=...&nt_detail=...) 만 있을 때
            url_tags = creative.get("url_tags")
            if not url and url_tags:
                url = "https://example.com/?" + url_tags  # 파라미터만 추출하기 위한 더미 base

            if url:
                result[ad_id] = url

            # 첫 5건 샘플 저장 (디버깅)
            if idx < 5:
                creative_dict = _to_dict(creative)
                story_spec_dict = _to_dict(creative_dict.get("object_story_spec"))
                _link_url_debug["samples"].append({
                    "ad_id": ad_id,
                    "url": url,
                    "url_tags": url_tags,
                    "creative_keys": list(creative_dict.keys()),
                    "story_spec_keys": list(story_spec_dict.keys()) if story_spec_dict else [],
                    "story_spec_preview": story_spec_dict,
                })
        except Exception as e:
            _link_url_debug["errors"].append(f"{ad_id}: {type(e).__name__}: {e}")
            continue
    return result


def _to_dict(obj):
    """FB SDK 객체 또는 dict를 plain dict로 변환."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    # facebook_business AbstractCrudObject는 _data 또는 export_all_data 사용
    if hasattr(obj, "export_all_data"):
        try:
            return obj.export_all_data()
        except Exception:
            pass
    if hasattr(obj, "_data"):
        return getattr(obj, "_data") or {}
    # dict-like (.get 가능)면 .keys()로 변환 시도
    try:
        return dict(obj)
    except Exception:
        return {}


def _extract_url_from_story_spec(spec) -> str:
    """object_story_spec의 다양한 형태에서 URL 추출."""
    spec = _to_dict(spec)
    if not spec:
        return ""
    link_data = _to_dict(spec.get("link_data"))
    if link_data.get("link"):
        return link_data["link"]
    # 캐러셀
    child_attachments = link_data.get("child_attachments", []) or []
    for child in child_attachments:
        child_d = _to_dict(child)
        if child_d.get("link"):
            return child_d["link"]
    video_data = _to_dict(spec.get("video_data"))
    cta = _to_dict(video_data.get("call_to_action"))
    cta_value = _to_dict(cta.get("value"))
    if cta_value.get("link"):
        return cta_value["link"]
    return ""


def _extract_url_from_asset_feed(spec) -> str:
    """asset_feed_spec (Advantage+ 광고)에서 URL 추출."""
    spec = _to_dict(spec)
    if not spec:
        return ""
    link_urls = spec.get("link_urls", []) or []
    for item in link_urls:
        item_d = _to_dict(item)
        if item_d.get("website_url"):
            return item_d["website_url"]
    return ""




def _fetch_mock(start_date: datetime, end_date: datetime) -> list:
    """Mock 데이터로 fallback."""
    from src.mock_data import generate_facebook_ads
    days = max(1, (end_date - start_date).days)
    return generate_facebook_ads(n_ads=60, period_days=days, ref_date=end_date, seed=7)


OWNER_BY_NT_MEDIUM = {
    "traffic_b": "김다빈",
    "traffic_e": "고은지",
    "traffic_s": "전수진",
    # 추가 매핑은 여기에 (예: 김민지 traffic_?)
}


def infer_owner(nt_medium: str = "", campaign_name: str = "") -> str:
    """담당자 식별. 우선순위:
    1) URL의 nt_medium suffix (사용자가 직접 설정한 매핑)
    2) (예비) 캠페인명 패턴
    3) 미지정
    """
    if nt_medium and nt_medium in OWNER_BY_NT_MEDIUM:
        return OWNER_BY_NT_MEDIUM[nt_medium]
    return "미지정"


def _infer_owner_from_campaign(campaign_name: str) -> str:
    """(레거시) 캠페인명에서 담당자 추정 — 이제 사용 안 함, 호환용으로 둠."""
    return "미지정"
