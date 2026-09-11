import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from app.auth import AuthenticatedUser
from app.config import load_config
from app.db import check_connection
from app.single_instance import acquire_single_instance_lock
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow
from app.ui.theme import build_app_qss, current_theme


def main() -> None:
    app = QApplication(sys.argv)

    lock_server = acquire_single_instance_lock()
    if lock_server is None:
        QMessageBox.warning(
            None, "중복 실행", "유티정보 경영관리 프로그램이 이미 실행 중입니다."
        )
        sys.exit(0)

    app.setStyleSheet(build_app_qss(current_theme()))
    app_config = load_config()

    # 접속 정보(config.ini)가 잘못됐거나 DB가 내려가 있으면, 로그인 화면부터 보여주지
    # 않고 여기서 바로 안내하고 종료한다 — 로그인 시도 후에야 실패를 알게 되는 걸 막는다.
    db_error = check_connection(app_config.database)
    if db_error:
        QMessageBox.critical(
            None,
            "데이터베이스 연결 실패",
            "데이터베이스에 연결할 수 없습니다.\n"
            f"{db_error}\n\n"
            f"접속 정보: {app_config.database.host}:{app_config.database.port}\n"
            "config.ini의 접속 정보를 확인해 주세요.",
        )
        sys.exit(1)

    # "_lock_server"는 화면이 아니지만, GC로 소켓 서버가 정리돼 잠금이 풀리지 않도록
    # 다른 창들과 같은 방식(참조 유지)으로 이 dict에 함께 보관한다.
    windows: dict[str, object] = {"_lock_server": lock_server}

    def on_theme_changed(_scheme) -> None:
        app.setStyleSheet(build_app_qss(current_theme()))
        main_window = windows.get("main")
        if main_window is not None:
            main_window.apply_theme()

    QGuiApplication.styleHints().colorSchemeChanged.connect(on_theme_changed)

    def on_login_success(user: AuthenticatedUser) -> None:
        main_window = MainWindow(app_config, user)
        windows["main"] = main_window  # 참조 유지 (GC 방지)
        main_window.show()
        login_window.close()

    login_window = LoginWindow(app_config, on_login_success)
    login_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
