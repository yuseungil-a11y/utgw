from contextlib import contextmanager

import pymysql
import pymysql.cursors

from app.config import DatabaseConfig


class ReadOnlyQueryError(Exception):
    """fetch_all/fetch_one은 SELECT 조회만 허용한다. 쓰기가 필요한 화면(예: 투입인력관리)은
    아래 execute()/execute_many()를 명시적으로 사용한다."""


def _connect(cfg: DatabaseConfig) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
    )


@contextmanager
def get_connection(cfg: DatabaseConfig):
    conn = _connect(cfg)
    try:
        yield conn
    finally:
        conn.close()


def check_connection(cfg: DatabaseConfig) -> str | None:
    """DB 접속 가능 여부만 확인한다. 성공하면 None, 실패하면 오류 메시지를 반환한다.
    프로그램 시작 시 로그인 화면을 띄우기 전에 config.ini의 접속 정보가 맞는지
    미리 확인하는 용도다(연결 실패 상태로 로그인 화면부터 보여주는 걸 막기 위함)."""
    try:
        with get_connection(cfg):
            pass
    except Exception as exc:  # noqa: BLE001 - 오류 문구를 그대로 사용자에게 보여준다
        return str(exc)
    return None


def fetch_all(cfg: DatabaseConfig, query: str, params=None) -> list[dict]:
    if not query.strip().upper().startswith("SELECT"):
        raise ReadOnlyQueryError("이 애플리케이션은 조회(SELECT) 쿼리만 허용합니다.")
    with get_connection(cfg) as conn, conn.cursor() as cur:
        cur.execute(query, params or ())
        return cur.fetchall()


def fetch_one(cfg: DatabaseConfig, query: str, params=None) -> dict | None:
    rows = fetch_all(cfg, query, params)
    return rows[0] if rows else None


def execute(cfg: DatabaseConfig, query: str, params=None) -> int:
    """INSERT/UPDATE/CREATE 등 쓰기 쿼리 실행. 자동 커밋하고 영향받은 행 수를 반환한다."""
    with get_connection(cfg) as conn, conn.cursor() as cur:
        affected = cur.execute(query, params or ())
        conn.commit()
        return affected


def execute_many(cfg: DatabaseConfig, query: str, seq_of_params) -> int:
    """동일한 쓰기 쿼리를 여러 파라미터 집합에 대해 일괄 실행 후 자동 커밋한다."""
    with get_connection(cfg) as conn, conn.cursor() as cur:
        affected = cur.executemany(query, seq_of_params)
        conn.commit()
        return affected or 0
