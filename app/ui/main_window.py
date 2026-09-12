from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.auth import AuthenticatedUser
from app.config import AppConfig
from app.ui.dashboard_view import DashboardView
from app.ui.menu_tree import MENU_TREE
from app.ui.project_cost_dialog import ProjectCostDialog
from app.ui.project_headcount_dialog import ProjectHeadcountDialog
from app.ui.project_input_mm_dialog import ProjectInputMmDialog
from app.ui.project_manpower_dialog import ProjectManpowerDialog
from app.ui.sales_purchase_dialog import SalesPurchaseDialog
from app.ui.theme import POPUP_HEIGHT, POPUP_WIDTH, build_menu_tree_qss, current_theme
from app.ui.update_dialog import UpdateDialog
from app.updater import ReleaseInfo, get_latest_release, is_newer
from app.version import APP_VERSION

CONTENT_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
UPDATE_CHECK_INTERVAL_MS = 60_000  # 1분마다 백그라운드로 새 버전이 있는지 확인


class _UpdateCheckWorker(QObject):
    """상단바 배너용 백그라운드 버전 확인. 실패(네트워크 없음 등)는 조용히 무시한다 —
    사용자가 직접 "프로그램 업데이트" 메뉴에서 확인하면 그때는 원인을 보여준다."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, repo: str, token: str):
        super().__init__()
        self._repo = repo
        self._token = token

    def run(self) -> None:
        try:
            info = get_latest_release(self._repo, self._token)
        except Exception as exc:  # noqa: BLE001 - 백그라운드 자동 체크는 실패를 조용히 무시
            self.error.emit(str(exc))
            return
        self.finished.emit(info)


class MainWindow(QMainWindow):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser):
        super().__init__()
        self._config = app_config
        self._user = user

        self.setWindowTitle("유티정보 그룹웨어 경영관리 프로그램")
        # 팝업 화면들과 동일한 크기(FullHD 80%, 16:9 와이드)로 맞춰서 처음 뜰 때부터
        # 가로로 넉넉하게 열리게 한다 — 기존 1200x800은 좁아서 대시보드 차트 x축
        # 라벨이 "2026..."처럼 잘려 보였다.
        self.resize(POPUP_WIDTH, POPUP_HEIGHT)

        self._dashboard_view = DashboardView(app_config, user)
        self._placeholder = self._build_placeholder()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._dashboard_view)
        self._stack.addWidget(self._placeholder)
        self._stack.setCurrentWidget(self._dashboard_view)

        self._menu_tree = self._build_menu_tree()
        self._topbar = self._build_topbar()

        self._update_thread: QThread | None = None
        self._update_worker: _UpdateCheckWorker | None = None
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(UPDATE_CHECK_INTERVAL_MS)
        self._update_timer.timeout.connect(self._check_for_update)
        self._update_timer.start()
        self._check_for_update()  # 시작하자마자 1회 확인, 이후 1분 주기

        splitter = QSplitter()
        splitter.addWidget(self._menu_tree)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, POPUP_WIDTH - 260])

        central = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._topbar)
        central_layout.addWidget(splitter)
        central.setLayout(central_layout)
        self.setCentralWidget(central)

        self.apply_theme()

    def apply_theme(self) -> None:
        """OS 다크/라이트 모드 변경 시 메뉴 트리·상단바·대시보드 차트를 다시 칠한다."""
        theme = current_theme()
        self._menu_tree.setStyleSheet(build_menu_tree_qss(theme))
        self._topbar.setStyleSheet(f"background-color: {theme.header_bg};")
        self._placeholder_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 14px;")
        self._dashboard_view.refresh()

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)

        title = QLabel("유티정보 경영관리 그룹웨어")
        title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet("color: rgba(255, 255, 255, 0.65); font-size: 11px;")

        self._update_banner = QPushButton("")
        self._update_banner.setVisible(False)
        self._update_banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_banner.setStyleSheet(
            "QPushButton { background-color: #FFC107; color: #1B1C24; border: none; "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #FFCA33; }"
        )
        self._update_banner.clicked.connect(self._on_update_banner_clicked)

        user_label = QLabel(f"로그인: {self._user.empl_nm}")
        user_label.setStyleSheet("color: white; font-size: 12px;")

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(version_label)
        layout.addWidget(self._update_banner)
        layout.addStretch()
        layout.addWidget(user_label)
        bar.setLayout(layout)
        return bar

    # ------------------------------------------------------------------
    # 자동 업데이트 확인 (1분 주기, 상단바 배너)
    # ------------------------------------------------------------------
    def _check_for_update(self) -> None:
        if self._update_thread is not None:
            return  # 이전 확인이 아직 진행 중이면 이번 틱은 건너뜀

        self._update_thread = QThread(self)
        self._update_worker = _UpdateCheckWorker(self._config.update.repo, self._config.update.token)
        self._update_worker.moveToThread(self._update_thread)

        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._on_update_check_finished)
        self._update_worker.error.connect(self._on_update_check_error)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.error.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._cleanup_update_thread)

        self._update_thread.start()

    def _cleanup_update_thread(self) -> None:
        self._update_thread = None
        self._update_worker = None

    def _on_update_check_error(self, _message: str) -> None:
        pass  # 자동 백그라운드 체크 실패는 조용히 무시(수동 확인은 UpdateDialog에서 안내)

    def _on_update_check_finished(self, info: ReleaseInfo) -> None:
        if info.version and info.asset is not None and is_newer(APP_VERSION, info.version):
            self._update_banner.setText(f"🔔 새 버전 v{info.version} 사용 가능 — 클릭해 업데이트")
            self._update_banner.setVisible(True)
        else:
            self._update_banner.setVisible(False)

    def _on_update_banner_clicked(self) -> None:
        UpdateDialog(self._config, parent=self).exec()

    def _build_menu_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setFixedWidth(260)
        tree.setIndentation(12)
        tree.setWordWrap(True)

        for item in MENU_TREE:
            top_item = QTreeWidgetItem([item.label])
            for child in item.children:
                child_item = QTreeWidgetItem([child.label])
                child_item.setData(0, CONTENT_KEY_ROLE, child.content_key)
                top_item.addChild(child_item)
            tree.addTopLevelItem(top_item)

        tree.itemClicked.connect(self._on_menu_item_clicked)
        return tree

    def _build_placeholder(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        self._placeholder_label = QLabel("준비중입니다.")
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder_label)
        widget.setLayout(layout)
        return widget

    def _on_menu_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
            return

        content_key = item.data(0, CONTENT_KEY_ROLE)
        if content_key == "dashboard":
            self._stack.setCurrentWidget(self._dashboard_view)
        elif content_key == "sales_purchase":
            SalesPurchaseDialog(self._config, parent=self).exec()
        elif content_key == "project_cost":
            ProjectCostDialog(self._config, parent=self).exec()
        elif content_key == "project_manpower":
            ProjectManpowerDialog(self._config, self._user, parent=self).exec()
        elif content_key == "project_input_mm":
            ProjectInputMmDialog(self._config, self._user, parent=self).exec()
        elif content_key == "project_headcount":
            ProjectHeadcountDialog(self._config, parent=self).exec()
        elif content_key == "app_update":
            UpdateDialog(self._config, parent=self).exec()
        else:
            self._placeholder_label.setText(f"'{item.text(0)}' 화면은 준비중입니다.")
            self._stack.setCurrentWidget(self._placeholder)

    def closeEvent(self, event) -> None:
        self._dashboard_view.shutdown()
        self._update_timer.stop()
        if self._update_thread is not None:
            self._update_thread.quit()
            self._update_thread.wait()
        super().closeEvent(event)
