from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
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
from app.ui.project_input_mm_dialog import ProjectInputMmDialog
from app.ui.project_manpower_dialog import ProjectManpowerDialog
from app.ui.sales_purchase_dialog import SalesPurchaseDialog
from app.ui.theme import build_menu_tree_qss, current_theme
from app.version import APP_VERSION

CONTENT_KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser):
        super().__init__()
        self._config = app_config
        self._user = user

        self.setWindowTitle("유티정보 그룹웨어 경영관리 프로그램")
        self.resize(1200, 800)

        self._dashboard_view = DashboardView(app_config, user)
        self._placeholder = self._build_placeholder()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._dashboard_view)
        self._stack.addWidget(self._placeholder)
        self._stack.setCurrentWidget(self._dashboard_view)

        self._menu_tree = self._build_menu_tree()
        self._topbar = self._build_topbar()

        splitter = QSplitter()
        splitter.addWidget(self._menu_tree)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])

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

        user_label = QLabel(f"로그인: {self._user.empl_nm}")
        user_label.setStyleSheet("color: white; font-size: 12px;")

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(version_label)
        layout.addStretch()
        layout.addWidget(user_label)
        bar.setLayout(layout)
        return bar

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
        else:
            self._placeholder_label.setText(f"'{item.text(0)}' 화면은 준비중입니다.")
            self._stack.setCurrentWidget(self._placeholder)

    def closeEvent(self, event) -> None:
        self._dashboard_view.shutdown()
        super().closeEvent(event)
