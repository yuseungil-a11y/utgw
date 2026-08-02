import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.auth import AuthenticatedUser
from app.config import load_config
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow
from app.ui.theme import build_app_qss, current_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_app_qss(current_theme()))
    app_config = load_config()

    windows: dict[str, object] = {}

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
