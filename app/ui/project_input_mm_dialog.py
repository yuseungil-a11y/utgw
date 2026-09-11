from PySide6.QtCharts import (
    QAbstractBarSeries,
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.auth import AuthenticatedUser
from app.config import AppConfig
from app.queries.labor_cost import ensure_table_exists as ensure_labor_cost_table
from app.queries.labor_cost import seed_default_rates
from app.queries.project_input_mm import (
    STANDARD_MONTH_HOURS,
    ExecutionComparisonRow,
    get_execution_comparison,
    get_project_options,
)
from app.ui.table_utils import NumericTableWidgetItem, enable_header_sorting
from app.ui.theme import POPUP_GRID_FONT_PX, POPUP_HEIGHT, POPUP_WIDTH, current_theme

_ROWS = [
    ("계약금액(수주금액)", "contract_amount", "contract_amount"),
    ("제안비용", "proposal_cost", "proposal_cost"),
    ("노무비", "plan_labor_cost", "actual_labor_cost"),
    ("경비", "plan_expense", "actual_expense"),
    ("외주비", "plan_outsourcing_cost", "actual_outsourcing_cost"),
]


def _won_to_million(value: int) -> float:
    """차트 막대 라벨이 지수표기(예: 5.43989e+08)로 바뀌지 않도록 백만원 단위로 축소한다.
    정확한 원 단위 금액은 표 쪽에 그대로 표시한다."""
    return round(value / 1_000_000, 1)


class ProjectInputMmDialog(QDialog):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._user = user
        self._projects: list[tuple[str, str, str]] = []

        self.setWindowTitle("프로젝트 실행원가 비교")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(POPUP_WIDTH, POPUP_HEIGHT)

        title_label = QLabel("프로젝트 실행원가 비교")
        title_label.setProperty("role", "title")

        project_label = QLabel("프로젝트 선택")
        project_label.setProperty("role", "secondary")
        self._project_search = QLineEdit()
        self._project_search.setPlaceholderText("프로젝트명, 발주처, 코드로 검색")
        self._project_search.textChanged.connect(self._apply_project_filter)
        self._project_list = QListWidget()
        self._project_list.setWordWrap(True)
        self._project_list.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        self._project_list.currentItemChanged.connect(self._on_project_selected)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(project_label, 0)
        left_layout.addWidget(self._project_search, 0)
        left_layout.addWidget(self._project_list, 1)
        left_panel = QWidget()
        left_panel.setLayout(left_layout)
        left_panel.setMinimumWidth(280)
        left_panel.setMaximumWidth(340)

        self._detail_title = QLabel("좌측 목록에서 프로젝트를 선택해 주세요.")
        self._detail_title.setProperty("role", "title")
        self._detail_meta = QLabel("")
        self._detail_meta.setProperty("role", "secondary")
        self._detail_meta.setWordWrap(True)

        self._chart = QChart()
        self._chart.setTitle("계획 대비 실적 (단위: 백만원)")
        self._chart_view = QChartView(self._chart)
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chart_view.setStyleSheet("background: transparent;")
        self._chart_view.setMinimumHeight(260)
        self._chart_view.setMaximumHeight(320)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["항목", "계획(실행예산)", "실적(집행)", "차이(실적-계획)"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        enable_header_sorting(self._table)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._table.setColumnWidth(0, 160)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 160)

        self._note_label = QLabel(
            "※ 노무비 실적은 업무일지(투입시간)를 직원 직급·근무연도별로 묶어 "
            f"tb_labor_cost 단가표(적용년도+직급코드 → 인월단가, 1인월={STANDARD_MONTH_HOURS}시간)를 "
            "적용해 계산합니다.\n"
            "※ 경비 실적은 전자결재 경비 지출결의(tb_request_expenses)의 해당 프로젝트 금액 합계이며, "
            "반려된 건만 제외합니다(승인·진행중 포함). 계획 경비는 실행예산 경비입니다.\n"
            "※ 외주비 실적은 매출/매입 원장에 등록된 매입 금액 합계이며, 확정 여부와는 무관합니다.\n"
            "※ 계약금액·제안비용은 계획/실적 구분 없이 동일한 값입니다."
        )
        self._note_label.setProperty("role", "secondary")
        self._note_label.setWordWrap(True)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._detail_title, 0)
        right_layout.addWidget(self._detail_meta, 0)
        right_layout.addWidget(self._chart_view, 0)
        right_layout.addWidget(self._table, 1)
        right_layout.addWidget(self._note_label, 0)
        right_panel = QWidget()
        right_panel.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 800])

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title_label, 0)
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

        try:
            ensure_labor_cost_table(self._config.database)
            seed_default_rates(self._config.database, self._user.empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "초기화 실패", f"노무비 단가표 준비에 실패했습니다.\n{exc}")

        self._load_projects()

    def _load_projects(self) -> None:
        try:
            self._projects = get_project_options(self._config.database)
        except Exception as exc:  # noqa: BLE001 - 조회 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "조회 실패", f"프로젝트 목록 조회에 실패했습니다.\n{exc}")
            return
        self._apply_project_filter("")

    def _apply_project_filter(self, keyword: str) -> None:
        keyword = keyword.strip().lower()
        self._project_list.blockSignals(True)
        self._project_list.clear()
        for prj_id, prj_name, client_name in self._projects:
            haystack = f"{prj_id} {prj_name} {client_name}".lower()
            if keyword and keyword not in haystack:
                continue
            item = QListWidgetItem(f"[{prj_id}] {prj_name}")
            item.setData(Qt.ItemDataRole.UserRole, prj_id)
            self._project_list.addItem(item)
        self._project_list.blockSignals(False)

    def _on_project_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        prj_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            row = get_execution_comparison(self._config.database, prj_id)
        except Exception as exc:  # noqa: BLE001 - 조회 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "조회 실패", f"집행비용 비교 조회에 실패했습니다.\n{exc}")
            return
        if row is None:
            self._detail_title.setText("데이터를 찾을 수 없습니다.")
            self._detail_meta.setText("")
            self._table.setRowCount(0)
            self._chart.removeAllSeries()
            return
        self._populate_detail(row)

    def _populate_detail(self, row: ExecutionComparisonRow) -> None:
        self._detail_title.setText(f"[{row.prj_id}] {row.prj_name}")
        meta_text = (
            f"발주처: {row.client_name or '-'}   ·   사업기간: {row.period or '-'}   ·   "
            f"업무일지 투입시간 합계: {row.actual_labor_hours:,.1f}시간"
        )
        if row.unrated_labor_hours > 0:
            meta_text += (
                f"   ·   단가 미등록 {row.unrated_labor_hours:,.1f}시간(0원 처리됨, tb_labor_cost 확인 필요)"
            )
        self._detail_meta.setText(meta_text)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(_ROWS))
        for row_idx, (label, plan_field, actual_field) in enumerate(_ROWS):
            plan_value = getattr(row, plan_field)
            actual_value = getattr(row, actual_field)
            diff_value = actual_value - plan_value

            label_item = QTableWidgetItem(label)
            self._table.setItem(row_idx, 0, label_item)

            for col_idx, value in ((1, plan_value), (2, actual_value), (3, diff_value)):
                item = NumericTableWidgetItem(f"{value:,}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row_idx, col_idx, item)
        self._table.resizeRowsToContents()
        self._table.setSortingEnabled(True)

        self._render_chart(row)

    def _render_chart(self, row: ExecutionComparisonRow) -> None:
        self._chart.removeAllSeries()

        plan_values = [_won_to_million(getattr(row, plan_field)) for _label, plan_field, _actual_field in _ROWS]
        actual_values = [
            _won_to_million(getattr(row, actual_field)) for _label, _plan_field, actual_field in _ROWS
        ]

        plan_set = QBarSet("계획(실행예산)")
        plan_set.append(plan_values)
        actual_set = QBarSet("실적(집행)")
        actual_set.append(actual_values)

        series = QBarSeries()
        series.append(plan_set)
        series.append(actual_set)
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value")
        series.setLabelsPosition(QAbstractBarSeries.LabelsPosition.LabelsOutsideEnd)
        self._chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append([label for label, _plan_field, _actual_field in _ROWS])
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%,.0f")
        axis_y.setRange(0, max(plan_values + actual_values + [1]) * 1.25)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        theme = current_theme()
        self._chart.setBackgroundBrush(QColor(theme.chart_bg))
        self._chart.setBackgroundRoundness(0)
        self._chart.setTitleBrush(QColor(theme.chart_text))
        self._chart.legend().setLabelColor(QColor(theme.chart_text))
        axis_x.setLabelsColor(QColor(theme.chart_text))
        axis_y.setLabelsColor(QColor(theme.chart_text))
        plan_set.setLabelColor(QColor(theme.chart_text))
        actual_set.setLabelColor(QColor(theme.chart_text))
