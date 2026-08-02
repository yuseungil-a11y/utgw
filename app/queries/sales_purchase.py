"""매출/매입현황 그리드 쿼리.

처음에는 tb_request_sales_prchss(전자결재 요청 원본)를 사용했으나, 실제 운영 화면
스크린샷과 금액을 대조한 결과 그 화면은 tb_prj_sales_prchss(계산서 발행/입금확정
상태를 가진 매출·매입 원장)를 쓰고 있음을 확인했다. 두 테이블 중 tb_prj_sales_prchss가
운영 화면 숫자와 정확히 일치해 이쪽으로 교체한다.

처리상태는 STT_DIV 코드값을 그대로 해석하지 않고(코드 정의 테이블이 없고, 같은 건인데도
코드값이 시점에 따라 바뀌는 것을 확인해 신뢰할 수 없음), 자기서술적인 날짜 컬럼 조합으로
유도한다:
- SALES_PRCHSS_CNFRM_DT(입금/지급 확인일)가 있으면 "종결"
- SALES_PRCHSS_DCSN_DT(매출/매입 확정일)가 있으면 "영업확인중" (매출/매입 공통)
- STMT_ISSE_DT(계산서 발행/수령일)만 있으면 "입금대기중"(매출)/"지급대기중"(매입)
- 셋 다 없으면 "계산서 발행중"(매출)/"계산서 수령중"(매입)
"""

from dataclasses import dataclass
from datetime import date

from app.config import DatabaseConfig
from app.db import fetch_all

DIV_LABELS = {"P601": "매출", "P602": "매입"}

BASE_QUERY = """
SELECT
    sp.PRJ_ID,
    sp.CONTRT_CD,
    pi.PRJ_NM,
    acc.ACCNT_NM,
    pc.SALES_PRCHSS_DIV,
    sp.SALES_PRCHSS_NM,
    sp.PRC,
    sp.STMT_ISSE_REQ_DT,
    sp.STMT_ISSE_DT,
    sp.SALES_PRCHSS_DCSN_DT,
    sp.SALES_PRCHSS_CNFRM_DT,
    sp.RGST_DT
FROM tb_prj_sales_prchss sp
JOIN tb_prj_contrt pc ON sp.PRJ_ID = pc.PRJ_ID AND sp.CONTRT_CD = pc.CONTRT_CD
JOIN tb_prj_info pi ON sp.PRJ_ID = pi.PRJ_ID
LEFT JOIN tb_account acc ON pi.ACCNT_NO = acc.ACCNT_NO
{where}
ORDER BY sp.RGST_DT DESC, sp.PRJ_ID, sp.CONTRT_CD
"""

COLUMNS = ["코드", "계약명", "계약처", "구분", "항목", "요청일자", "등록일자", "처리상태", "금액"]


@dataclass(frozen=True)
class SalesPurchaseRow:
    code: str
    contract_name: str
    account_name: str
    division: str
    item_name: str
    request_date: str
    register_date: str
    status: str
    amount: int

    def as_tuple(self) -> tuple:
        return (
            self.code,
            self.contract_name,
            self.account_name,
            self.division,
            self.item_name,
            self.request_date,
            self.register_date,
            self.status,
            self.amount,
        )


def _fmt_date(value) -> str:
    return value.isoformat() if value else ""


def _derive_status(division: str, issue_dt, decision_dt, confirm_dt) -> str:
    if confirm_dt is not None:
        return "종결"
    if decision_dt is not None:
        return "영업확인중"
    if issue_dt is not None:
        return "입금대기중" if division == "매출" else "지급대기중"
    return "계산서 발행중" if division == "매출" else "계산서 수령중"


def get_sales_purchase_rows(
    db_cfg: DatabaseConfig,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[SalesPurchaseRow]:
    """등록일자(RGST_DT) 기준으로 date_from ~ date_to 구간의 매출/매입 내역을 조회한다."""
    where_clauses = []
    params: list = []
    if date_from is not None:
        where_clauses.append("sp.RGST_DT >= %s")
        params.append(date_from)
    if date_to is not None:
        where_clauses.append("sp.RGST_DT <= %s")
        params.append(date_to)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = BASE_QUERY.format(where=where_sql)

    records = fetch_all(db_cfg, query, tuple(params))
    rows: list[SalesPurchaseRow] = []
    for record in records:
        division = DIV_LABELS.get(record["SALES_PRCHSS_DIV"], record["SALES_PRCHSS_DIV"])
        rows.append(
            SalesPurchaseRow(
                code=f"{record['PRJ_ID']}/{record['CONTRT_CD']}",
                contract_name=record["PRJ_NM"] or "",
                account_name=record["ACCNT_NM"] or "",
                division=division,
                item_name=record["SALES_PRCHSS_NM"] or "",
                request_date=_fmt_date(record["STMT_ISSE_REQ_DT"]),
                register_date=_fmt_date(record["RGST_DT"]),
                status=_derive_status(
                    division,
                    record["STMT_ISSE_DT"],
                    record["SALES_PRCHSS_DCSN_DT"],
                    record["SALES_PRCHSS_CNFRM_DT"],
                ),
                amount=int(record["PRC"]),
            )
        )
    return rows
