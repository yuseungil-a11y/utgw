"""대시보드 차트용 집계 쿼리.

처음에는 tb_request_sales_prchss/tb_request_expenses로 최선 추정 집계를 했으나,
실제 운영 화면(매출매입 관리) 스크린샷과 금액을 대조해 tb_prj_sales_prchss가
정확한 원장 테이블임을 확인했다 (app/queries/sales_purchase.py 참고).
이 모듈도 같은 테이블 기준으로 다시 집계한다.

상태 판정은 STT_DIV 코드를 해석하지 않고 STMT_ISSE_DT(계산서 발행/수령일),
SALES_PRCHSS_DCSN_DT(매출/매입 확정일 - "영업확인중" 단계), SALES_PRCHSS_CNFRM_DT
(입금/지급 확인일) 세 날짜 컬럼으로 유도한다. sales_purchase.py의 _derive_status와
동일한 근거다.
"""

from dataclasses import dataclass

from app.config import DatabaseConfig
from app.db import fetch_all, fetch_one

SALES_DIV = "P601"
PURCHASE_DIV = "P602"


@dataclass(frozen=True)
class SalesStatus:
    year: int
    target: int
    actual: int


@dataclass(frozen=True)
class CashFlowStatus:
    sales_closed: int  # 매출 종결 (입금 확인 완료)
    purchase_closed: int  # 매입 종결 (지급 확인 완료)
    sales_confirming: int  # 매출 영업확인중 (확정일은 있지만 입금 미확인)
    purchase_confirming: int  # 매입 영업확인중 (확정일은 있지만 지급 미확인)
    sales_issuing: int  # 계산서 발행중 (매출, 아직 계산서 미발행)
    sales_pending: int  # 입금대기중 (매출, 계산서는 발행했지만 입금 미확인)
    purchase_receiving: int  # 계산서 수령중 (매입, 아직 계산서 미수령)
    purchase_pending: int  # 지급대기중 (매입, 계산서는 수령했지만 지급 미확인)


def get_sales_status(db_cfg: DatabaseConfig, year: int, target: int) -> SalesStatus:
    row = fetch_one(
        db_cfg,
        """
        SELECT COALESCE(SUM(sp.PRC), 0) AS actual
        FROM tb_prj_sales_prchss sp
        JOIN tb_prj_contrt pc ON sp.PRJ_ID = pc.PRJ_ID AND sp.CONTRT_CD = pc.CONTRT_CD
        WHERE pc.SALES_PRCHSS_DIV = %s AND YEAR(sp.RGST_DT) = %s
        """,
        (SALES_DIV, year),
    )
    actual = int(row["actual"]) if row else 0
    return SalesStatus(year=year, target=target, actual=actual)


def get_cash_flow_status(db_cfg: DatabaseConfig, year: int) -> CashFlowStatus:
    rows = fetch_all(
        db_cfg,
        """
        SELECT
            pc.SALES_PRCHSS_DIV AS div_code,
            COALESCE(SUM(CASE WHEN sp.SALES_PRCHSS_CNFRM_DT IS NOT NULL THEN sp.PRC ELSE 0 END), 0) AS closed_total,
            COALESCE(
                SUM(
                    CASE
                        WHEN sp.SALES_PRCHSS_CNFRM_DT IS NULL AND sp.SALES_PRCHSS_DCSN_DT IS NOT NULL
                        THEN sp.PRC ELSE 0
                    END
                ), 0
            ) AS confirming_total,
            COALESCE(
                SUM(
                    CASE
                        WHEN sp.SALES_PRCHSS_CNFRM_DT IS NULL AND sp.SALES_PRCHSS_DCSN_DT IS NULL
                            AND sp.STMT_ISSE_DT IS NOT NULL
                        THEN sp.PRC ELSE 0
                    END
                ), 0
            ) AS pending_total,
            COALESCE(SUM(CASE WHEN sp.STMT_ISSE_DT IS NULL THEN sp.PRC ELSE 0 END), 0) AS issuing_total
        FROM tb_prj_sales_prchss sp
        JOIN tb_prj_contrt pc ON sp.PRJ_ID = pc.PRJ_ID AND sp.CONTRT_CD = pc.CONTRT_CD
        WHERE YEAR(sp.RGST_DT) = %s
        GROUP BY pc.SALES_PRCHSS_DIV
        """,
        (year,),
    )
    by_div = {row["div_code"]: row for row in rows}
    sales = by_div.get(SALES_DIV)
    purchase = by_div.get(PURCHASE_DIV)

    return CashFlowStatus(
        sales_closed=int(sales["closed_total"]) if sales else 0,
        purchase_closed=int(purchase["closed_total"]) if purchase else 0,
        sales_confirming=int(sales["confirming_total"]) if sales else 0,
        purchase_confirming=int(purchase["confirming_total"]) if purchase else 0,
        sales_issuing=int(sales["issuing_total"]) if sales else 0,
        sales_pending=int(sales["pending_total"]) if sales else 0,
        purchase_receiving=int(purchase["issuing_total"]) if purchase else 0,
        purchase_pending=int(purchase["pending_total"]) if purchase else 0,
    )
