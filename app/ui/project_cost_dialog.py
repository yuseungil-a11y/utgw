from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

_ORG_COL = COLUMNS.index("수행조직")
_ALL_ORGS_LABEL = "전체"

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

        self.setWindowTitle("프로젝트 원가")
        self.resize(1300, 680)

        title_label = QLabel("프로젝트 원가")
        title_label.setProperty("role", "title")

        org_label = QLabel("수행조직:")
        org_label.setProperty("role", "secondary")

        self._org_combo = QComboBox()
        self._org_combo.addItem(_ALL_ORGS_LABEL)
        self._org_combo.currentTextChanged.connect(self._on_org_filter_changed)

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
        header_row.addStretch()
        header_row.addWidget(refresh_button)
        header_row.addWidget(export_button)

        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(True)

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
        self._refresh_org_options()
        self._apply_org_filter()

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
        self._status_label.setText(f"총 {len(self._rows)}개 프로젝트")

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            for col_idx, value in enumerate(row):
                text = f"{value:,}" if isinstance(value, int) else str(value)
                item = QTableWidgetItem(text)
                if isinstance(value, int):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
