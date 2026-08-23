from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDateEdit,
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
    QWidget,
)
from openpyxl import Workbook

from app.config import AppConfig
from app.queries.sales_purchase import COLUMNS, get_sales_purchase_rows
from app.ui.theme import current_theme

_DIVISION_COL = COLUMNS.index("구분")
_AMOUNT_COL = COLUMNS.index("금액")

# 컬럼별 초기 폭(px). 사용자가 드래그해서 자유롭게 조절할 수 있고, 여기서는
# "계약명"처럼 문장이 긴 컬럼이 기본으로 잘리지 않도록 넉넉하게 잡아둔다.
_INITIAL_COLUMN_WIDTHS = {
    "코드": 150,
    "계약명": 320,
    "계약처": 140,
    "구분": 60,
    "항목": 160,
    "요청일자": 90,
    "등록일자": 90,
    "처리상태": 100,
    "금액": 120,
}


class SalesPurchaseDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._rows: list[tuple] = []

        self.setWindowTitle("매출/매입현황")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(1100, 640)

        today = QDate.currentDate()
        self._date_from_edit = QDateEdit(QDate(today.year(), 1, 1))
        self._date_from_edit.setCalendarPopup(True)
        self._date_from_edit.setDisplayFormat("yyyy-MM-dd")

        self._date_to_edit = QDateEdit(today)
        self._date_to_edit.setCalendarPopup(True)
        self._date_to_edit.setDisplayFormat("yyyy-MM-dd")

        search_button = QPushButton("조회")
        search_button.clicked.connect(self._load_data)

        export_button = QPushButton("엑셀로 저장")
        export_button.setProperty("variant", "secondary")
        export_button.clicked.connect(self._export_to_excel)

        filter_label = QLabel("등록일자 기준 기간:")
        filter_label.setProperty("role", "secondary")

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(filter_label)
        filter_bar.addWidget(self._date_from_edit)
        filter_bar.addWidget(QLabel("~"))
        filter_bar.addWidget(self._date_to_edit)
        filter_bar.addWidget(search_button)
        filter_bar.addStretch()
        filter_bar.addWidget(export_button)

        self._summary_label = QLabel("")
        self._summary_label.setProperty("role", "title")

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")

        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(True)
        self._table.setAlternatingRowColors(True)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for col_idx, col_name in enumerate(COLUMNS):
            width = _INITIAL_COLUMN_WIDTHS.get(col_name)
            if width is not None:
                self._table.setColumnWidth(col_idx, width)

        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addLayout(filter_bar)
        toolbar_layout.addWidget(self._summary_label)
        toolbar_layout.addWidget(self._status_label)

        toolbar_card = QWidget()
        toolbar_card.setProperty("role", "card")
        toolbar_card.setLayout(toolbar_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(toolbar_card)
        layout.addWidget(self._table)
        self.setLayout(layout)

        self._load_data()

    @staticmethod
    def _to_python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _load_data(self) -> None:
        date_from = self._to_python_date(self._date_from_edit.date())
        date_to = self._to_python_date(self._date_to_edit.date())

        if date_from > date_to:
            QMessageBox.warning(self, "매출/매입현황", "시작일이 종료일보다 늦을 수 없습니다.")
            return

        try:
            rows = get_sales_purchase_rows(self._config.database, date_from, date_to)
        except Exception as exc:  # noqa: BLE001 - 조회 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "조회 실패", f"매출/매입현황 조회에 실패했습니다.\n{exc}")
            return

        self._rows = [row.as_tuple() for row in rows]
        self._populate_table()
        self._update_summary()
        self._status_label.setText(
            f"{date_from.isoformat()} ~ {date_to.isoformat()} · 총 {len(self._rows)}건"
        )

    def _update_summary(self) -> None:
        # self._rows는 위 _load_data에서 선택된 기간(date_from~date_to)으로 조회한
        # 결과이므로, 여기서 만드는 합계도 자동으로 선택된 기간 기준이 된다.
        sales_total = sum(
            row[_AMOUNT_COL] for row in self._rows if row[_DIVISION_COL] == "매출"
        )
        purchase_total = sum(
            row[_AMOUNT_COL] for row in self._rows if row[_DIVISION_COL] == "매입"
        )
        self._summary_label.setText(
            f"매출 합계: {sales_total:,}원   /   매입 합계: {purchase_total:,}원"
        )

    def _populate_table(self) -> None:
        theme = current_theme()
        # 디자인 가이드: 상태값은 배지(배경 채움) 대신 컬러 텍스트만으로 구분한다.
        division_text_colors = {"매출": theme.sales_text, "매입": theme.purchase_text}

        self._table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            for col_idx, value in enumerate(row):
                text = f"{value:,}" if isinstance(value, int) else str(value)
                item = QTableWidgetItem(text)
                if isinstance(value, int):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col_idx == _DIVISION_COL:
                    color = division_text_colors.get(value)
                    if color is not None:
                        item.setForeground(QColor(color))
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_idx, col_idx, item)
        self._table.resizeRowsToContents()

    def _export_to_excel(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "엑셀로 저장", "저장할 데이터가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "엑셀로 저장", "매출매입현황.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "매출매입현황"
        sheet.append(COLUMNS)
        for row in self._rows:
            sheet.append(row)

        try:
            workbook.save(path)
        except Exception as exc:  # noqa: BLE001 - 저장 실패를 사용자에게 그대로 안내
            QMessageBox.critical(self, "저장 실패", f"엑셀 파일 저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "엑셀로 저장", f"저장이 완료되었습니다.\n{path}")
