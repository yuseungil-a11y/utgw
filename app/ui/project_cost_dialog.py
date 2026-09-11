from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from openpyxl import Workbook

from app.config import AppConfig
from app.queries.project_cost import COLUMNS, get_project_cost_rows
from app.queries.project_input_mm import get_bulk_actuals
from app.ui.theme import POPUP_GRID_FONT_PX, POPUP_HEIGHT, POPUP_WIDTH, current_theme

_ORG_COL = COLUMNS.index("수행조직")
_NAME_COL = COLUMNS.index("프로젝트명")
_LABOR_COL = COLUMNS.index("노무비")
_EXPENSE_COL = COLUMNS.index("경비")
_OUTSOURCING_COL = COLUMNS.index("외주비")
_ALL_ORGS_LABEL = "전체"
_ACTUAL_ROW_LABEL = "└ 실적 집행"
# {계획 컬럼 인덱스: 실적 dict(get_bulk_actuals 반환값)의 키} — 실적 데이터가 있는 항목만.
_ACTUAL_COMPARABLE_COLS = {
    _LABOR_COL: "labor",
    _EXPENSE_COL: "expense",
    _OUTSOURCING_COL: "outsourcing",
}

_INITIAL_COLUMN_WIDTHS = {
    "프로젝트코드": 110,
    "프로젝트명": 260,
    "수행조직": 120,
    "PM": 70,
    "발주처": 140,
    "매출처": 140,
    "프로젝트 기간": 170,
    "매출총액": 120,
    "제안비용": 100,
    "재료비": 90,
    "노무비": 110,
    "경비": 100,
    "일반관리비": 100,
    "영업비": 90,
    "외주비": 110,
    "영업이익": 110,
    "하자보수비": 100,
    "최종영업이익": 120,
}


class ProjectCostDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._all_rows: list[tuple] = []
        self._rows: list[tuple] = []
        self._actuals_by_prj: dict[str, dict[str, float | int]] = {}

        self.setWindowTitle("프로젝트 원가")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(POPUP_WIDTH, POPUP_HEIGHT)

        title_label = QLabel("프로젝트 원가")
        title_label.setProperty("role", "title")

        org_label = QLabel("수행조직:")
        org_label.setProperty("role", "secondary")

        self._org_combo = QComboBox()
        self._org_combo.addItem(_ALL_ORGS_LABEL)
        self._org_combo.currentTextChanged.connect(self._on_org_filter_changed)

        self._compare_checkbox = QCheckBox("실적 집행 비교")
        self._compare_checkbox.toggled.connect(self._on_compare_toggled)

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")

        refresh_button = QPushButton("새로고침")
        refresh_button.clicked.connect(self._load_data)

        export_button = QPushButton("엑셀로 저장")
        export_button.setProperty("variant", "secondary")
        export_button.clicked.connect(self._export_to_excel)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addSpacing(16)
        header_row.addWidget(org_label)
        header_row.addWidget(self._org_combo)
        header_row.addSpacing(16)
        header_row.addWidget(self._compare_checkbox)
        header_row.addStretch()
        header_row.addWidget(refresh_button)
        header_row.addWidget(export_button)

        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(True)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for col_idx, col_name in enumerate(COLUMNS):
            width = _INITIAL_COLUMN_WIDTHS.get(col_name)
            if width is not None:
                self._table.setColumnWidth(col_idx, width)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        self.setLayout(layout)

        self._load_data()

    def _load_data(self) -> None:
        try:
            rows = get_project_cost_rows(self._config.database)
        except Exception as exc:  # noqa: BLE001 - 조회 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "조회 실패", f"프로젝트 원가 조회에 실패했습니다.\n{exc}")
            return

        self._all_rows = [row.as_tuple() for row in rows]

        try:
            self._actuals_by_prj = get_bulk_actuals(self._config.database)
        except Exception as exc:  # noqa: BLE001 - 실적 비교는 부가 기능이라 계획 표는 그대로 보여준다
            self._actuals_by_prj = {}
            if self._compare_checkbox.isChecked():
                QMessageBox.warning(self, "실적 집행 비교", f"실적 데이터 조회에 실패했습니다.\n{exc}")

        self._refresh_org_options()
        self._apply_org_filter()

    def _on_compare_toggled(self, _checked: bool) -> None:
        self._populate_table()
        self._update_status_label()

    def _refresh_org_options(self) -> None:
        orgs = sorted({row[_ORG_COL] for row in self._all_rows if row[_ORG_COL]})
        current = self._org_combo.currentText()

        self._org_combo.blockSignals(True)
        self._org_combo.clear()
        self._org_combo.addItem(_ALL_ORGS_LABEL)
        self._org_combo.addItems(orgs)
        restore_index = self._org_combo.findText(current)
        self._org_combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self._org_combo.blockSignals(False)

    def _on_org_filter_changed(self, _text: str) -> None:
        self._apply_org_filter()

    def _apply_org_filter(self) -> None:
        selected = self._org_combo.currentText()
        if selected and selected != _ALL_ORGS_LABEL:
            self._rows = [row for row in self._all_rows if row[_ORG_COL] == selected]
        else:
            self._rows = list(self._all_rows)

        self._populate_table()
        self._update_status_label()

    def _update_status_label(self) -> None:
        status = f"총 {len(self._rows)}개 프로젝트"
        if self._compare_checkbox.isChecked():
            compared = sum(1 for row in self._rows if row[0] in self._actuals_by_prj)
            status += f" · 실적 집행 데이터 있음 {compared}건"
        self._status_label.setText(status)

    def _populate_table(self) -> None:
        """"실적 집행 비교" 체크박스가 켜져 있으면, 프로젝트(계획) 행 바로 아래에
        실적(노무비·경비·외주비) 비교 행을 추가한다. 실적 데이터가 아예 없는
        프로젝트는 비교 행을 만들지 않는다(대부분의 프로젝트가 아직 업무일지/경비
        실적이 없어서, 전부 0으로 채운 행을 보여주면 오히려 표만 산만해진다)."""
        show_compare = self._compare_checkbox.isChecked()
        theme = current_theme()

        display_rows: list[tuple[str, tuple]] = []
        for row in self._rows:
            display_rows.append(("plan", row))
            if not show_compare:
                continue
            actuals = self._actuals_by_prj.get(row[0])
            if actuals is None:
                continue
            actual_row = [""] * len(COLUMNS)
            actual_row[_NAME_COL] = _ACTUAL_ROW_LABEL
            for col_idx, key in _ACTUAL_COMPARABLE_COLS.items():
                actual_row[col_idx] = int(actuals.get(key, 0))
            display_rows.append(("actual", tuple(actual_row)))

        self._table.setRowCount(len(display_rows))
        for row_idx, (kind, row) in enumerate(display_rows):
            plan_row = display_rows[row_idx - 1][1] if kind == "actual" else None
            for col_idx, value in enumerate(row):
                text = f"{value:,}" if isinstance(value, int) else str(value)
                item = QTableWidgetItem(text)
                if isinstance(value, int):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                if kind == "actual":
                    if col_idx == _NAME_COL:
                        item.setForeground(QColor(theme.text_secondary))
                    elif col_idx in _ACTUAL_COMPARABLE_COLS:
                        plan_value = plan_row[col_idx] if plan_row else 0
                        if isinstance(value, int) and value > plan_value:
                            font = QFont()
                            font.setBold(True)
                            item.setFont(font)
                            item.setForeground(QColor(theme.destructive))
                            item.setBackground(QColor(theme.destructive).lighter(175))
                        else:
                            item.setForeground(QColor(theme.text_secondary))

                self._table.setItem(row_idx, col_idx, item)
        self._table.resizeRowsToContents()

    def _export_to_excel(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "엑셀로 저장", "저장할 데이터가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "엑셀로 저장", "프로젝트원가.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "프로젝트원가"
        sheet.append(COLUMNS)
        for row in self._rows:
            sheet.append(row)

        try:
            workbook.save(path)
        except Exception as exc:  # noqa: BLE001 - 저장 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "저장 실패", f"엑셀 파일 저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "엑셀로 저장", f"저장이 완료되었습니다.\n{path}")
