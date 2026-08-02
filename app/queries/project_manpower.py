"""한국도로공사 투입인력관리 - 직원 x 프로젝트 매트릭스 조회/편집.

레이아웃은 사용자가 제공한 엑셀(`한국도로공사 프로젝트 현황_2026.xlsx`,
시트 `도공_프로젝트 투입 현황`)을 참조했다: 직원별 행 + 프로젝트별로 반복되는
5개 컬럼(참여/역할/상주/비상주/비고) 블록의 매트릭스.

이 화면이 이 앱에서 처음으로 쓰기(INSERT/UPDATE)가 필요한 화면이라, 신규 테이블
tb_extms(PRJ_ID, EMPL_ID 복합키)를 만들어 참여 정보를 저장한다. "이 화면에 표시되는
프로젝트 목록" = tb_extms에 이미 행이 있는 PRJ_ID의 DISTINCT 집합이다.

코드값 출처(tb_sub_category에서 확인):
- 기술등급: 처음엔 tb_technology_grade를 참조했으나, 사용자 요청으로 DB 참조를 끊고
  이 화면에서 직접 드롭다운으로 선택/저장하도록 변경했다. 선택값은 신규 테이블
  tb_extms_empl(EMPL_ID 단일키)에 저장하고, 드롭다운 목록은 tb_sub_category
  (MACTG_CD='A4': 초급기능사~기술사)를 그대로 재사용한다.
- 직급: tb_employee.RNK -> tb_sub_category(MACTG_CD='A1')
- 부서: tb_employee.ORG_ID -> tb_organization
- 역할 드롭다운: tb_sub_category(MACTG_CD='P2')
"""

from dataclasses import dataclass, field
from datetime import date

from app.config import DatabaseConfig
from app.db import execute, execute_many, fetch_all, fetch_one

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tb_extms (
    PRJ_ID VARCHAR(20) NOT NULL,
    EMPL_ID VARCHAR(20) NOT NULL,
    PRTCPT_YN CHAR(1) NOT NULL DEFAULT 'N',
    ROLE_DIV VARCHAR(4) NULL,
    RESDNG_YN CHAR(1) NOT NULL DEFAULT 'N',
    NON_RESDNG_YN CHAR(1) NOT NULL DEFAULT 'N',
    RMRK VARCHAR(500) NULL,
    RGST_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    RGST_EMPL_ID VARCHAR(20) NOT NULL,
    CHNG_DTTM DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHNG_EMPL_ID VARCHAR(20) NOT NULL,
    PRIMARY KEY (PRJ_ID, EMPL_ID)
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


def ensure_table_exists(db_cfg: DatabaseConfig) -> None:
    execute(db_cfg, CREATE_TABLE_SQL)
    execute(db_cfg, CREATE_EMPL_TABLE_SQL)


@dataclass(frozen=True)
class ProjectMeta:
    prj_id: str
    prj_name: str
    client_name: str
    start_date: str
    end_date: str
    total_days: int


@dataclass(frozen=True)
class ProjectCell:
    participate: bool = False
    role_div: str | None = None
    role_name: str = ""
    resident: bool = False
    non_resident: bool = False
    remark: str = ""


@dataclass(frozen=True)
class EmployeeRow:
    seq: int
    empl_id: str
    name: str
    join_date: str
    dept: str
    position: str
    grade_external_div: str | None
    grade_external: str
    grade_sw_div: str | None
    grade_sw: str
    participates: bool
    is_pm_or_pl: bool
    cells: dict[str, ProjectCell]


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
        FROM (SELECT DISTINCT PRJ_ID FROM tb_extms) t
        JOIN tb_prj_info pi ON pi.PRJ_ID = t.PRJ_ID
        LEFT JOIN tb_account acc ON acc.ACCNT_NO = pi.ACCNT_NO
        ORDER BY pi.PRJ_ID
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
    """'프로젝트 추가' 대화상자용 검색. (PRJ_ID, PRJ_NM, 발주기관명) 목록을 반환한다."""
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


def add_project(db_cfg: DatabaseConfig, prj_id: str, current_empl_id: str) -> None:
    """선택한 프로젝트를 전 재직 직원에 대해 기본값(참여 N)으로 일괄 추가한다."""
    employees = fetch_all(db_cfg, "SELECT EMPL_ID FROM tb_employee WHERE LEAV_DT IS NULL")
    if not employees:
        return
    params = [(prj_id, row["EMPL_ID"], current_empl_id, current_empl_id) for row in employees]
    execute_many(
        db_cfg,
        """
        INSERT IGNORE INTO tb_extms (PRJ_ID, EMPL_ID, RGST_EMPL_ID, CHNG_EMPL_ID)
        VALUES (%s, %s, %s, %s)
        """,
        params,
    )


def remove_project(db_cfg: DatabaseConfig, prj_id: str) -> None:
    """투입인력관리에서 프로젝트를 제거한다. 해당 프로젝트의 tb_extms 행을 전부 지운다
    (프로젝트 자체나 tb_prj_info 등 다른 데이터에는 영향 없음 - 기간 종료 등으로 이
    화면에서 더 이상 추적할 필요가 없어진 프로젝트를 정리하는 용도)."""
    execute(db_cfg, "DELETE FROM tb_extms WHERE PRJ_ID = %s", (prj_id,))


def get_employee_matrix(
    db_cfg: DatabaseConfig, project_ids: list[str]
) -> list[EmployeeRow]:
    employees = fetch_all(
        db_cfg,
        """
        SELECT
            e.EMPL_ID,
            e.EMPL_NM,
            e.JOIN_DT,
            org.ORG_NM,
            pos.SBCTG_NM AS position_nm
        FROM tb_employee e
        LEFT JOIN tb_organization org ON org.ORG_ID = e.ORG_ID
        LEFT JOIN tb_sub_category pos ON pos.SBCTG_CD = e.RNK AND pos.MACTG_CD = %s
        WHERE e.LEAV_DT IS NULL
        ORDER BY e.JOIN_DT, e.EMPL_ID
        """,
        (POSITION_MACTG,),
    )

    grade_names = dict(get_grade_options(db_cfg))
    grades_by_empl: dict[str, tuple[str | None, str | None]] = {}
    grade_rows = fetch_all(
        db_cfg, "SELECT EMPL_ID, GRADE_EXTERNAL_DIV, GRADE_SW_DIV FROM tb_extms_empl"
    )
    for row in grade_rows:
        grades_by_empl[row["EMPL_ID"]] = (row["GRADE_EXTERNAL_DIV"], row["GRADE_SW_DIV"])

    role_names = dict(get_role_options(db_cfg))

    cells_by_empl: dict[str, dict[str, ProjectCell]] = {}
    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        ext_rows = fetch_all(
            db_cfg,
            f"""
            SELECT PRJ_ID, EMPL_ID, PRTCPT_YN, ROLE_DIV, RESDNG_YN, NON_RESDNG_YN, RMRK
            FROM tb_extms
            WHERE PRJ_ID IN ({placeholders})
            """,
            tuple(project_ids),
        )
        for row in ext_rows:
            cell = ProjectCell(
                participate=row["PRTCPT_YN"] == "Y",
                role_div=row["ROLE_DIV"],
                role_name=role_names.get(row["ROLE_DIV"], "") if row["ROLE_DIV"] else "",
                resident=row["RESDNG_YN"] == "Y",
                non_resident=row["NON_RESDNG_YN"] == "Y",
                remark=row["RMRK"] or "",
            )
            cells_by_empl.setdefault(row["EMPL_ID"], {})[row["PRJ_ID"]] = cell

    rows: list[EmployeeRow] = []
    for seq, employee in enumerate(employees, start=1):
        empl_id = employee["EMPL_ID"]
        grade_external_div, grade_sw_div = grades_by_empl.get(empl_id, (None, None))

        cells = cells_by_empl.get(empl_id, {})
        participates = any(cell.participate for cell in cells.values())
        is_pm_or_pl = any(
            ("PM" in cell.role_name or "PL" in cell.role_name) for cell in cells.values()
        )

        rows.append(
            EmployeeRow(
                seq=seq,
                empl_id=empl_id,
                name=employee["EMPL_NM"] or "",
                join_date=_fmt_date(employee["JOIN_DT"]),
                dept=employee["ORG_NM"] or "",
                position=employee["position_nm"] or "",
                grade_external_div=grade_external_div,
                grade_external=grade_names.get(grade_external_div, "") if grade_external_div else "",
                grade_sw_div=grade_sw_div,
                grade_sw=grade_names.get(grade_sw_div, "") if grade_sw_div else "",
                participates=participates,
                is_pm_or_pl=is_pm_or_pl,
                cells=cells,
            )
        )
    return rows


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


def save_matrix(
    db_cfg: DatabaseConfig,
    cell_updates: list[tuple[str, str, ProjectCell]],
    current_empl_id: str,
) -> None:
    """(PRJ_ID, EMPL_ID, ProjectCell) 목록을 upsert한다."""
    if not cell_updates:
        return
    params = [
        (
            prj_id,
            empl_id,
            "Y" if cell.participate else "N",
            cell.role_div,
            "Y" if cell.resident else "N",
            "Y" if cell.non_resident else "N",
            cell.remark or None,
            current_empl_id,
            current_empl_id,
        )
        for prj_id, empl_id, cell in cell_updates
    ]
    execute_many(
        db_cfg,
        """
        INSERT INTO tb_extms
            (PRJ_ID, EMPL_ID, PRTCPT_YN, ROLE_DIV, RESDNG_YN, NON_RESDNG_YN, RMRK,
             RGST_EMPL_ID, CHNG_EMPL_ID)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            PRTCPT_YN = VALUES(PRTCPT_YN),
            ROLE_DIV = VALUES(ROLE_DIV),
            RESDNG_YN = VALUES(RESDNG_YN),
            NON_RESDNG_YN = VALUES(NON_RESDNG_YN),
            RMRK = VALUES(RMRK),
            CHNG_EMPL_ID = VALUES(CHNG_EMPL_ID)
        """,
        params,
    )
