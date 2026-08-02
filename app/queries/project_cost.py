"""프로젝트원가 집계 쿼리. "실행예산관리"(tb_request_exec_bgt 계열) 참조.

- tb_prj_exec_bgt: PRJ_ID <-> SND_REQ_NO(승인된 실행예산 요청) 연결 테이블.
  한 프로젝트에 여러 승인 건(수정/증액 등)이 있을 수 있어 전부 합산한다.
- 경비 세부 코드는 tb_sub_category에서 확인했다:
  EXPS_MACTG_DIV='D201'(제안비용), EXPS_MACTG_DIV='D221'(재료비) 두 그룹을
  경비합계에서 분리해 각각 "제안비"/"재료비"로, 나머지를 "경비"로 잡는다.
- 노무비는 전용 테이블 tb_request_exec_bgt_lbcst(TOTAL_MM*UNTPC 합),
  외주비는 전용 테이블 tb_request_exec_bgt_prchss(PRC 합)를 그대로 쓴다.
- 발주처와 매출처는 서로 다른 값이다 (실제 화면으로 확인함): 발주처는
  tb_prj_info.ACCNT_NO(최종 발주기관, 예: 부산광역시), 매출처는 tb_prj_contrt
  중 매출 계약(SALES_PRCHSS_DIV='P601')의 거래처다 (예: 하도급 원청 동인시스템).
"""

from dataclasses import dataclass

from app.config import DatabaseConfig
from app.db import fetch_all

PROPOSAL_MACTG_DIV = "D201"
MATERIAL_MACTG_DIV = "D221"
PM_ROLE_DIV = "P201"

GENERAL_ADMIN_RATE = 0.15
SALES_COST_RATE = 0.01
WARRANTY_RATE = 0.03

COLUMNS = [
    "프로젝트코드",
    "프로젝트명",
    "수행조직",
    "PM",
    "발주처",
    "매출처",
    "프로젝트 기간",
    "매출총액",
    "제안비용",
    "재료비",
    "노무비",
    "경비",
    "일반관리비",
    "영업비",
    "외주비",
    "영업이익",
    "하자보수비",
    "최종영업이익",
]


@dataclass(frozen=True)
class ProjectCostRow:
    prj_code: str
    prj_name: str
    exec_org: str
    pm_name: str
    client_name: str
    sales_account_name: str
    period: str
    revenue: int
    proposal_cost: int
    material_cost: int
    labor_cost: int
    expense: int
    general_admin_cost: int
    sales_cost: int
    outsourcing_cost: int
    operating_profit: int
    warranty_cost: int
    final_operating_profit: int

    def as_tuple(self) -> tuple:
        return (
            self.prj_code,
            self.prj_name,
            self.exec_org,
            self.pm_name,
            self.client_name,
            self.sales_account_name,
            self.period,
            self.revenue,
            self.proposal_cost,
            self.material_cost,
            self.labor_cost,
            self.expense,
            self.general_admin_cost,
            self.sales_cost,
            self.outsourcing_cost,
            self.operating_profit,
            self.warranty_cost,
            self.final_operating_profit,
        )


def _fmt_date(value) -> str:
    return value.isoformat() if value else ""


def _fmt_period(start, end) -> str:
    if not start and not end:
        return ""
    return f"{_fmt_date(start)} ~ {_fmt_date(end)}"


def _build_req_to_prj_map(db_cfg: DatabaseConfig) -> dict[str, str]:
    rows = fetch_all(db_cfg, "SELECT PRJ_ID, SND_REQ_NO FROM tb_prj_exec_bgt")
    return {row["SND_REQ_NO"]: row["PRJ_ID"] for row in rows}


def _accumulate(totals: dict[str, int], prj_id: str | None, amount: int) -> None:
    if prj_id is None:
        return
    totals[prj_id] = totals.get(prj_id, 0) + amount


def get_project_cost_rows(db_cfg: DatabaseConfig) -> list[ProjectCostRow]:
    req_to_prj = _build_req_to_prj_map(db_cfg)

    revenue_by_prj: dict[str, int] = {}
    for row in fetch_all(db_cfg, "SELECT SND_REQ_NO, BSNDVL_PRC FROM tb_request_exec_bgt"):
        _accumulate(revenue_by_prj, req_to_prj.get(row["SND_REQ_NO"]), int(row["BSNDVL_PRC"]))

    proposal_by_prj: dict[str, int] = {}
    material_by_prj: dict[str, int] = {}
    expense_total_by_prj: dict[str, int] = {}
    for row in fetch_all(
        db_cfg, "SELECT SND_REQ_NO, EXPS_MACTG_DIV, PRC FROM tb_request_exec_bgt_expens"
    ):
        prj_id = req_to_prj.get(row["SND_REQ_NO"])
        prc = int(row["PRC"])
        _accumulate(expense_total_by_prj, prj_id, prc)
        if row["EXPS_MACTG_DIV"] == PROPOSAL_MACTG_DIV:
            _accumulate(proposal_by_prj, prj_id, prc)
        elif row["EXPS_MACTG_DIV"] == MATERIAL_MACTG_DIV:
            _accumulate(material_by_prj, prj_id, prc)

    labor_by_prj: dict[str, int] = {}
    for row in fetch_all(
        db_cfg, "SELECT SND_REQ_NO, TOTAL_MM, UNTPC FROM tb_request_exec_bgt_lbcst"
    ):
        amount = round(float(row["TOTAL_MM"]) * int(row["UNTPC"]))
        _accumulate(labor_by_prj, req_to_prj.get(row["SND_REQ_NO"]), amount)

    outsourcing_by_prj: dict[str, int] = {}
    for row in fetch_all(db_cfg, "SELECT SND_REQ_NO, PRC FROM tb_request_exec_bgt_prchss"):
        _accumulate(outsourcing_by_prj, req_to_prj.get(row["SND_REQ_NO"]), int(row["PRC"]))

    # 매출처: tb_prj_info.ACCNT_NO(발주처, 예: 부산광역시)와는 다른 개념이다.
    # 실제 화면에서 확인한 결과, 매출처는 tb_prj_contrt(매출 계약)의 거래처였다
    # (예: 26-PRJ-0001의 발주처는 부산광역시지만, 매출처는 하도급 원청인 동인시스템).
    sales_account_by_prj: dict[str, str] = {}
    for row in fetch_all(
        db_cfg,
        """
        SELECT pc.PRJ_ID, GROUP_CONCAT(DISTINCT acc.ACCNT_NM SEPARATOR ', ') AS account_names
        FROM tb_prj_contrt pc
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pc.ACCNT_NO
        WHERE pc.SALES_PRCHSS_DIV = 'P601'
        GROUP BY pc.PRJ_ID
        """,
    ):
        sales_account_by_prj[row["PRJ_ID"]] = row["account_names"] or ""

    projects = fetch_all(
        db_cfg,
        """
        SELECT
            pi.PRJ_ID,
            pi.PRJ_NM,
            pi.PRJ_STRT_DT,
            pi.PRJ_END_DT,
            org.ORG_NM AS exec_org_nm,
            acc.ACCNT_NM AS account_nm,
            pm.EMPL_NM AS pm_nm
        FROM tb_prj_info pi
        LEFT JOIN tb_organization org ON org.ORG_ID = pi.EXC_ORG_ID
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        LEFT JOIN tb_prj_inp_mp mp ON mp.PRJ_ID = pi.PRJ_ID AND mp.INP_MP_DIV_CD = %s
        LEFT JOIN tb_employee pm ON pm.EMPL_ID = mp.EMPL_ID
        ORDER BY pi.PRJ_ID
        """,
        (PM_ROLE_DIV,),
    )

    rows: list[ProjectCostRow] = []
    for project in projects:
        prj_id = project["PRJ_ID"]
        revenue = revenue_by_prj.get(prj_id, 0)
        proposal_cost = proposal_by_prj.get(prj_id, 0)
        material_cost = material_by_prj.get(prj_id, 0)
        expense_total = expense_total_by_prj.get(prj_id, 0)
        expense = expense_total - proposal_cost - material_cost
        labor_cost = labor_by_prj.get(prj_id, 0)
        outsourcing_cost = outsourcing_by_prj.get(prj_id, 0)

        general_admin_cost = round(revenue * GENERAL_ADMIN_RATE)
        sales_cost = round(revenue * SALES_COST_RATE)
        warranty_cost = round(revenue * WARRANTY_RATE)
        operating_profit = revenue - (
            proposal_cost
            + material_cost
            + labor_cost
            + expense
            + general_admin_cost
            + sales_cost
            + outsourcing_cost
        )
        final_operating_profit = operating_profit - warranty_cost

        rows.append(
            ProjectCostRow(
                prj_code=prj_id,
                prj_name=project["PRJ_NM"] or "",
                exec_org=project["exec_org_nm"] or "",
                pm_name=project["pm_nm"] or "",
                client_name=project["account_nm"] or "",
                sales_account_name=sales_account_by_prj.get(prj_id, ""),
                period=_fmt_period(project["PRJ_STRT_DT"], project["PRJ_END_DT"]),
                revenue=revenue,
                proposal_cost=proposal_cost,
                material_cost=material_cost,
                labor_cost=labor_cost,
                expense=expense,
                general_admin_cost=general_admin_cost,
                sales_cost=sales_cost,
                outsourcing_cost=outsourcing_cost,
                operating_profit=operating_profit,
                warranty_cost=warranty_cost,
                final_operating_profit=final_operating_profit,
            )
        )
    return rows
