"""개발/테스트용 Mock 데이터 생성기.

API 키 없이도 전체 파이프라인을 검증할 수 있도록
페북 광고 데이터와 네이버 주문 데이터를 합성합니다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


OWNERS = ["김다빈", "고은지", "전수진"]

CAMPAIGN_THEMES = [
    "2025이야기다이어리",
    "2025오늘쓰임",
    "2025회사생활",
    "2025다다일력",
    "반가워겨울방학",
    "2025오늘기억",
    "2025레이어블",
    "2025하고싶은말",
    "알지질문스티커",
]

CREATIVE_HOOKS = [
    "한정판", "갓생", "직장인", "방학준비", "선물로",
    "단한번의", "한개시킨줄", "도태", "2025계획", "착각",
    "유형", "인기컬러", "새로운시작", "직장인외", "직장인픽",
]

DELIVERY_STATUS = ["active", "active", "active", "active", "inactive", "not_delivering"]


@dataclass
class FacebookAd:
    """페북 광고 1건 (광고소재 단위)."""
    owner: str
    campaign_name: str
    adset_name: str
    ad_name: str
    delivery_status: str
    reach: int
    clicks: int
    impressions: int
    spend: float  # KRW
    date_start: datetime
    date_stop: datetime
    link_url: str = ""        # 광고가 가리키는 랜딩 URL
    nt_source: str = ""       # 매칭 키
    nt_medium: str = ""
    nt_detail: str = ""
    nt_keyword: str = ""
    created_time: datetime | None = None  # 광고 등록일 (페북 API created_time)

    @property
    def nt_key(self) -> tuple:
        """4개 nt_* 파라미터로 만든 매칭 키."""
        return (self.nt_source, self.nt_medium, self.nt_detail, self.nt_keyword)

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions else 0.0

    @property
    def cpc(self) -> float:
        return (self.spend / self.clicks) if self.clicks else 0.0

    @property
    def cpm(self) -> float:
        return (self.spend / self.impressions * 1000) if self.impressions else 0.0


@dataclass
class NaverOrder:
    """네이버 스마트스토어 주문 1건."""
    order_id: str
    product_name: str
    amount: float  # 매출 (KRW)
    order_at: datetime
    utm_source: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    refund_amount: float = 0.0  # 환불액 (별도 컬럼)
    is_refunded: bool = False


def _make_campaign_id(idx: int, theme: str) -> str:
    """예: '08-12.2025이야기다이어리_1114' 형식."""
    group = f"{random.randint(1, 20):02d}-{random.randint(1, 25):02d}"
    date_suffix = f"{random.randint(10, 12)}{random.randint(10, 28):02d}"
    return f"{group}.{theme}_{date_suffix}"


def _make_ad_id(idx: int, theme: str, hook: str) -> str:
    """예: '2025이야기다이어리_47/새로운시작_1114' 형식."""
    num = random.randint(20, 80)
    date_suffix = f"{random.randint(10, 12)}{random.randint(10, 28):02d}"
    return f"{theme}_{num}/{hook}_{date_suffix}"


MOCK_NT_DETAILS = [
    "today_cashbook_easy", "bookdive_elementary", "walkingsmile",
    "today_cashbook_category", "1mresolve_accordion", "todaymemory_5year",
    "tts_3month", "renewal2026_oneday_bookdiary", "shoppinglive",
    "winter_planner", "story_diary", "kids_cashbook",
]


def generate_facebook_ads(
    n_ads: int = 50,
    period_days: int = 3,
    ref_date: datetime | None = None,
    seed: int | None = None,
) -> list[FacebookAd]:
    """페북 광고 가짜 데이터 생성.

    Args:
        n_ads: 생성할 광고소재 수.
        period_days: 보고서 집계 기간 (월=3, 수/금=2).
        ref_date: 보고일 기준 (기본: 오늘).
        seed: 난수 시드 (재현용).
    """
    if seed is not None:
        random.seed(seed)
    ref = ref_date or datetime.now()
    period_start = ref - timedelta(days=period_days)

    ads: list[FacebookAd] = []
    for i in range(n_ads):
        theme = random.choice(CAMPAIGN_THEMES)
        hook = random.choice(CREATIVE_HOOKS)
        owner = random.choice(OWNERS)
        delivery = random.choice(DELIVERY_STATUS)

        # 비활성 광고는 노출/클릭이 적음
        scale = 1.0 if delivery == "active" else 0.05

        impressions = int(random.randint(2000, 18000) * scale)
        clicks = int(impressions * random.uniform(0.015, 0.06))
        reach = int(impressions * random.uniform(0.6, 0.95))
        spend = round(clicks * random.uniform(150, 350), 0)

        nt_detail = random.choice(MOCK_NT_DETAILS)
        nt_medium = random.choice(["traffic_b", "traffic_e", "traffic_s"])
        nt_keyword = str(random.randint(1, 30))
        link_url = (
            f"https://mkt.shopping.naver.com/link/abc123"
            f"?nt_source=facebook&nt_medium={nt_medium}&nt_detail={nt_detail}&nt_keyword={nt_keyword}"
        )
        ads.append(
            FacebookAd(
                owner=owner,
                campaign_name=_make_campaign_id(i, theme),
                adset_name="All",
                ad_name=_make_ad_id(i, theme, hook),
                delivery_status=delivery,
                reach=reach,
                clicks=clicks,
                impressions=impressions,
                spend=spend,
                date_start=period_start,
                date_stop=ref,
                link_url=link_url,
                nt_source="facebook",
                nt_medium=nt_medium,
                nt_detail=nt_detail,
                nt_keyword=nt_keyword,
            )
        )
    return ads


def generate_mock_naver_excel_df(facebook_ads, seed: int = 7):
    """페북 광고에 대응되는 Mock 네이버 마케팅분석 데이터프레임 생성 (테스트용)."""
    import pandas as pd
    if seed is not None:
        random.seed(seed)
    used_keys = {(ad.nt_source, ad.nt_medium, ad.nt_detail, ad.nt_keyword) for ad in facebook_ads if ad.nt_detail}
    rows = []
    for source, medium, detail, keyword in used_keys:
        if random.random() > 0.85:
            continue
        rows.append({
            "채널속성": "모바일",
            "nt_source": source,
            "nt_medium": medium,
            "nt_detail": detail,
            "nt_keyword": keyword,
            "유입수": random.randint(100, 3000),
            "결제수": random.randint(0, 50),
            "결제금액": float(random.randint(0, 500000)),
        })
    # 매칭 안 된 (페북에 없는) nt_detail도 일부 추가
    for nt in MOCK_NT_DETAILS:
        if not any(d == nt for _, _, d, _ in used_keys) and random.random() < 0.3:
            rows.append({
                "채널속성": "모바일",
                "nt_source": "facebook",
                "nt_medium": "traffic_b",
                "nt_detail": nt,
                "nt_keyword": str(random.randint(1, 30)),
                "유입수": random.randint(50, 500),
                "결제수": random.randint(0, 10),
                "결제금액": float(random.randint(0, 100000)),
            })
    return pd.DataFrame(rows)


def generate_naver_orders(
    facebook_ads: Iterable[FacebookAd],
    match_rate: float = 0.85,
    avg_order_per_ad: float = 1.5,
    unmatched_orders: int = 8,
    seed: int | None = None,
) -> list[NaverOrder]:
    """페북 광고에 대응되는 네이버 주문 생성.

    Args:
        match_rate: 광고 중 주문이 있는 비율.
        avg_order_per_ad: 광고당 평균 주문 수.
        unmatched_orders: utm 없는 (매칭 실패용) 주문 수.
        seed: 난수 시드.
    """
    if seed is not None:
        random.seed(seed)

    orders: list[NaverOrder] = []
    order_counter = 1

    for ad in facebook_ads:
        if random.random() > match_rate:
            continue
        n_orders = max(1, int(random.gauss(avg_order_per_ad, 1.0)))
        for _ in range(n_orders):
            amount = random.choice([12800, 15800, 19800, 24800, 32000, 42000])
            order_at = ad.date_start + timedelta(
                seconds=random.randint(0, int((ad.date_stop - ad.date_start).total_seconds()))
            )
            is_refunded = random.random() < 0.05  # 5% 환불
            orders.append(
                NaverOrder(
                    order_id=f"2026{order_counter:08d}",
                    product_name=ad.ad_name.split("_")[0],
                    amount=amount,
                    order_at=order_at,
                    utm_source="facebook",
                    utm_campaign=ad.campaign_name,
                    utm_content=ad.ad_name,
                    refund_amount=amount if is_refunded else 0.0,
                    is_refunded=is_refunded,
                )
            )
            order_counter += 1

    # 매칭 실패 케이스 (utm 누락)
    for i in range(unmatched_orders):
        orders.append(
            NaverOrder(
                order_id=f"2026{order_counter:08d}",
                product_name=random.choice(CAMPAIGN_THEMES),
                amount=random.choice([12800, 19800, 32000]),
                order_at=datetime.now() - timedelta(hours=random.randint(1, 72)),
                utm_source=None,
                utm_campaign=None,
                utm_content=None,
            )
        )
        order_counter += 1

    return orders


def generate_last_year_data(
    n_ads: int = 50,
    seed: int = 42,
) -> tuple[list[FacebookAd], list[NaverOrder]]:
    """작년 동기 데이터 생성 (같은 주차)."""
    last_year = datetime.now() - timedelta(days=365)
    ads = generate_facebook_ads(n_ads=n_ads, period_days=3, ref_date=last_year, seed=seed)
    orders = generate_naver_orders(ads, match_rate=0.80, seed=seed + 1)
    return ads, orders


def generate_full_dataset(seed: int = 7) -> dict:
    """이번주 + 지난주 + 작년 동기 데이터 한 번에."""
    now = datetime.now()
    return {
        "this_week": {
            "ads": generate_facebook_ads(n_ads=60, ref_date=now, seed=seed),
            "orders": generate_naver_orders(
                generate_facebook_ads(n_ads=60, ref_date=now, seed=seed),
                seed=seed + 100,
            ),
        },
        "last_week": {
            "ads": generate_facebook_ads(
                n_ads=55, ref_date=now - timedelta(days=7), seed=seed + 10
            ),
            "orders": generate_naver_orders(
                generate_facebook_ads(n_ads=55, ref_date=now - timedelta(days=7), seed=seed + 10),
                seed=seed + 110,
            ),
        },
        "last_year": {
            "ads": generate_facebook_ads(
                n_ads=50, ref_date=now - timedelta(days=365), seed=seed + 20
            ),
            "orders": generate_naver_orders(
                generate_facebook_ads(
                    n_ads=50, ref_date=now - timedelta(days=365), seed=seed + 20
                ),
                seed=seed + 120,
            ),
        },
    }
