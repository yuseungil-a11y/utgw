from typing import Callable

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth import AuthenticatedUser, AuthError, login
from app.config import AppConfig

SETTINGS_ORG = "UTGW"
SETTINGS_APP = "경영관리프로그램"


class LoginWindow(QWidget):
    def __init__(self, app_config: AppConfig, on_success: Callable[[AuthenticatedUser], None]):
        super().__init__()
        self._config = app_config
        self._on_success = on_success
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        self.setWindowTitle("유티정보 경영관리 그룹웨어 로그인")
        self.setFixedSize(420, 460)

        title = QLabel("유티정보 경영관리 그룹웨어")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setProperty("role", "title")

        subtitle = QLabel("로그인")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setProperty("role", "secondary")

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("아이디 또는 이메일을 입력해 주세요")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("비밀번호를 입력해 주세요.")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._attempt_login)

        self.remember_checkbox = QCheckBox("아이디 저장")

        login_button = QPushButton("로그인")
        login_button.setDefault(True)
        login_button.setMinimumHeight(36)
        login_button.clicked.connect(self._attempt_login)

        id_label = QLabel("아이디")
        id_label.setProperty("role", "secondary")
        pw_label = QLabel("비밀번호")
        pw_label.setProperty("role", "secondary")

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(28, 28, 28, 24)
        card_layout.setSpacing(10)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(12)
        card_layout.addWidget(id_label)
        card_layout.addWidget(self.email_input)
        card_layout.addSpacing(4)
        card_layout.addWidget(pw_label)
        card_layout.addWidget(self.password_input)
        card_layout.addWidget(self.remember_checkbox)
        card_layout.addSpacing(8)
        card_layout.addWidget(login_button)

        card = QWidget()
        card.setProperty("role", "card")
        card.setFixedWidth(340)
        card.setLayout(card_layout)

        notice = QLabel(
            "※ 본 시스템은 인가된 사용자만 사용할 수 있으며\n"
            "불법 사용시에는 법적 제재를 받을 수 있습니다."
        )
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setProperty("role", "secondary")
        notice.setWordWrap(True)

        card_row = QHBoxLayout()
        card_row.addStretch()
        card_row.addWidget(card)
        card_row.addStretch()

        outer = QVBoxLayout()
        outer.addStretch()
        outer.addLayout(card_row)
        outer.addSpacing(16)
        outer.addWidget(notice)
        outer.addStretch()
        self.setLayout(outer)

        self._load_saved_email()

    def _load_saved_email(self) -> None:
        saved_email = self._settings.value("saved_email", "")
        if saved_email:
            self.email_input.setText(saved_email)
            self.remember_checkbox.setChecked(True)
            self.password_input.setFocus()

    def _attempt_login(self) -> None:
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(self, "로그인", "아이디와 비밀번호를 입력해 주세요.")
            return

        try:
            user = login(self._config.database, email, password)
        except AuthError as exc:
            QMessageBox.critical(self, "로그인 실패", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - DB 연결 실패 등을 사용자에게 그대로 안내
            QMessageBox.critical(self, "연결 오류", f"DB 연결에 실패했습니다.\n{exc}")
            return

        if self.remember_checkbox.isChecked():
            self._settings.setValue("saved_email", email)
        else:
            self._settings.remove("saved_email")

        self._on_success(user)
