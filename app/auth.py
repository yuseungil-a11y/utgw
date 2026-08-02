from dataclasses import dataclass

import bcrypt

from app.config import DatabaseConfig
from app.db import fetch_one


class AuthError(Exception):
    """로그인 실패 사유를 사용자에게 그대로 보여줄 수 있는 예외."""


@dataclass(frozen=True)
class AuthenticatedUser:
    empl_id: str
    empl_nm: str
    email: str


def login(db_cfg: DatabaseConfig, login_id: str, password: str) -> AuthenticatedUser:
    row = fetch_one(
        db_cfg,
        "SELECT EMPL_ID, EMPL_NM, EMAIL, PWD, LEAV_DT FROM tb_employee WHERE EMAIL = %s OR EMPL_ID = %s",
        (login_id, login_id),
    )
    if row is None:
        raise AuthError("존재하지 않는 계정입니다.")
    if row["LEAV_DT"] is not None:
        raise AuthError("퇴직 처리된 계정입니다.")
    if not bcrypt.checkpw(password.encode("utf-8"), row["PWD"].encode("utf-8")):
        raise AuthError("비밀번호가 일치하지 않습니다.")
    return AuthenticatedUser(empl_id=row["EMPL_ID"], empl_nm=row["EMPL_NM"], email=row["EMAIL"])
