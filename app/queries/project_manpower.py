"""한국도로공사 투입인력관리 - 참여 목록(프로젝트 x 직원) 조회/편집.

레이아웃은 사용자가 제공한 엑셀(`한국도로공사 프로젝트별 인력 투입현황_v1.0.xlsx`,
시트 `01.2026년_프로젝트별 투입현황`)을 그대로 따른다: 한 행 = 한 직원의 한 프로젝트
참여 건. 월별 투입률(%, 5% 단위)을 직접 입력하고, 투입률(합계)은 그 평균으로
화면에서 자동 계산한다.

이 화면이 이 앱에서 처음으로 쓰기(INSERT/UPDATE)가 필요한 화면이라, 신규 테이블
tb_extms(PRJ_ID, EMPL_ID 복합키)를 만들어 참여 정보를 저장한다. 월별 투입률은 별도
테이블 tb_extms_month(PRJ_ID, EMPL_ID, YYYYMM 복합키)에 저장한다. "이 화면에 표시되는
프로젝트 목록" = tb_extms에 이미 행이 있는 PRJ_ID의 DISTINCT 집합이다.

코드값 출처(tb_sub_category에서 확인):
- 기술등급: 처음엔 tb_technology_grade를 참조했으나, 사용자 요청으로 DB 참조를 끊고
  별도 화면(기술등급 관리)에서 직접 드롭다운으로 선택/저장하도록 변경했다. 선택값은
  신규 테이블 tb_extms_empl(EMPL_ID 단일키)에 저장하고, 드롭다운 목록은
  tb_sub_category(MACTG_CD='A4': 초급기능사~기술사)를 그대로 재사용한다.
- 직급: tb_employee.RNK -> tb_sub_category(MACTG_CD='A1')
- 부서: tb_employee.ORG_ID -> tb_organization
- 역할 드롭다운: tb_sub_category(MACTG_CD='P2')
- 상주/비상주: 첨부 엑셀에는 한 행에 하나의 값만 있어 코드 테이블 없이 '상주'/'비상주'
  텍스트를 그대로 저장한다(tb_extms.RESDNG_DIV).
"""

from dataclasses import dataclass

from app.config import DatabaseConfig
from app.db import execute, execute_many, fetch_all, fetch_one

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tb_extms (
    PRJ_ID VARCHAR(20) NOT NULL,
    EMPL_ID VARCHAR(20) NOT NULL,
    PRTCPT_YN CHAR(1) NOT NULL DEFAULT 'N',
    ROLE_DIV VARCHAR(4) NULL,
    RESDNG_DIV VARCHAR(10) NULL,
    RMRK VARCHAR(500) NULL,
    RGST_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    RGST_EMPL_ID VARCHAR(20) NOT NULL,
    CHNG_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHNG_EMPL_ID VARCHAR(20) NOT NULL,
    PRIMARY KEY (PRJ_ID, EMPL_ID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

CREATE_MONTH_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tb_extms_month (
    PRJ_ID VARCHAR(20) NOT NULL,
    EMPL_ID VARCHAR(20) NOT NULL,
    YYYYMM CHAR(6) NOT NULL,
    INPUT_RATE TINYINT UNSIGNED NOT NULL DEFAULT 0,
    CHNG_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHNG_EMPL_ID VARCHAR(20) NOT NULL,
    PRIMARY KEY (PRJ_ID, EMPL_ID, YYYYMM)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

CREATE_EMPL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tb_extms_empl (
    EMPL_ID VARCHAR(20) NOT NULL,
    GRADE_EXTERNAL_DIV VARCHAR(4) NULL,
    GRADE_SW_DIV VARCHAR(4) NULL,
    CHNG_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHNG_EMPL_ID VARCHAR(20) NOT NULL,
    PRIMARY KEY (EMPL_ID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

POSITION_MACTG = "A1"
ROLE_MACTG = "P2"
GRADE_MACTG = "A4"


def _migrate_resdng_columns(db_cfg: DatabaseConfig) -> None:
    """예전 스키마(RESDNG_YN/NON_RESDNG_YN 체크박스 2개)로 이미 만들어져 있던 운영
    tb_extms 테이블을 새 스키마(RESDNG_DIV 단일 선택)로 1회 마이그레이션한다.
    RESDNG_YN 컬럼이 더 이상 없으면(신규 설치 또는 마이그레이션 완료) 아무 것도 하지
    않는다."""
    row = fetch_one(
        db_cfg,
        """
        SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_extms' AND COLUMN_NAME = 'RESDNG_YN'
        """,
    )
    if not row or not row["cnt"]:
        return

    execute(db_cfg, "ALTER TABLE tb_extms ADD COLUMN RESDNG_DIV VARCHAR(10) NULL AFTER NON_RESDNG_YN")
    execute(
        db_cfg,
        """
        UPDATE tb_extms
        SET RESDNG_DIV = CASE
            WHEN RESDNG_YN = 'Y' THEN '상주'
            WHEN NON_RESDNG_YN = 'Y' THEN '비상주'
            ELSE NULL
        END
        """,
    )
    execute(db_cfg, "ALTER TABLE tb_extms DROP COLUMN RESDNG_YN")
    execute(db_cfg, "ALTER TABLE tb_extms DROP COLUMN NON_RESDNG_YN")


def ensure_table_exists(db_cfg: DatabaseConfig) -> None:
    execute(db_cfg, CREATE_TABLE_SQL)
    execute(db_cfg, CREATE_MONTH_TABLE_SQL)
    execute(db_cfg, CREATE_EMPL_TABLE_SQL)
    _migrate_resdng_columns(db_cfg)


@dataclass(frozen=True)
class ProjectMeta:
    prj_id: str
    prj_name: str
    client_name: str
    start_date: str
    end_date: str
    total_days: int


@dataclass(frozen=True)
class EmployeeBasic:
    empl_id: str
    name: str
    join_date: str
    dept: str
    position: str


@dataclass(frozen=True)
class ParticipationRow:
    prj_id: str
    empl_id: str
    prj_name: str
    client_name: str
    start_date: str
    end_date: str
    empl_name: str
    role_div: str | None
    role_name: str
    resdng_div: str | None
    remark: str
    monthly_rates: dict[str, int]  # YYYYMM -> 0~100(%)


def _fmt_date(value) -> str:
    return value.isoformat() if value else ""


def get_role_options(db_cfg: DatabaseConfig) -> list[tuple[str, str]]:
    rows = fetch_all(
        db_cfg,
        "SELECT SBCTG_CD, SBCTG_NM FROM tb_sub_category WHERE MACTG_CD = %s ORDER BY SBCTG_CD",
        (ROLE_MACTG,),
    )
    return [(row["SBCTG_CD"], row["SBCTG_NM"]) for row in rows]


def get_grade_options(db_cfg: DatabaseConfig) -> list[tuple[str, str]]:
    """기술등급 드롭다운 목록 (초급기능사~기술사). 대외/제안서용, S/W자격증용 둘 다 이 목록을 쓴다."""
    rows = fetch_all(
        db_cfg,
        "SELECT SBCTG_CD, SBCTG_NM FROM tb_sub_category WHERE MACTG_CD = %s ORDER BY SBCTG_CD",
        (GRADE_MACTG,),
    )
    return [(row["SBCTG_CD"], row["SBCTG_NM"]) for row in rows]


def get_tracked_projects(db_cfg: DatabaseConfig) -> list[ProjectMeta]:
    rows = fetch_all(
        db_cfg,
        """
        SELECT
            pi.PRJ_ID,
            pi.PRJ_NM,
            acc.ACCNT_NM,
            pi.PRJ_STRT_DT,
            pi.PRJ_END_DT,
            DATEDIFF(pi.PRJ_END_DT, pi.PRJ_STRT_DT) + 1 AS total_days
        FROM (SELECT DISTINCT PRJ_ID FROM tb_extms WHERE PRTCPT_YN = 'Y') t
        JOIN tb_prj_info pi ON pi.PRJ_ID = t.PRJ_ID
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        ORDER BY pi.PRJ_STRT_DT, pi.PRJ_ID
        """,
    )
    return [
        ProjectMeta(
            prj_id=row["PRJ_ID"],
            prj_name=row["PRJ_NM"] or "",
            client_name=row["ACCNT_NM"] or "",
            start_date=_fmt_date(row["PRJ_STRT_DT"]),
            end_date=_fmt_date(row["PRJ_END_DT"]),
            total_days=int(row["total_days"]) if row["total_days"] is not None else 0,
        )
        for row in rows
    ]


def search_projects(db_cfg: DatabaseConfig, keyword: str) -> list[tuple[str, str, str]]:
    """'참여자 추가' 대화상자용 검색. (PRJ_ID, PRJ_NM, 발주기관명) 목록을 반환한다."""
    like = f"%{keyword}%"
    rows = fetch_all(
        db_cfg,
        """
        SELECT pi.PRJ_ID, pi.PRJ_NM, acc.ACCNT_NM
        FROM tb_prj_info pi
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        WHERE pi.PRJ_NM LIKE %s OR pi.PRJ_ID LIKE %s OR acc.ACCNT_NM LIKE %s
        ORDER BY (acc.ACCNT_NM LIKE '%%한국도로공사%%') DESC, pi.PRJ_ID
        LIMIT 50
        """,
        (like, like, like),
    )
    return [(row["PRJ_ID"], row["PRJ_NM"] or "", row["ACCNT_NM"] or "") for row in rows]


def search_employees(db_cfg: DatabaseConfig, keyword: str) -> list[tuple[str, str, str]]:
    """'참여자 추가' 대화상자용 검색. (EMPL_ID, 성명, 부서명) 목록을 반환한다."""
    like = f"%{keyword}%"
    rows = fetch_all(
        db_cfg,
        """
        SELECT e.EMPL_ID, e.EMPL_NM, org.ORG_NM
        FROM tb_employee e
        LEFT JOIN tb_organization org ON org.ORG_ID = e.ORG_ID
        WHERE e.LEAV_DT IS NULL AND (e.EMPL_NM LIKE %s OR e.EMPL_ID LIKE %s)
        ORDER BY e.JOIN_DT, e.EMPL_ID
        LIMIT 50
        """,
        (like, like),
    )
    return [(row["EMPL_ID"], row["EMPL_NM"] or "", row["ORG_NM"] or "") for row in rows]


def get_active_employees(db_cfg: DatabaseConfig) -> list[EmployeeBasic]:
    rows = fetch_all(
        db_cfg,
        """
        SELECT e.EMPL_ID, e.EMPL_NM, e.JOIN_DT, org.ORG_NM, pos.SBCTG_NM AS position_nm
        FROM tb_employee e
        LEFT JOIN tb_organization org ON org.ORG_ID = e.ORG_ID
        LEFT JOIN tb_sub_category pos ON pos.SBCTG_CD = e.RNK AND pos.MACTG_CD = %s
        WHERE e.LEAV_DT IS NULL
        ORDER BY e.JOIN_DT, e.EMPL_ID
        """,
        (POSITION_MACTG,),
    )
    return [
        EmployeeBasic(
            empl_id=row["EMPL_ID"],
            name=row["EMPL_NM"] or "",
            join_date=_fmt_date(row["JOIN_DT"]),
            dept=row["ORG_NM"] or "",
            position=row["position_nm"] or "",
        )
        for row in rows
    ]


def get_employee_grades(db_cfg: DatabaseConfig) -> dict[str, tuple[str | None, str | None]]:
    rows = fetch_all(db_cfg, "SELECT EMPL_ID, GRADE_EXTERNAL_DIV, GRADE_SW_DIV FROM tb_extms_empl")
    return {row["EMPL_ID"]: (row["GRADE_EXTERNAL_DIV"], row["GRADE_SW_DIV"]) for row in rows}


def save_employee_grades(
    db_cfg: DatabaseConfig,
    grade_updates: list[tuple[str, str | None, str | None]],
    current_empl_id: str,
) -> None:
    """(EMPL_ID, 대외등급코드, SW등급코드) 목록을 upsert한다."""
    if not grade_updates:
        return
    params = [
        (empl_id, grade_external_div, grade_sw_div, current_empl_id)
        for empl_id, grade_external_div, grade_sw_div in grade_updates
    ]
    execute_many(
        db_cfg,
        """
        INSERT INTO tb_extms_empl (EMPL_ID, GRADE_EXTERNAL_DIV, GRADE_SW_DIV, CHNG_EMPL_ID)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            GRADE_EXTERNAL_DIV = VALUES(GRADE_EXTERNAL_DIV),
            GRADE_SW_DIV = VALUES(GRADE_SW_DIV),
            CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
        """,
        params,
    )


def get_participation_rows(
    db_cfg: DatabaseConfig, start_year: int, start_month: int, end_year: int, end_month: int
) -> list[ParticipationRow]:
    """프로젝트 시작일 순으로 정렬된 참여 목록(한 행 = 직원 1명의 프로젝트 1건 참여).
    같은 프로젝트에 속한 참여자들은 연속으로 묶여서 나온다(첨부 엑셀 시트01과 동일한
    정렬)."""
    role_names = dict(get_role_options(db_cfg))

    rows = fetch_all(
        db_cfg,
        """
        SELECT
            t.PRJ_ID, t.EMPL_ID, t.ROLE_DIV, t.RESDNG_DIV, t.RMRK,
            pi.PRJ_NM, pi.PRJ_STRT_DT, pi.PRJ_END_DT,
            acc.ACCNT_NM,
            e.EMPL_NM
        FROM tb_extms t
        JOIN tb_prj_info pi ON pi.PRJ_ID = t.PRJ_ID
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        JOIN tb_employee e ON e.EMPL_ID = t.EMPL_ID
        WHERE t.PRTCPT_YN = 'Y'
        ORDER BY pi.PRJ_STRT_DT, pi.PRJ_ID, e.JOIN_DT, e.EMPL_ID
        """,
    )

    month_rows = fetch_all(
        db_cfg,
        """
        SELECT PRJ_ID, EMPL_ID, YYYYMM, INPUT_RATE
        FROM tb_extms_month
        WHERE YYYYMM BETWEEN %s AND %s
        """,
        (f"{start_year:04d}{start_month:02d}", f"{end_year:04d}{end_month:02d}"),
    )
    rates_by_key: dict[tuple[str, str], dict[str, int]] = {}
    for row in month_rows:
        rates_by_key.setdefault((row["PRJ_ID"], row["EMPL_ID"]), {})[row["YYYYMM"]] = int(
            row["INPUT_RATE"]
        )

    result: list[ParticipationRow] = []
    for row in rows:
        result.append(
            ParticipationRow(
                prj_id=row["PRJ_ID"],
                empl_id=row["EMPL_ID"],
                prj_name=row["PRJ_NM"] or "",
                client_name=row["ACCNT_NM"] or "",
                start_date=_fmt_date(row["PRJ_STRT_DT"]),
                end_date=_fmt_date(row["PRJ_END_DT"]),
                empl_name=row["EMPL_NM"] or "",
                role_div=row["ROLE_DIV"],
                role_name=role_names.get(row["ROLE_DIV"], "") if row["ROLE_DIV"] else "",
                resdng_div=row["RESDNG_DIV"],
                remark=row["RMRK"] or "",
                monthly_rates=rates_by_key.get((row["PRJ_ID"], row["EMPL_ID"]), {}),
            )
        )
    return result


def participation_exists(db_cfg: DatabaseConfig, prj_id: str, empl_id: str) -> bool:
    row = fetch_one(
        db_cfg,
        "SELECT 1 AS x FROM tb_extms WHERE PRJ_ID = %s AND EMPL_ID = %s AND PRTCPT_YN = 'Y'",
        (prj_id, empl_id),
    )
    return row is not None


def add_participant(db_cfg: DatabaseConfig, prj_id: str, empl_id: str, current_empl_id: str) -> None:
    """(PRJ_ID, EMPL_ID) 행이 이미 있으면(과거 매트릭스 보기가 기본값으로 미리 깔아둔
    미참여 행 등) 참여로 승격시키고, 없으면 새로 만든다."""
    execute(
        db_cfg,
        """
        INSERT INTO tb_extms (PRJ_ID, EMPL_ID, PRTCPT_YN, RGST_EMPL_ID, CHNG_EMPL_ID)
        VALUES (%s, %s, 'Y', %s, %s)
        ON DUPLICATE KEY UPDATE
            PRTCPT_YN = 'Y',
            CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
        """,
        (prj_id, empl_id, current_empl_id, current_empl_id),
    )


def remove_participant(db_cfg: DatabaseConfig, prj_id: str, empl_id: str) -> None:
    """참여 정보와 그 직원의 해당 프로젝트 월별 투입률을 함께 삭제한다."""
    execute(db_cfg, "DELETE FROM tb_extms_month WHERE PRJ_ID = %s AND EMPL_ID = %s", (prj_id, empl_id))
    execute(db_cfg, "DELETE FROM tb_extms WHERE PRJ_ID = %s AND EMPL_ID = %s", (prj_id, empl_id))


def save_participation_rows(
    db_cfg: DatabaseConfig,
    updates: list[tuple[str, str, str | None, str | None, str, dict[str, int]]],
    current_empl_id: str,
) -> None:
    """updates: (PRJ_ID, EMPL_ID, 역할코드, 상주구분, 비고, {YYYYMM: 0~100}) 목록을 upsert한다."""
    if not updates:
        return

    extms_params = [
        (prj_id, empl_id, role_div, resdng_div, remark or None, current_empl_id, current_empl_id)
        for prj_id, empl_id, role_div, resdng_div, remark, _monthly in updates
    ]
    execute_many(
        db_cfg,
        """
        INSERT INTO tb_extms
            (PRJ_ID, EMPL_ID, PRTCPT_YN, ROLE_DIV, RESDNG_DIV, RMRK, RGST_EMPL_ID, CHNG_EMPL_ID)
        VALUES (%s, %s, 'Y', %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            PRTCPT_YN = 'Y',
            ROLE_DIV = VALUES(ROLE_DIV),
            RESDNG_DIV = VALUES(RESDNG_DIV),
            RMRK = VALUES(RMRK),
            CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
        """,
        extms_params,
    )

    month_params = [
        (prj_id, empl_id, yyyymm, percent, current_empl_id)
        for prj_id, empl_id, _role_div, _resdng_div, _remark, monthly in updates
        for yyyymm, percent in monthly.items()
    ]
    if month_params:
        execute_many(
            db_cfg,
            """
            INSERT INTO tb_extms_month (PRJ_ID, EMPL_ID, YYYYMM, INPUT_RATE, CHNG_EMPL_ID)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                INPUT_RATE = VALUES(INPUT_RATE),
                CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
            """,
            month_params,
        )
