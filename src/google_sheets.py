"""구글 스프레드시트 연동 — 보고서 누적 저장."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd


CUMULATIVE_SHEET_NAME = "누적_보고서"
MANUAL_MATCH_SHEET_NAME = "매칭_실패_보정"
VALIDITY_LOG_SHEET_NAME = "광고_상태_변경"


def get_gspread_client_diag():
    """gspread 클라이언트 생성 + 진단 메시지 반환.

    Returns:
        (client, error_message) — 성공 시 (client, ""), 실패 시 (None, "원인")
    """
    try:
        import gspread
        import streamlit as st
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        return None, f"필수 라이브러리 누락: {e}"

    try:
        cfg = st.secrets.get("google", {})
    except Exception as e:
        return None, f"secrets.toml에 [google] 섹션 없음: {e}"

    sa_json_str = cfg.get("SERVICE_ACCOUNT_JSON")
    if not sa_json_str:
        return None, "secrets.toml의 [google] 섹션에 SERVICE_ACCOUNT_JSON 없음"

    try:
        sa_dict = json.loads(sa_json_str) if isinstance(sa_json_str, str) else sa_json_str
    except json.JSONDecodeError as e:
        return None, f"SERVICE_ACCOUNT_JSON 형식 오류 (JSON 파싱 실패): {e}"

    if not isinstance(sa_dict, dict) or "client_email" not in sa_dict:
        return None, "SERVICE_ACCOUNT_JSON에 client_email 필드 없음 (JSON 키 파일 내용 통째 붙여넣었나요?)"

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(sa_dict, scopes=scopes)
        return gspread.authorize(creds), ""
    except Exception as e:
        return None, f"인증 실패: {type(e).__name__}: {e}"


def get_gspread_client():
    """gspread 클라이언트 생성. 시크릿 없으면 None 반환 (호환용)."""
    client, _ = get_gspread_client_diag()
    return client


def get_sheet_id() -> str | None:
    try:
        import streamlit as st
        return st.secrets.get("google", {}).get("SHEET_ID")
    except (ImportError, AttributeError, KeyError):
        return None


def _col_letter(n: int) -> str:
    """1-indexed 열 번호를 알파벳으로 변환 (1→A, 27→AA)."""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def append_report(df: pd.DataFrame, report_date: datetime) -> tuple[bool, str]:
    """보고서를 보고일별 시트(MMDD 이름)에 저장.

    구조:
        === 보고일 YYYY-MM-DD (요일) — 집계 N건 ===
        ▶ 김다빈
        [컬럼 헤더 — 회색]
        [데이터 행들 — ROAS≥100% 셀은 분홍]
        김다빈 소계 ...
    """
    client, err = get_gspread_client_diag()
    if not client:
        return False, f"구글 인증 실패 — {err}"

    sheet_id = get_sheet_id()
    if not sheet_id:
        return False, "secrets.toml의 [google] 섹션에 SHEET_ID 없음"

    try:
        spreadsheet = client.open_by_key(sheet_id)
        sheet_name = report_date.strftime("%m%d")

        try:
            ws = spreadsheet.worksheet(sheet_name)
            ws.clear()
        except Exception:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=2000, cols=40)

        weekday = ["월", "화", "수", "목", "금", "토", "일"][report_date.weekday()]
        # 꺼진 광고 분리:
        #   - 게재상태 != active 이고 매출 == 0 → 시트에서 제외 (저장 안 함)
        #   - 게재상태 != active 이고 매출 > 0 → 맨 아래 별도 섹션 (연한 회색)
        # 매출 컬럼은 라벨 변경 후일 수 있어 동적으로 탐색 (예: "2일매출", "3일매출", "5일매출")
        primary_revenue_col = None
        for c in df.columns:
            cs = str(c)
            if cs.endswith("매출") and cs != "7일매출" and not cs.startswith("작년") and not cs.startswith("지난주"):
                primary_revenue_col = c
                break
        if primary_revenue_col is None and "매출" in df.columns:
            primary_revenue_col = "매출"

        if "게재상태" in df.columns and primary_revenue_col is not None:
            is_active = df["게재상태"].astype(str).str.lower() == "active"
            has_revenue = df[primary_revenue_col].fillna(0).astype(float) > 0
            active_df = df[is_active].copy()
            inactive_with_revenue = df[(~is_active) & has_revenue].copy()
            # 꺼진 광고 + 매출 0 → 완전히 제외
        else:
            active_df = df.copy()
            inactive_with_revenue = df.iloc[0:0].copy()

        # 컬럼 정리
        # 1) 제외: 담당자(섹션 타이틀에 있음), 매칭방식, 게재상태(켜진 것만), 환불액, 작년/지난주 비교 컬럼
        # 2) nt_* 4개는 맨 뒤로 이동 (참고용)
        # 3) 표시 순서는 formatting.display_column_order 사용 (1일지출→N일→7일→유효...)
        from src.formatting import display_column_order

        columns_all = list(df.columns)
        EXCLUDED = {
            "담당자", "매칭방식", "게재상태", "환불액",
            "작년매출", "작년ROAS", "작년대비", "지난주매출", "지난주대비",
        }
        NT_COLS = ["nt_source", "nt_medium", "nt_detail", "nt_keyword"]

        # 동적 days 추론: 컬럼명에서 "N일지출" (N=2~6) 패턴 찾기
        days_inferred = 2
        for c in columns_all:
            if c.endswith("지출") and c not in {"1일지출", "7일지출"}:
                try:
                    days_inferred = int(c.replace("일지출", ""))
                    break
                except ValueError:
                    pass

        preferred_order = display_column_order(days_inferred)
        front = [c for c in preferred_order if c in columns_all and c not in EXCLUDED and c not in NT_COLS]
        # display_column_order에 없는 컬럼은 뒤에 (호환)
        leftover = [c for c in columns_all if c not in front and c not in EXCLUDED and c not in NT_COLS]
        back = [c for c in NT_COLS if c in columns_all]
        columns = front + leftover + back
        n_cols = len(columns)

        spend_col = next((c for c in columns if c.endswith("지출") and c not in {"1일지출", "7일지출"}), None)
        revenue_col = next(
            (c for c in columns
             if c.endswith("매출")
             and c != "7일매출"
             and not c.startswith("작년") and not c.startswith("지난주")),
            None,
        )
        roas_col = next(
            (c for c in columns
             if c.endswith("ROAS") and c != "7일ROAS" and c != "작년ROAS"),
            "ROAS",
        )

        new_rows: list[list] = []
        header_row_indices: list[int] = []      # 회색 — 컬럼 헤더 행
        pink_row_indices: list[int] = []        # 연한 분홍 — 데이터 행 ROAS≥100
        deep_pink_row_indices: list[int] = []   # 진한 분홍 — 담당자 소계 ROAS≥100
        sky_row_indices: list[int] = []         # 하늘색 — 담당자 소계 ROAS<100
        light_gray_row_indices: list[int] = []  # 연한 회색 — 꺼진 광고 (매출 있음)

        section_title = f"▣ 보고일 {report_date.strftime('%Y-%m-%d')} ({weekday}) — 집계 {active_df.shape[0]}건"
        new_rows.append([section_title] + [""] * (n_cols - 1))
        new_rows.append([""] * n_cols)

        for owner in sorted(active_df["담당자"].dropna().unique()):
            group = active_df[active_df["담당자"] == owner]
            if group.empty:
                continue

            new_rows.append([f"▶ {owner}"] + [""] * (n_cols - 1))
            # 컬럼 헤더 (회색 칠할 행)
            new_rows.append(list(columns))
            header_row_indices.append(len(new_rows))

            for _, row in group.iterrows():
                formatted = [_format_cell(c, row[c]) for c in columns]
                new_rows.append(formatted)
                # ROAS≥100 → 행 전체 분홍 칠
                raw_roas = row.get(roas_col) if roas_col in row else row.get("ROAS")
                try:
                    if raw_roas is not None and not pd.isna(raw_roas):
                        v = float(raw_roas)
                        if v >= 100 and v != float("inf"):
                            pink_row_indices.append(len(new_rows))
                except (ValueError, TypeError):
                    pass

            total_spend = float(group[spend_col].sum()) if spend_col and spend_col in group else 0
            total_revenue = float(group[revenue_col].sum()) if revenue_col and revenue_col in group else 0
            roas = (total_revenue / total_spend * 100) if total_spend else 0
            conv_col = next((c for c in columns if c.endswith("전환수")), "전환수")
            total_conv = int(group[conv_col].sum()) if conv_col in group else 0
            subtotal_row = [""] * n_cols
            subtotal_row[0] = f"{owner} 소계"
            col_pos = {name: i for i, name in enumerate(columns)}  # 0-indexed
            if spend_col and spend_col in col_pos:
                subtotal_row[col_pos[spend_col]] = _format_cell(spend_col, total_spend)
            if revenue_col and revenue_col in col_pos:
                subtotal_row[col_pos[revenue_col]] = _format_cell(revenue_col, total_revenue)
            if roas_col in col_pos:
                subtotal_row[col_pos[roas_col]] = _format_cell(roas_col, roas)
            if conv_col in col_pos:
                subtotal_row[col_pos[conv_col]] = _format_cell(conv_col, total_conv)
            new_rows.append(subtotal_row)
            subtotal_row_idx = len(new_rows)
            # 소계 ROAS ≥100% → 진한 분홍, <100% → 하늘색
            try:
                if roas >= 100 and roas != float("inf"):
                    deep_pink_row_indices.append(subtotal_row_idx)
                else:
                    sky_row_indices.append(subtotal_row_idx)
            except (ValueError, TypeError):
                pass
            new_rows.append([""] * n_cols)

        # 꺼진 광고 (매출 있음) 섹션 — 맨 아래 + 연한 회색
        if not inactive_with_revenue.empty:
            new_rows.append([f"▶ 꺼진 광고 (매출 있음, {len(inactive_with_revenue)}건)"] + [""] * (n_cols - 1))
            new_rows.append(list(columns))
            header_row_indices.append(len(new_rows))
            for _, row in inactive_with_revenue.iterrows():
                formatted = [_format_cell(c, row[c]) for c in columns]
                new_rows.append(formatted)
                light_gray_row_indices.append(len(new_rows))

        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")

        # 색상 적용
        try:
            LIGHT_GRAY = {"backgroundColor": {"red": 0.92, "green": 0.92, "blue": 0.92}}
            VERY_LIGHT_GRAY = {"backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96}}
            LIGHT_PINK = {"backgroundColor": {"red": 1.0, "green": 0.91, "blue": 0.95}}
            DEEP_PINK = {"backgroundColor": {"red": 0.98, "green": 0.73, "blue": 0.83}}
            SKY = {"backgroundColor": {"red": 0.85, "green": 0.92, "blue": 1.0}}
            LIGHT_GREEN = {"backgroundColor": {"red": 0.83, "green": 0.96, "blue": 0.79}}   # 연두 (N일 컬럼 헤더)
            LIGHT_BLUE = {"backgroundColor": {"red": 0.78, "green": 0.92, "blue": 0.99}}    # 하늘 (7일 컬럼 헤더)
            formats = []
            last_col = _col_letter(n_cols)

            # 1) 전체 헤더 행 회색
            for row_idx in header_row_indices:
                formats.append({"range": f"A{row_idx}:{last_col}{row_idx}", "format": LIGHT_GRAY})

            # 2) 헤더 중 N일 컬럼은 연두색으로 덮어씀
            n_day_col_names = [
                f"{days_inferred}일지출",
                f"{days_inferred}일매출",
                f"{days_inferred}일전환수",
                f"{days_inferred}일유입수",
                f"{days_inferred}일ROAS",
            ]
            n_day_indices = [columns.index(c) for c in n_day_col_names if c in columns]
            if n_day_indices:
                ng_start = _col_letter(min(n_day_indices) + 1)
                ng_end = _col_letter(max(n_day_indices) + 1)
                for row_idx in header_row_indices:
                    formats.append({
                        "range": f"{ng_start}{row_idx}:{ng_end}{row_idx}",
                        "format": LIGHT_GREEN,
                    })

            # 3) 헤더 중 7일 컬럼은 하늘색으로 덮어씀
            seven_day_names = ["7일지출", "7일매출", "7일ROAS"]
            seven_indices = [columns.index(c) for c in seven_day_names if c in columns]
            if seven_indices:
                sb_start = _col_letter(min(seven_indices) + 1)
                sb_end = _col_letter(max(seven_indices) + 1)
                for row_idx in header_row_indices:
                    formats.append({
                        "range": f"{sb_start}{row_idx}:{sb_end}{row_idx}",
                        "format": LIGHT_BLUE,
                    })

            # 4) 데이터 행 색상 (순서: pink → deep_pink → sky → light_gray)
            for row_idx in pink_row_indices:
                formats.append({"range": f"A{row_idx}:{last_col}{row_idx}", "format": LIGHT_PINK})
            for row_idx in deep_pink_row_indices:
                formats.append({"range": f"A{row_idx}:{last_col}{row_idx}", "format": DEEP_PINK})
            for row_idx in sky_row_indices:
                formats.append({"range": f"A{row_idx}:{last_col}{row_idx}", "format": SKY})
            for row_idx in light_gray_row_indices:
                formats.append({"range": f"A{row_idx}:{last_col}{row_idx}", "format": VERY_LIGHT_GRAY})

            if formats:
                ws.batch_format(formats)
        except Exception:
            pass  # 색상 실패해도 데이터는 저장됨

        # 컬럼 너비 조정: 모든 컬럼 자동 맞춤 → 일부 컬럼은 고정 픽셀
        try:
            width_requests = [{
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": n_cols,
                    }
                }
            }]
            fixed_widths = {
                "캠페인명": 75,
                "광고세트": 200,
                "광고이름": 200,
                "유효": 50,
                "유효사유": 140,
            }
            for fixed_col, px in fixed_widths.items():
                if fixed_col in columns:
                    col_idx = columns.index(fixed_col)
                    width_requests.append({
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": ws.id,
                                "dimension": "COLUMNS",
                                "startIndex": col_idx,
                                "endIndex": col_idx + 1,
                            },
                            "properties": {"pixelSize": px},
                            "fields": "pixelSize",
                        }
                    })
            spreadsheet.batch_update({"requests": width_requests})
        except Exception:
            pass  # 너비 조정 실패해도 데이터는 저장됨

        n_pink = len(pink_row_indices) + len(deep_pink_row_indices)
        return True, (
            f"'{sheet_name}' 탭에 저장됨 ({len(new_rows)}행 / "
            f"분홍 {n_pink} / 하늘 {len(sky_row_indices)} / "
            f"꺼진광고매출있음 {len(light_gray_row_indices)})"
        )
    except Exception as e:
        return False, f"시트 저장 실패: {e}"


def fetch_validity_history(report_date: datetime, lookback_days: int = 7) -> dict:
    """모든 MMDD 탭에서 최근 N일치 데이터 읽어 광고별 7일 ROAS 계산.

    Returns:
        {ad_name: {"7d_revenue", "7d_spend", "7d_roas", "has_enough_history"}}
    """
    client = get_gspread_client()
    sheet_id = get_sheet_id()
    if not client or not sheet_id:
        return {}

    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheets = spreadsheet.worksheets()
    except Exception:
        return {}

    cutoff = report_date - timedelta(days=lookback_days)
    grouped: dict = {}
    dates_seen: set[str] = set()

    for ws in worksheets:
        # MMDD 패턴 (4자리 숫자) 탭만 처리
        title = ws.title.strip()
        if not (len(title) == 4 and title.isdigit()):
            continue
        # 동일 연도 가정
        try:
            ws_date = datetime(report_date.year, int(title[:2]), int(title[2:]))
        except ValueError:
            # 작년 폴백 (1월 보고일에서 12월 시트 참조 등)
            try:
                ws_date = datetime(report_date.year - 1, int(title[:2]), int(title[2:]))
            except ValueError:
                continue
        if ws_date < cutoff or ws_date > report_date:
            continue

        try:
            rows = ws.get_all_values()
        except Exception:
            continue

        # 헤더 동적 검색: 셀에 "광고이름"이 들어있는 행이 컬럼 헤더
        current_header: list[str] | None = None
        for row in rows:
            if not row or not any(c.strip() for c in row):
                continue
            stripped = [(c or "").strip() for c in row]
            if "광고이름" in stripped:
                current_header = stripped
                continue
            if not current_header:
                continue
            # 데이터 행
            row_dict = {current_header[i]: row[i] for i in range(min(len(current_header), len(row))) if current_header[i]}
            ad_name = str(row_dict.get("광고이름", "")).strip()
            first = (row[0] or "").strip()
            if not ad_name or first.endswith("소계") or first.startswith("===") or first.startswith("▣") or first.startswith("▶"):
                continue
            # N일지출/매출만 합산 (1일지출=일평균, 7일지출/매출=누적값이라 중복합산 방지로 제외)
            spend = _read_money(
                row_dict,
                ("지출", "2일지출", "3일지출", "4일지출", "5일지출", "6일지출"),
            )
            revenue = _read_money(
                row_dict,
                ("매출", "2일매출", "3일매출", "4일매출", "5일매출", "6일매출"),
            )
            ex = grouped.setdefault(ad_name, {"spend": 0.0, "revenue": 0.0, "dates": set()})
            ex["spend"] += spend
            ex["revenue"] += revenue
            ex["dates"].add(title)
            dates_seen.add(title)

    result: dict = {}
    for ad_name, data in grouped.items():
        spend = data["spend"]
        revenue = data["revenue"]
        roas = (revenue / spend * 100) if spend > 0 else 0.0
        has_enough = len(data["dates"]) >= 2  # 월·수·금 기준 2회 이상이면 충분
        result[ad_name] = {
            "7d_revenue": revenue,
            "7d_spend": spend,
            "7d_roas": roas,
            "has_enough_history": has_enough,
        }
    return result


def fetch_report_from_sheet(report_date: datetime) -> pd.DataFrame:
    """저장된 MMDD 탭에서 보고서 DataFrame 복원 (비교용).

    Returns:
        매칭 완료 DataFrame (광고이름·지출·매출·ROAS·전환수 등). 없으면 빈 DF.
    """
    client = get_gspread_client()
    sheet_id = get_sheet_id()
    if not client or not sheet_id:
        return pd.DataFrame()

    sheet_name = report_date.strftime("%m%d")
    try:
        spreadsheet = client.open_by_key(sheet_id)
        ws = spreadsheet.worksheet(sheet_name)
        rows = ws.get_all_values()
    except Exception:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    records = []
    current_header: list[str] | None = None
    current_owner = ""
    for row in rows:
        if not row or not any((c or "").strip() for c in row):
            continue
        first = (row[0] or "").strip()
        # 섹션 타이틀 / 빈 행 건너뜀
        if first.startswith("▣") or first.startswith("==="):
            continue
        if first.startswith("▶"):
            current_owner = first.lstrip("▶").strip()
            continue
        if first.endswith("소계"):
            continue
        stripped = [(c or "").strip() for c in row]
        # 헤더 행
        if "광고이름" in stripped:
            current_header = stripped
            continue
        if not current_header:
            continue
        # 데이터 행
        row_dict = {current_header[i]: row[i] for i in range(min(len(current_header), len(row))) if current_header[i]}
        if not str(row_dict.get("광고이름", "")).strip():
            continue
        # ROAS·전환수도 라벨이 N일ROAS/N일전환수로 변경됐을 수 있어 동적 탐색
        roas_value = 0.0
        for k in ("ROAS", "2일ROAS", "3일ROAS", "4일ROAS", "5일ROAS", "6일ROAS"):
            if k in row_dict and row_dict[k]:
                roas_value = _parse_pct(row_dict[k])
                break
        conv_value = 0
        for k in ("전환수", "2일전환수", "3일전환수", "4일전환수", "5일전환수", "6일전환수"):
            if k in row_dict and row_dict[k]:
                conv_value = _parse_int(row_dict[k])
                break

        record = {
            "담당자": current_owner,
            "캠페인명": row_dict.get("캠페인명", ""),
            "광고세트": row_dict.get("광고세트", ""),
            "광고이름": str(row_dict.get("광고이름", "")).strip(),
            "지출": _read_money(row_dict, ("지출", "2일지출", "3일지출", "4일지출", "5일지출", "6일지출")),
            "매출": _read_money(row_dict, ("매출", "2일매출", "3일매출", "4일매출", "5일매출", "6일매출")),
            "ROAS": roas_value,
            "전환수": conv_value,
        }
        records.append(record)
    return pd.DataFrame(records)


def _parse_pct(v) -> float:
    if v is None or v == "" or v == "-":
        return 0.0
    s = str(v).replace("%", "").replace(",", "").strip()
    if s in ("∞", "-∞"):
        return float("inf") if s == "∞" else float("-inf")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_int(v) -> int:
    if v is None or v == "":
        return 0
    s = str(v).replace(",", "").replace("₩", "").strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _read_money(row: dict, candidate_keys: tuple) -> float:
    """row에서 후보 컬럼들 중 첫 번째로 발견된 값을 float로 반환."""
    for key in candidate_keys:
        val = row.get(key)
        if val is None or val == "":
            continue
        try:
            # "₩42,000" 같은 문자열도 처리
            s = str(val).replace("₩", "").replace(",", "").strip()
            return float(s) if s else 0.0
        except (ValueError, TypeError):
            continue
    return 0.0


def log_manual_match(
    order_id: str,
    matched_ad_name: str,
    user: str,
    reason: str = "",
) -> None:
    """수동 매칭 이력 기록."""
    client = get_gspread_client()
    sheet_id = get_sheet_id()
    if not client or not sheet_id:
        return
    try:
        spreadsheet = client.open_by_key(sheet_id)
        try:
            ws = spreadsheet.worksheet(MANUAL_MATCH_SHEET_NAME)
        except Exception:
            ws = spreadsheet.add_worksheet(title=MANUAL_MATCH_SHEET_NAME, rows=1000, cols=10)
            ws.append_row(["일시", "주문ID", "매칭광고명", "사용자", "메모"])
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            order_id,
            matched_ad_name,
            user,
            reason,
        ])
    except Exception:
        pass


def _to_value(v):
    if v is None:
        return ""
    if pd.isna(v):
        return ""
    if isinstance(v, float):
        if v == float("inf"):
            return "∞"
        if v == float("-inf"):
            return "-∞"
        if v != v:
            return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


_PCT_COLS = {"ROAS", "작년대비", "지난주대비", "작년ROAS", "7일ROAS"}
_INT_COLS = {"전환수", "클릭", "노출", "도달", "유입수"}


def _is_pct(name: str) -> bool:
    return name in _PCT_COLS or name.endswith("ROAS")


def _is_int_count(name: str) -> bool:
    return name in _INT_COLS or name.endswith("전환수") or name.endswith("유입수")


def _format_cell(col_name: str, v):
    """컬럼명 기반 포맷 (천 단위 콤마 + ₩/%)."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v == "":
        return ""
    if isinstance(v, float):
        if v == float("inf"):
            return "∞%" if _is_pct(col_name) else "∞"
        if v == float("-inf"):
            return "-∞"
        if v != v:
            return ""
    name = str(col_name)
    # 퍼센트 (N일ROAS, 작년/지난주 비교) — 돈 컬럼보다 먼저 체크 (ROAS는 돈 아님)
    if _is_pct(name):
        try:
            return f"{int(float(v)):,}%"
        except (ValueError, TypeError):
            return _to_value(v)
    # 돈 단위 (지출/매출 + N일지출 N일매출 + 환불/CPC/CPM)
    if (name.endswith("지출") or name.endswith("매출")
            or name in {"환불액", "CPC", "CPM"}):
        try:
            return f"₩{int(float(v)):,}"
        except (ValueError, TypeError):
            return _to_value(v)
    if _is_int_count(name):
        try:
            return f"{int(float(v)):,}"
        except (ValueError, TypeError):
            return _to_value(v)
    if name == "CTR":
        try:
            return f"{float(v):.2f}%"
        except (ValueError, TypeError):
            return _to_value(v)
    return _to_value(v)
