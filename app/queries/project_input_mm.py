"""프로젝트 실행원가 비교 — 실행예산(계획) 대비 실제 집행 비교.

메뉴 "프로젝트 투입 M/M (설계중)" 자리를 대체하는 화면의 데이터 소스. 기획 PPT
(`그룹웨어 프로그램 기획.pptx`, 슬라이드 2 "프로젝트 집행비용 비교")에 정의된 필드를
그대로 따른다:

- 계약금액(수주금액) · 제안비용: 실행예산 계획값과 동일 — project_cost.py의 계산 결과를
  재사용한다(프로젝트별 최신 승인 실행예산 1건만 반영하는 로직 포함).
- 노무비: 계획은 실행예산의 인건비(TOTAL_MM*UNTPC)를 그대로 쓰고, 실적은
  tb_wrkst_diary_info(업무일지)의 실제 투입시간(TM)을 직원 직급(tb_employee.RNK)·근무
  연도별로 묶어 tb_labor_cost 단가표(적용년도+직급코드 -> 인월단가)를 적용해 계산한다
  ("1인월=160시간" 기준). 해당 연도·직급의 단가가 아직 등록돼 있지 않으면 그 시간은
  0원으로 계산하고 unrated_labor_hours로 따로 집계한다.
- 경비: 계획은 실행예산 경비(tb_request_exec_bgt_expens에서 제안비용·재료비를 뺀 나머지,
  project_cost.py의 expense)이고, 실적은 전자결재 경비 지출결의(tb_request_expenses)의
  해당 프로젝트 EXPS_PRC 합계다(RFSL_DT가 있는 반려 건만 제외, 승인/진행중은 모두 포함).
- 외주비: 계획은 실행예산의 매입(tb_request_exec_bgt_prchss)이고, 실적은
  tb_prj_sales_prchss(매출/매입 원장)에서 매입 구분(tb_prj_contrt.SALES_PRCHSS_DIV
  ='P602')인 건의 금액 합계다(확정 여부와 무관하게 등록된 전체 합계).
"""

from dataclasses import dataclass

from app.config import DatabaseConfig
from app.db import fetch_all, fetch_one
from app.queries.labor_cost import get_rate_map
from app.queries.project_cost import get_project_cost_rows

PURCHASE_DIV = "P602"

STANDARD_MONTH_HOURS = 160


@dataclass(frozen=True)
class ExecutionComparisonRow:
    prj_id: str
    prj_name: str
    client_name: str
    period: str
    contract_amount: int  # 계약금액(수주금액)
    proposal_cost: int  # 제안비용
    plan_labor_cost: int  # 노무비 - 계획(실행예산)
    actual_labor_hours: float  # 노무비 실적 계산 근거 시간(업무일지 합계)
    actual_labor_cost: int  # 노무비 - 실적(직급별 단가표 적용)
    unrated_labor_hours: float  # 단가표에 없는 (연도, 직급) 조합이라 0원 처리된 시간
    plan_expense: int  # 경비 - 계획(실행예산 경비)
    actual_expense: int  # 경비 - 실적(전자결재 지출결의 합계, 반려 제외)
    plan_outsourcing_cost: int  # 외주비 - 계획(실행예산)
    actual_outsourcing_cost: int  # 외주비 - 실적(매입 원장 합계)


def get_project_options(db_cfg: DatabaseConfig) -> list[tuple[str, str, str]]:
    """프로젝트 선택 리스트박스용 (PRJ_ID, PRJ_NM, 발주처명) 전체 목록."""
    rows = fetch_all(
        db_cfg,
        """
        SELECT pi.PRJ_ID, pi.PRJ_NM, acc.ACCNT_NM
        FROM tb_prj_info pi
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        ORDER BY pi.PRJ_ID ASC
        """,
    )
    return [(row["PRJ_ID"], row["PRJ_NM"] or "", row["ACCNT_NM"] or "") for row in rows]


def _get_actual_labor_cost(db_cfg: DatabaseConfig, prj_id: str) -> tuple[float, int, float]:
    """반환: (총 투입시간, 노무비 합계, 단가 미등록으로 0원 처리된 시간)."""
    rows = fetch_all(
        db_cfg,
        """
        SELECT e.RNK, YEAR(d.WRKST_SCHDUL_DT) AS apply_year, SUM(d.TM) AS total_tm
        FROM tb_wrkst_diary_info d
        JOIN tb_employee e ON e.EMPL_ID = d.EMPL_ID
        WHERE d.PRJ_ID = %s
        GROUP BY e.RNK, YEAR(d.WRKST_SCHDUL_DT)
        """,
        (prj_id,),
    )
    rate_map = get_rate_map(db_cfg)

    total_hours = 0.0
    total_cost = 0
    unrated_hours = 0.0
    for row in rows:
        hours = float(row["total_tm"])
        total_hours += hours
        rate = rate_map.get((str(row["apply_year"]), row["RNK"]))
        if rate is None:
            unrated_hours += hours
            continue
        total_cost += round(hours / STANDARD_MONTH_HOURS * rate)

    return total_hours, total_cost, unrated_hours


def _get_actual_expense(db_cfg: DatabaseConfig, prj_id: str) -> int:
    """전자결재 경비 지출결의(tb_request_expenses)의 실제 사용 경비 합계.
    반려된 건(RFSL_DT IS NOT NULL)만 제외하고, 승인·진행중 건은 모두 합산한다."""
    row = fetch_one(
        db_cfg,
        """
        SELECT COALESCE(SUM(EXPS_PRC), 0) AS total
        FROM tb_request_expenses
        WHERE PRJ_ID = %s AND RFSL_DT IS NULL
        """,
        (prj_id,),
    )
    return int(row["total"]) if row else 0


def _get_actual_outsourcing_cost(db_cfg: DatabaseConfig, prj_id: str) -> int:
    row = fetch_one(
        db_cfg,
        """
        SELECT COALESCE(SUM(sp.PRC), 0) AS total
        FROM tb_prj_sales_prchss sp
        JOIN tb_prj_contrt pc ON sp.PRJ_ID = pc.PRJ_ID AND sp.CONTRT_CD = pc.CONTRT_CD
        WHERE sp.PRJ_ID = %s AND pc.SALES_PRCHSS_DIV = %s
        """,
        (prj_id, PURCHASE_DIV),
    )
    return int(row["total"]) if row else 0


def get_bulk_actuals(db_cfg: DatabaseConfig) -> dict[str, dict[str, float | int]]:
    """전체 프로젝트의 노무비/경비/외주비 실적을 프로젝트별로 한 번에 집계한다.
    "프로젝트 원가" 그리드에 실적 비교 행을 추가할 때처럼, 프로젝트 수만큼
    get_execution_comparison을 반복 호출하면 쿼리가 N배로 늘어나므로 이 함수로
    한 번에 계산한다. 반환값의 각 프로젝트 dict는 labor/expense/outsourcing 키를
    가진다(단가 미등록 등으로 데이터가 없는 프로젝트는 결과에서 빠지며, 호출한
    쪽에서 .get(prj_id, {})로 기본값 0 처리하면 된다)."""
    labor_rows = fetch_all(
        db_cfg,
        """
        SELECT d.PRJ_ID, e.RNK, YEAR(d.WRKST_SCHDUL_DT) AS apply_year, SUM(d.TM) AS total_tm
        FROM tb_wrkst_diary_info d
        JOIN tb_employee e ON e.EMPL_ID = d.EMPL_ID
        GROUP BY d.PRJ_ID, e.RNK, YEAR(d.WRKST_SCHDUL_DT)
        """,
    )
    rate_map = get_rate_map(db_cfg)
    labor_by_prj: dict[str, int] = {}
    for row in labor_rows:
        rate = rate_map.get((str(row["apply_year"]), row["RNK"]))
        if rate is None:
            continue
        hours = float(row["total_tm"])
        prj_id = row["PRJ_ID"]
        labor_by_prj[prj_id] = labor_by_prj.get(prj_id, 0) + round(hours / STANDARD_MONTH_HOURS * rate)

    expense_rows = fetch_all(
        db_cfg,
        """
        SELECT PRJ_ID, COALESCE(SUM(EXPS_PRC), 0) AS total
        FROM tb_request_expenses
        WHERE RFSL_DT IS NULL AND PRJ_ID IS NOT NULL
        GROUP BY PRJ_ID
        """,
    )
    expense_by_prj = {row["PRJ_ID"]: int(row["total"]) for row in expense_rows}

    outsourcing_rows = fetch_all(
        db_cfg,
        """
        SELECT sp.PRJ_ID, COALESCE(SUM(sp.PRC), 0) AS total
        FROM tb_prj_sales_prchss sp
        JOIN tb_prj_contrt pc ON sp.PRJ_ID = pc.PRJ_ID AND sp.CONTRT_CD = pc.CONTRT_CD
        WHERE pc.SALES_PRCHSS_DIV = %s
        GROUP BY sp.PRJ_ID
        """,
        (PURCHASE_DIV,),
    )
    outsourcing_by_prj = {row["PRJ_ID"]: int(row["total"]) for row in outsourcing_rows}

    prj_ids = set(labor_by_prj) | set(expense_by_prj) | set(outsourcing_by_prj)
    return {
        prj_id: {
            "labor": labor_by_prj.get(prj_id, 0),
            "expense": expense_by_prj.get(prj_id, 0),
            "outsourcing": outsourcing_by_prj.get(prj_id, 0),
        }
        for prj_id in prj_ids
    }


def get_execution_comparison(db_cfg: DatabaseConfig, prj_id: str) -> ExecutionComparisonRow | None:
    plan_rows = get_project_cost_rows(db_cfg)
    plan = next((row for row in plan_rows if row.prj_code == prj_id), None)
    if plan is None:
        return None

    actual_hours, actual_labor_cost, unrated_hours = _get_actual_labor_cost(db_cfg, prj_id)
    actual_expense = _get_actual_expense(db_cfg, prj_id)
    actual_outsourcing_cost = _get_actual_outsourcing_cost(db_cfg, prj_id)

    return ExecutionComparisonRow(
        prj_id=plan.prj_code,
        prj_name=plan.prj_name,
        client_name=plan.client_name,
        period=plan.period,
        contract_amount=plan.revenue,
        proposal_cost=plan.proposal_cost,
        plan_labor_cost=plan.labor_cost,
        actual_labor_hours=actual_hours,
        actual_labor_cost=actual_labor_cost,
        unrated_labor_hours=unrated_hours,
        plan_expense=plan.expense,
        actual_expense=actual_expense,
        plan_outsourcing_cost=plan.outsourcing_cost,
        actual_outsourcing_cost=actual_outsourcing_cost,
    )
