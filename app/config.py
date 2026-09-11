import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

from app.updater import DEFAULT_REPO

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_config_path() -> Path:
    """PyInstaller로 빌드된 실행파일에서는 exe와 같은 폴더에서 config.ini를 찾는다.
    (Windows에서는 exe 옆에 두는 게 더 익숙한 배포 방식이라 이렇게 통일했다.
    macOS의 .app 번들은 재빌드할 때마다 통째로 새로 만들어지므로, 빌드 스크립트가
    매번 config.ini를 다시 복사해 넣어준다.)"""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir / "config.ini"
    return PROJECT_ROOT / "config.ini"


CONFIG_PATH = _default_config_path()


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str


@dataclass(frozen=True)
class UpdateConfig:
    repo: str  # "owner/repo" 형태의 GitHub 저장소
    token: str  # 비공개 저장소용 읽기전용 PAT. 비어있으면 익명 요청(공개 저장소만 가능).


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    sales_targets: dict[int, int]
    update: UpdateConfig


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 파일이 없습니다. config.ini.example을 복사해 config.ini를 만들고 "
            "DB 접속정보와 매출목표를 채워주세요."
        )

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    db = parser["database"]
    database = DatabaseConfig(
        host=db.get("host"),
        port=db.getint("port"),
        database=db.get("database"),
        user=db.get("user"),
        password=db.get("password"),
    )

    sales_targets: dict[int, int] = {}
    if parser.has_section("sales_target"):
        for year, amount in parser.items("sales_target"):
            sales_targets[int(year)] = int(amount)

    # [update] 섹션은 선택사항이다 — 없으면 기본 저장소를 익명(토큰 없이) 상태로 둔다.
    # 비공개 저장소는 token 없이는 버전 확인이 실패하며, 그 경우 오류 메시지를 그대로
    # 사용자에게 보여준다(app/updater.py 참고).
    update_section = parser["update"] if parser.has_section("update") else {}
    update = UpdateConfig(
        repo=update_section.get("repo", DEFAULT_REPO),
        token=update_section.get("token", ""),
    )

    return AppConfig(database=database, sales_targets=sales_targets, update=update)
