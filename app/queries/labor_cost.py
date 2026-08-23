"""노무비(인월 단가) 기준 테이블 — 직급별/연도별 단가.

"프로젝트 실행원가 비교" 화면의 노무비 실적을 "1인월=160시간, 인월단가 600만원 고정"이라는
임시 계산식 대신, 적용년도 + 직급별 실제 단가로 계산하기 위해 사용자가 제공한 단가표를
그대로 옮긴 신규 테이블이다(운영 DB에 원래 없던 테이블이라 이 앱이 직접 생성/관리한다 —
tb_extms 계열과 같은 방식).

SBCTG_CD는 새 코드를 만들지 않고 기존 직급 코드 테이블
tb_sub_category(MACTG_CD='A1', tb_employee.RNK가 참조하는 것과 동일한 코드)를 그대로
참조한다. 직급명은 이 테이블에 중복 저장하지 않고 항상 tb_sub_category와 조인해서 가져온다.
"""

from dataclasses import dataclass

from app.config import DatabaseConfig
from app.db import execute, execute_many, fetch_all

RANK_MACTG = "A1"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tb_labor_cost (
    APPLY_YEAR CHAR(4) NOT NULL,
    SBCTG_CD VARCHAR(4) NOT NULL,
    LABOR_COST BIGINT UNSIGNED NOT NULL,
    CHNG_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHNG_EMPL_ID VARCHAR(20) NULL,
    PRIMARY KEY (APPLY_YEAR, SBCTG_CD)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# 사용자가 제공한 2026년 직급별 노무비(인월 단가) 초기값. tb_sub_category(MACTG_CD='A1')의
# SBCTG_CD와 1:1로 대응한다(대표이사~인턴, 연구직군 포함).
_DEFAULT_RATES_2026 = [
    ("A101", 10_000_000),  # 대표이사
    ("A102", 10_000_000),  # 의장
    ("A103", 10_000_000),  # 부의장
    ("A104", 10_000_000),  # 사장
    ("A105", 10_000_000),  # 부사장
    ("A106", 8_500_000),  # 전무
    ("A107", 7_500_000),  # 상무
    ("A108", 6_500_000),  # 이사
    ("A109", 6_000_000),  # 부장
    ("A110", 5_500_000),  # 차장
    ("A111", 4_500_000),  # 과장
    ("A112", 4_000_000),  # 대리
    ("A113", 3_500_000),  # 사원
    ("A114", 6_500_000),  # 연구위원
    ("A115", 6_000_000),  # 수석연구원
    ("A116", 5_500_000),  # 책임연구원
    ("A117", 4_500_000),  # 선임연구원
    ("A118", 4_000_000),  # 연구원
    ("A119", 3_500_000),  # 연구보
    ("A120", 3_000_000),  # 인턴
]
_DEFAULT_RATES_APPLY_YEAR = "2026"


@dataclass(frozen=True)
class LaborCostRateRow:
    apply_year: str
    sbctg_cd: str
    rank_name: str
    labor_cost: int


def ensure_table_exists(db_cfg: DatabaseConfig) -> None:
    execute(db_cfg, CREATE_TABLE_SQL)


def seed_default_rates(db_cfg: DatabaseConfig, current_empl_id: str) -> None:
    """초기 단가표가 비어있을 때만 사용자가 제공한 2026년 기본값을 채운다. 이미 값이 있으면
    아무 것도 하지 않는다(운영 중 수정한 단가를 덮어쓰지 않기 위함)."""
    existing = fetch_all(
        db_cfg,
        "SELECT 1 AS x FROM tb_labor_cost WHERE APPLY_YEAR = %s LIMIT 1",
        (_DEFAULT_RATES_APPLY_YEAR,),
    )
    if existing:
        return

    params = [
        (_DEFAULT_RATES_APPLY_YEAR, sbctg_cd, labor_cost, current_empl_id)
        for sbctg_cd, labor_cost in _DEFAULT_RATES_2026
    ]
    execute_many(
        db_cfg,
        """
        INSERT INTO tb_labor_cost (APPLY_YEAR, SBCTG_CD, LABOR_COST, CHNG_EMPL_ID)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            LABOR_COST = VALUES(LABOR_COST),
            CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
        """,
        params,
    )


def get_rate_map(db_cfg: DatabaseConfig) -> dict[tuple[str, str], int]:
    """(적용년도, SBCTG_CD) -> 노무비(인월단가) 맵."""
    rows = fetch_all(db_cfg, "SELECT APPLY_YEAR, SBCTG_CD, LABOR_COST FROM tb_labor_cost")
    return {(row["APPLY_YEAR"], row["SBCTG_CD"]): int(row["LABOR_COST"]) for row in rows}


def get_rate_rows(db_cfg: DatabaseConfig) -> list[LaborCostRateRow]:
    rows = fetch_all(
        db_cfg,
        """
        SELECT lc.APPLY_YEAR, lc.SBCTG_CD, sc.SBCTG_NM AS rank_name, lc.LABOR_COST
        FROM tb_labor_cost lc
        LEFT JOIN tb_sub_category sc ON sc.SBCTG_CD = lc.SBCTG_CD AND sc.MACTG_CD = %s
        ORDER BY lc.APPLY_YEAR DESC, lc.SBCTG_CD
        """,
        (RANK_MACTG,),
    )
    return [
        LaborCostRateRow(
            apply_year=row["APPLY_YEAR"],
            sbctg_cd=row["SBCTG_CD"],
            rank_name=row["rank_name"] or "",
            labor_cost=int(row["LABOR_COST"]),
        )
        for row in rows
    ]
