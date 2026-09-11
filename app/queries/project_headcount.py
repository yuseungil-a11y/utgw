"""프로젝트 인력 투입 — tb_wrkst_diary_info(업무일지) 기준 월별 투입시간 집계.

두 가지 보기를 제공한다.
- 프로젝트 기준: 프로젝트 × 월 = 투입시간(TM) 합계 + 투입인원(기간 내 distinct 직원 수)
- 사람 기준: (직원, 프로젝트) × 월 = 투입시간 합계

시간 단위는 tb_wrkst_diary_info.TM(시간, 0.1 단위)을 그대로 합산한 값이다. 프로젝트명/
직원명/부서는 각각 tb_prj_info · tb_employee · tb_organization과 LEFT JOIN해서 채운다
(업무일지에만 있고 마스터에 없는 코드는 코드값을 그대로 노출한다).
"""

from dataclasses import dataclass
from datetime import date

from app.config import DatabaseConfig
from app.db import fetch_all


def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def period_months(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> list[tuple[int, int]]:
    """조회기간(시작 연/월 ~ 종료 연/월)을 아우르는 (연,월) 목록."""
    months: list[tuple[int, int]] = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _period_bounds(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> tuple[date, date]:
    start = date(start_year, start_month, 1)
    ey, em = _month_add(end_year, end_month, 1)
    return start, date(ey, em, 1)  # end는 다음 달 1일(미포함)


@dataclass(frozen=True)
class ProjectMonthRow:
    prj_id: str
    prj_name: str
    headcount: int  # 조회기간 내 투입인원(distinct 직원)
    total_hours: float
    monthly: dict[str, float]  # 'YYYYMM' -> 시간


@dataclass(frozen=True)
class PersonProjectMonthRow:
    empl_id: str
    empl_name: str
    dept: str
    prj_id: str
    prj_name: str
    total_hours: float
    monthly: dict[str, float]  # 'YYYYMM' -> 시간


def get_diary_date_bounds(db_cfg: DatabaseConfig) -> tuple[date | None, date | None]:
    rows = fetch_all(
        db_cfg,
        "SELECT MIN(WRKST_SCHDUL_DT) AS mn, MAX(WRKST_SCHDUL_DT) AS mx FROM tb_wrkst_diary_info",
    )
    if not rows or rows[0]["mn"] is None:
        return None, None
    return rows[0]["mn"], rows[0]["mx"]


def get_project_month_hours(
    db_cfg: DatabaseConfig, start_year: int, start_month: int, end_year: int, end_month: int
) -> list[ProjectMonthRow]:
    start, end_ex = _period_bounds(start_year, start_month, end_year, end_month)

    rows = fetch_all(
        db_cfg,
        """
        SELECT
            d.PRJ_ID,
            COALESCE(pi.PRJ_NM, d.PRJ_ID) AS prj_name,
            YEAR(d.WRKST_SCHDUL_DT) AS yr,
            MONTH(d.WRKST_SCHDUL_DT) AS mo,
            SUM(d.TM) AS hours
        FROM tb_wrkst_diary_info d
        LEFT JOIN tb_prj_info pi ON pi.PRJ_ID = d.PRJ_ID
        WHERE d.WRKST_SCHDUL_DT >= %s AND d.WRKST_SCHDUL_DT < %s
        GROUP BY d.PRJ_ID, prj_name, yr, mo
        ORDER BY prj_name, d.PRJ_ID
        """,
        (start, end_ex),
    )

    hc_rows = fetch_all(
        db_cfg,
        """
        SELECT d.PRJ_ID, COUNT(DISTINCT d.EMPL_ID) AS hc
        FROM tb_wrkst_diary_info d
        WHERE d.WRKST_SCHDUL_DT >= %s AND d.WRKST_SCHDUL_DT < %s
        GROUP BY d.PRJ_ID
        """,
        (start, end_ex),
    )
    headcount_by_prj = {row["PRJ_ID"]: int(row["hc"]) for row in hc_rows}

    by_prj: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        prj_id = row["PRJ_ID"]
        if prj_id not in by_prj:
            by_prj[prj_id] = {"name": row["prj_name"] or prj_id, "monthly": {}, "total": 0.0}
            order.append(prj_id)
        hours = float(row["hours"] or 0)
        yyyymm = f"{int(row['yr']):04d}{int(row['mo']):02d}"
        entry = by_prj[prj_id]
        entry["monthly"][yyyymm] = entry["monthly"].get(yyyymm, 0.0) + hours
        entry["total"] += hours

    return [
        ProjectMonthRow(
            prj_id=prj_id,
            prj_name=by_prj[prj_id]["name"],
            headcount=headcount_by_prj.get(prj_id, 0),
            total_hours=by_prj[prj_id]["total"],
            monthly=by_prj[prj_id]["monthly"],
        )
        for prj_id in order
    ]


def get_person_project_month_hours(
    db_cfg: DatabaseConfig, start_year: int, start_month: int, end_year: int, end_month: int
) -> list[PersonProjectMonthRow]:
    start, end_ex = _period_bounds(start_year, start_month, end_year, end_month)

    rows = fetch_all(
        db_cfg,
        """
        SELECT
            d.EMPL_ID,
            COALESCE(e.EMPL_NM, d.EMPL_ID) AS empl_name,
            COALESCE(org.ORG_NM, '') AS dept,
            d.PRJ_ID,
            COALESCE(pi.PRJ_NM, d.PRJ_ID) AS prj_name,
            YEAR(d.WRKST_SCHDUL_DT) AS yr,
            MONTH(d.WRKST_SCHDUL_DT) AS mo,
            SUM(d.TM) AS hours
        FROM tb_wrkst_diary_info d
        LEFT JOIN tb_employee e ON e.EMPL_ID = d.EMPL_ID
        LEFT JOIN tb_organization org ON org.ORG_ID = e.ORG_ID
        LEFT JOIN tb_prj_info pi ON pi.PRJ_ID = d.PRJ_ID
        WHERE d.WRKST_SCHDUL_DT >= %s AND d.WRKST_SCHDUL_DT < %s
        GROUP BY d.EMPL_ID, empl_name, dept, d.PRJ_ID, prj_name, yr, mo
        ORDER BY empl_name, d.EMPL_ID, prj_name, d.PRJ_ID
        """,
        (start, end_ex),
    )

    by_key: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (row["EMPL_ID"], row["PRJ_ID"])
        if key not in by_key:
            by_key[key] = {
                "empl_name": row["empl_name"] or row["EMPL_ID"],
                "dept": row["dept"] or "",
                "prj_name": row["prj_name"] or row["PRJ_ID"],
                "monthly": {},
                "total": 0.0,
            }
            order.append(key)
        hours = float(row["hours"] or 0)
        yyyymm = f"{int(row['yr']):04d}{int(row['mo']):02d}"
        entry = by_key[key]
        entry["monthly"][yyyymm] = entry["monthly"].get(yyyymm, 0.0) + hours
        entry["total"] += hours

    result: list[PersonProjectMonthRow] = []
    for empl_id, prj_id in order:
        entry = by_key[(empl_id, prj_id)]
        result.append(
            PersonProjectMonthRow(
                empl_id=empl_id,
                empl_name=entry["empl_name"],
                dept=entry["dept"],
                prj_id=prj_id,
                prj_name=entry["prj_name"],
                total_hours=entry["total"],
                monthly=entry["monthly"],
            )
        )
    return result
