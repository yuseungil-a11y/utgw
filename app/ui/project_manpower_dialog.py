from calendar import monthrange
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from app.auth import AuthenticatedUser
from app.config import AppConfig
from app.queries.project_manpower import (
    EmployeeRow,
    ProjectCell,
    ProjectMeta,
    add_project,
    ensure_table_exists,
    get_employee_matrix,
    get_grade_options,
    get_role_options,
    get_tracked_projects,
    remove_project,
    save_employee_grades,
    save_matrix,
    search_projects,
)
from app.ui.theme import current_theme

# 스크롤해도 항상 보여야 하는 직원 식별 컬럼 (틀고정 영역)
FROZEN_COLUMNS = ["번호", "성명", "입사일", "부서"]
# 나머지 직원 정보 컬럼 (스크롤 영역의 왼쪽에 위치)
SCROLL_FIXED_COLUMNS = [
    "직급",
    "기술등급\n(대외/제안서)",
    "기술등급\n(S/W자격증)",
    "참여여부\n(하나라도)",
    "PM,PL\n여부",
]
BLOCK_LABELS = ["참여", "역할", "상주", "비상주", "비고"]
FROZEN_COL_COUNT = len(FROZEN_COLUMNS)
SCROLL_FIXED_COL_COUNT = len(SCROLL_FIXED_COLUMNS)
BLOCK_SIZE = len(BLOCK_LABELS)

_NO_ROLE_LABEL = "(선택 안 함)"
_NO_GRADE_LABEL = "(선택 안 함)"
_ROW_HEIGHT = 30
_PARTICIPATE_COL_MIN_WIDTH = 140
_PARTICIPATE_COL_MAX_WIDTH = 340
_HEADER_TEXT_PADDING = 24

WBS_FIXED_COLUMNS = ["성명", "역할"]
WBS_FIXED_COL_COUNT = len(WBS_FIXED_COLUMNS)


def _month_range(projects: list[ProjectMeta]) -> list[tuple[int, int]]:
    """추적 중인 전체 프로젝트의 계약기간을 아우르는 (연,월) 목록을 만든다."""
    starts = [date.fromisoformat(p.start_date) for p in projects if p.start_date]
    ends = [date.fromisoformat(p.end_date) for p in projects if p.end_date]
    if not starts or not ends:
        today = date.today()
        return [(today.year, m) for m in range(1, 13)]

    min_start, max_end = min(starts), max(ends)
    months: list[tuple[int, int]] = []
    y, m = min_start.year, min_start.month
    while (y, m) <= (max_end.year, max_end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _month_overlaps(year: int, month: int, start: date, end: date) -> bool:
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    return first_day <= end and last_day >= start


class _AddProjectDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = app_config
        self.selected_prj_id: str | None = None

        self.setWindowTitle("프로젝트 추가")
        self.resize(560, 420)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("프로젝트명, 발주기관, 코드로 검색 (예: 한국도로공사)")
        self._search_input.textChanged.connect(self._on_search_changed)

        self._result_list = QListWidget()
        self._result_list.itemDoubleClicked.connect(lambda _item: self._confirm())

        add_button = QPushButton("추가")
        add_button.clicked.connect(self._confirm)
        cancel_button = QPushButton("취소")
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(add_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self._search_input)
        layout.addWidget(self._result_list)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self._on_search_changed("한국도로공사")
        self._search_input.setText("한국도로공사")

    def _on_search_changed(self, keyword: str) -> None:
        keyword = keyword.strip()
        if not keyword:
            self._result_list.clear()
            return
        try:
            results = search_projects(self._config.database, keyword)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "검색 실패", f"프로젝트 검색에 실패했습니다.\n{exc}")
            return

        self._result_list.clear()
        for prj_id, prj_name, client_name in results:
            item = QListWidgetItem(f"[{prj_id}] {prj_name}  ·  {client_name}")
            item.setData(Qt.ItemDataRole.UserRole, prj_id)
            self._result_list.addItem(item)

    def _confirm(self) -> None:
        item = self._result_list.currentItem()
        if item is None:
            QMessageBox.warning(self, "프로젝트 추가", "추가할 프로젝트를 선택해 주세요.")
            return
        self.selected_prj_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class ProjectManpowerDialog(QDialog):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._user = user
        self._projects: list[ProjectMeta] = []
        self._role_options: list[tuple[str, str]] = []
        self._grade_options: list[tuple[str, str]] = []
        self._employee_rows: list[EmployeeRow] = []
        self._syncing_scroll = False

        self.setWindowTitle("한국도로공사 투입인력관리")
        self.resize(1400, 720)

        title_label = QLabel("한국도로공사 투입인력관리")
        title_label.setProperty("role", "title")

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")

        self._matrix_radio = QRadioButton("매트릭스 보기")
        self._matrix_radio.setChecked(True)
        self._wbs_radio = QRadioButton("WBS(월별) 보기")
        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.addButton(self._matrix_radio)
        self._view_mode_group.addButton(self._wbs_radio)
        self._matrix_radio.toggled.connect(self._on_view_mode_changed)

        refresh_button = QPushButton("새로고침")
        refresh_button.setProperty("variant", "secondary")
        refresh_button.clicked.connect(self._load_data)

        add_project_button = QPushButton("+ 프로젝트 추가")
        add_project_button.setProperty("variant", "secondary")
        add_project_button.clicked.connect(self._on_add_project)

        export_button = QPushButton("엑셀로 저장")
        export_button.setProperty("variant", "secondary")
        export_button.clicked.connect(self._export_to_excel)

        self._save_button = QPushButton("저장")
        self._save_button.clicked.connect(self._on_save)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addSpacing(20)
        header_row.addWidget(self._matrix_radio)
        header_row.addWidget(self._wbs_radio)
        header_row.addStretch()
        header_row.addWidget(refresh_button)
        header_row.addWidget(add_project_button)
        header_row.addWidget(export_button)
        header_row.addWidget(self._save_button)

        # 틀고정 패널(번호/성명/입사일/부서) — 항상 보임, 자체 스크롤 없음
        self._frozen_table = QTableWidget()
        self._frozen_table.setColumnCount(FROZEN_COL_COUNT)
        self._frozen_table.setHorizontalHeaderLabels(FROZEN_COLUMNS)
        self._frozen_table.verticalHeader().setVisible(False)
        self._frozen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._frozen_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._frozen_table.setColumnWidth(0, 50)
        self._frozen_table.setColumnWidth(1, 80)
        self._frozen_table.setColumnWidth(2, 90)
        self._frozen_table.setColumnWidth(3, 110)
        self._frozen_table.setFixedWidth(50 + 80 + 90 + 110 + 2)

        # 나머지(직급/기술등급/참여여부/PM,PL여부 + 프로젝트 블록) — 가로 스크롤
        self._data_table = QTableWidget()
        self._data_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self._data_table.verticalHeader().setVisible(False)

        for table in (self._frozen_table, self._data_table):
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(50)
            header.setFixedHeight(96)
            table.setMinimumHeight(560)

        # 프로젝트 블록 헤더 우클릭 -> 프로젝트 삭제
        data_header = self._data_table.horizontalHeader()
        data_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        data_header.customContextMenuRequested.connect(self._on_header_context_menu)

        self._frozen_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(self._data_table, v)
        )
        self._data_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(self._frozen_table, v)
        )

        tables_row = QHBoxLayout()
        tables_row.setSpacing(0)
        tables_row.addWidget(self._frozen_table)
        tables_row.addWidget(self._data_table)
        matrix_page = QWidget()
        matrix_page.setLayout(tables_row)

        # WBS(월별) 보기 — 프로젝트별 헤더 행 + 참여 직원의 계약기간을 월별 막대로 표시
        self._wbs_table = QTableWidget()
        self._wbs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._wbs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._wbs_table.verticalHeader().setVisible(False)
        self._wbs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._wbs_table.setMinimumHeight(560)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(matrix_page)
        self._view_stack.addWidget(self._wbs_table)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._view_stack)
        self.setLayout(layout)

        try:
            ensure_table_exists(self._config.database)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "초기화 실패", f"tb_extms 테이블 준비에 실패했습니다.\n{exc}")

        self._load_data()

    def _sync_scroll(self, target: QTableWidget, value: int) -> None:
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        target.verticalScrollBar().setValue(value)
        self._syncing_scroll = False

    def _on_view_mode_changed(self, _checked: bool) -> None:
        is_matrix = self._matrix_radio.isChecked()
        self._view_stack.setCurrentIndex(0 if is_matrix else 1)
        self._save_button.setEnabled(is_matrix)

    # ------------------------------------------------------------------
    # 데이터 로드
    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        try:
            self._role_options = get_role_options(self._config.database)
            self._grade_options = get_grade_options(self._config.database)
            self._projects = get_tracked_projects(self._config.database)
            self._employee_rows = get_employee_matrix(
                self._config.database, [p.prj_id for p in self._projects]
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "조회 실패", f"투입인력 정보 조회에 실패했습니다.\n{exc}")
            return

        self._build_tables()
        self._build_wbs_table()
        self._status_label.setText(
            f"직원 {len(self._employee_rows)}명 · 프로젝트 {len(self._projects)}건"
        )

    # ------------------------------------------------------------------
    # 테이블 구성
    # ------------------------------------------------------------------
    def _build_tables(self) -> None:
        row_count = len(self._employee_rows)

        self._frozen_table.setRowCount(row_count)
        for row_idx, employee in enumerate(self._employee_rows):
            values = [str(employee.seq), employee.name, employee.join_date, employee.dept]
            for col_idx, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._frozen_table.setItem(row_idx, col_idx, item)
            self._frozen_table.setRowHeight(row_idx, _ROW_HEIGHT)

        column_count = SCROLL_FIXED_COL_COUNT + BLOCK_SIZE * len(self._projects)
        self._data_table.clear()
        self._data_table.setColumnCount(column_count)
        self._data_table.setRowCount(row_count)

        headers = list(SCROLL_FIXED_COLUMNS)
        block_widths: list[int] = []
        for project in self._projects:
            period = f"{project.start_date} ~ {project.end_date}"
            meta = f"{project.prj_name}\n{project.client_name}\n{period}\n총 {project.total_days}일"
            header_text = f"{meta}\n참여"
            headers.append(header_text)
            headers.extend(BLOCK_LABELS[1:])
            block_widths.append(self._measure_header_width(header_text))
        self._data_table.setHorizontalHeaderLabels(headers)

        for col_idx, name in enumerate(SCROLL_FIXED_COLUMNS):
            width = 90 if "기술등급" in name else 80
            self._data_table.setColumnWidth(col_idx, width)
        for block_idx, block_start in enumerate(
            range(SCROLL_FIXED_COL_COUNT, column_count, BLOCK_SIZE)
        ):
            self._data_table.setColumnWidth(block_start, block_widths[block_idx])  # 참여(+사업명 등)
            self._data_table.setColumnWidth(block_start + 1, 110)  # 역할
            self._data_table.setColumnWidth(block_start + 2, 55)  # 상주
            self._data_table.setColumnWidth(block_start + 3, 55)  # 비상주
            self._data_table.setColumnWidth(block_start + 4, 160)  # 비고

        for row_idx, employee in enumerate(self._employee_rows):
            self._fill_scroll_fixed_columns(row_idx, employee)
            for block_idx, project in enumerate(self._projects):
                col = SCROLL_FIXED_COL_COUNT + block_idx * BLOCK_SIZE
                cell = employee.cells.get(project.prj_id, ProjectCell())
                self._fill_project_block(row_idx, col, cell)
            self._data_table.setRowHeight(row_idx, _ROW_HEIGHT)

    def _measure_header_width(self, header_text: str) -> int:
        """프로젝트 블록의 "참여" 컬럼 폭을 사업명 등 헤더 텍스트의 가장 긴 줄에 맞춰
        자동으로 계산한다 (너무 길면 최대폭에서 Qt가 알아서 말줄임표로 잘라 보여준다)."""
        metrics = QFontMetrics(self._data_table.horizontalHeader().font())
        widest_line = max(
            (metrics.horizontalAdvance(line) for line in header_text.split("\n")), default=0
        )
        return max(_PARTICIPATE_COL_MIN_WIDTH, min(widest_line + _HEADER_TEXT_PADDING, _PARTICIPATE_COL_MAX_WIDTH))

    def _fill_scroll_fixed_columns(self, row_idx: int, employee: EmployeeRow) -> None:
        readonly_values = {
            0: employee.position,
            3: "O" if employee.participates else "",
            4: "O" if employee.is_pm_or_pl else "",
        }
        for col_idx, text in readonly_values.items():
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._data_table.setItem(row_idx, col_idx, item)

        self._data_table.setCellWidget(
            row_idx, 1, self._build_grade_combo(employee.grade_external_div)
        )
        self._data_table.setCellWidget(row_idx, 2, self._build_grade_combo(employee.grade_sw_div))

    def _build_grade_combo(self, current_div: str | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem(_NO_GRADE_LABEL, None)
        selected_index = 0
        for idx, (code, name) in enumerate(self._grade_options, start=1):
            combo.addItem(name, code)
            if code == current_div:
                selected_index = idx
        combo.setCurrentIndex(selected_index)
        return combo

    def _fill_project_block(self, row_idx: int, col: int, cell: ProjectCell) -> None:
        participate_item = QTableWidgetItem()
        participate_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        participate_item.setCheckState(
            Qt.CheckState.Checked if cell.participate else Qt.CheckState.Unchecked
        )
        self._data_table.setItem(row_idx, col, participate_item)

        role_combo = QComboBox()
        role_combo.addItem(_NO_ROLE_LABEL, None)
        selected_index = 0
        for idx, (code, name) in enumerate(self._role_options, start=1):
            role_combo.addItem(name, code)
            if code == cell.role_div:
                selected_index = idx
        role_combo.setCurrentIndex(selected_index)
        self._data_table.setCellWidget(row_idx, col + 1, role_combo)

        resident_item = QTableWidgetItem()
        resident_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        resident_item.setCheckState(
            Qt.CheckState.Checked if cell.resident else Qt.CheckState.Unchecked
        )
        self._data_table.setItem(row_idx, col + 2, resident_item)

        non_resident_item = QTableWidgetItem()
        non_resident_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        non_resident_item.setCheckState(
            Qt.CheckState.Checked if cell.non_resident else Qt.CheckState.Unchecked
        )
        self._data_table.setItem(row_idx, col + 3, non_resident_item)

        remark_item = QTableWidgetItem(cell.remark)
        self._data_table.setItem(row_idx, col + 4, remark_item)

    # ------------------------------------------------------------------
    # WBS(월별) 보기 — 첨부 "도로공사 투입 WBS 형태.xlsx" 레이아웃 참조:
    # 프로젝트명 헤더 행 다음에 참여 직원(성명/역할) 행이 이어지고, 그 직원이 해당
    # 프로젝트에 계약기간 동안 투입된 개월을 색칠된 막대로 표시한다. tb_extms에 저장된
    # "참여" 여부와 프로젝트 계약기간(tb_prj_info)만으로 만드는 파생 뷰라 별도 월별
    # 편집 데이터는 없다 — 마지막으로 저장한 매트릭스 상태를 기준으로 그린다.
    # ------------------------------------------------------------------
    def _wbs_row_spec(self) -> list[tuple[str, str, str, str, str]]:
        """(kind, 텍스트/성명, 역할, 시작일, 종료일) 목록. kind는 'header' 또는 'data'."""
        rows: list[tuple[str, str, str, str, str]] = []
        for project in self._projects:
            rows.append(("header", project.prj_name, "", "", ""))
            for employee in self._employee_rows:
                cell = employee.cells.get(project.prj_id)
                if cell and cell.participate:
                    rows.append(
                        ("data", employee.name, cell.role_name, project.start_date, project.end_date)
                    )
        return rows

    def _build_wbs_table(self) -> None:
        theme = current_theme()
        months = _month_range(self._projects)
        rows_spec = self._wbs_row_spec()

        self._wbs_table.clear()
        self._wbs_table.setColumnCount(WBS_FIXED_COL_COUNT + len(months))
        self._wbs_table.setHorizontalHeaderLabels(
            WBS_FIXED_COLUMNS + [f"{y}.{m}월" for y, m in months]
        )
        self._wbs_table.setColumnWidth(0, 90)
        self._wbs_table.setColumnWidth(1, 90)
        for col in range(WBS_FIXED_COL_COUNT, WBS_FIXED_COL_COUNT + len(months)):
            self._wbs_table.setColumnWidth(col, 55)

        self._wbs_table.setRowCount(len(rows_spec))
        for row_idx, (kind, name, role, start, end) in enumerate(rows_spec):
            self._wbs_table.setRowHeight(row_idx, _ROW_HEIGHT)
            if kind == "header":
                item = QTableWidgetItem(name)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setBackground(QColor(theme.accent))
                item.setForeground(QColor(theme.accent_text))
                self._wbs_table.setItem(row_idx, 0, item)
                self._wbs_table.setSpan(row_idx, 0, 1, WBS_FIXED_COL_COUNT + len(months))
                continue

            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._wbs_table.setItem(row_idx, 0, name_item)

            role_item = QTableWidgetItem(role)
            role_item.setFlags(role_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._wbs_table.setItem(row_idx, 1, role_item)

            start_d = date.fromisoformat(start) if start else None
            end_d = date.fromisoformat(end) if end else None
            for offset, (y, m) in enumerate(months):
                bar_item = QTableWidgetItem("")
                bar_item.setFlags(bar_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if start_d and end_d and _month_overlaps(y, m, start_d, end_d):
                    bar_item.setBackground(QColor(theme.sales_badge_bg))
                self._wbs_table.setItem(row_idx, WBS_FIXED_COL_COUNT + offset, bar_item)

    # ------------------------------------------------------------------
    # 프로젝트 추가
    # ------------------------------------------------------------------
    def _on_add_project(self) -> None:
        dialog = _AddProjectDialog(self._config, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_prj_id:
            return

        if any(p.prj_id == dialog.selected_prj_id for p in self._projects):
            QMessageBox.information(self, "프로젝트 추가", "이미 추가된 프로젝트입니다.")
            return

        try:
            add_project(self._config.database, dialog.selected_prj_id, self._user.empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "추가 실패", f"프로젝트 추가에 실패했습니다.\n{exc}")
            return

        self._load_data()

    # ------------------------------------------------------------------
    # 프로젝트 삭제 (헤더 우클릭)
    # ------------------------------------------------------------------
    def _on_header_context_menu(self, pos) -> None:
        header = self._data_table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < SCROLL_FIXED_COL_COUNT:
            return
        block_idx = (col - SCROLL_FIXED_COL_COUNT) // BLOCK_SIZE
        if block_idx >= len(self._projects):
            return
        project = self._projects[block_idx]

        menu = QMenu(self)
        delete_action = menu.addAction(f"'{project.prj_name}' 프로젝트 삭제")
        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen == delete_action:
            self._on_delete_project(project)

    def _on_delete_project(self, project: ProjectMeta) -> None:
        reply = QMessageBox.question(
            self,
            "프로젝트 삭제",
            f"'{project.prj_name}' 프로젝트를 투입인력관리에서 삭제할까요?\n"
            "이 프로젝트에 저장된 모든 직원의 참여/역할/비고 데이터가 삭제됩니다.\n"
            "(프로젝트 자체나 다른 화면의 데이터에는 영향이 없습니다.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            remove_project(self._config.database, project.prj_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "삭제 실패", f"프로젝트 삭제에 실패했습니다.\n{exc}")
            return

        self._load_data()

    # ------------------------------------------------------------------
    # 화면에 표시된(아직 저장 전일 수도 있는) 현재 셀 상태 읽기
    # ------------------------------------------------------------------
    def _read_current_cell(self, row_idx: int, block_idx: int) -> ProjectCell:
        col = SCROLL_FIXED_COL_COUNT + block_idx * BLOCK_SIZE
        participate_item = self._data_table.item(row_idx, col)
        resident_item = self._data_table.item(row_idx, col + 2)
        non_resident_item = self._data_table.item(row_idx, col + 3)
        remark_item = self._data_table.item(row_idx, col + 4)
        role_combo = self._data_table.cellWidget(row_idx, col + 1)

        return ProjectCell(
            participate=participate_item.checkState() == Qt.CheckState.Checked,
            role_div=role_combo.currentData() if role_combo else None,
            role_name=role_combo.currentText() if role_combo and role_combo.currentData() else "",
            resident=resident_item.checkState() == Qt.CheckState.Checked,
            non_resident=non_resident_item.checkState() == Qt.CheckState.Checked,
            remark=remark_item.text().strip() if remark_item else "",
        )

    # ------------------------------------------------------------------
    # 저장
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        if not self._employee_rows:
            QMessageBox.information(self, "저장", "저장할 데이터가 없습니다.")
            return

        cell_updates: list[tuple[str, str, ProjectCell]] = []
        grade_updates: list[tuple[str, str | None, str | None]] = []
        for row_idx, employee in enumerate(self._employee_rows):
            for block_idx, project in enumerate(self._projects):
                cell = self._read_current_cell(row_idx, block_idx)
                cell_updates.append((project.prj_id, employee.empl_id, cell))

            grade_external_combo = self._data_table.cellWidget(row_idx, 1)
            grade_sw_combo = self._data_table.cellWidget(row_idx, 2)
            grade_updates.append(
                (
                    employee.empl_id,
                    grade_external_combo.currentData() if grade_external_combo else None,
                    grade_sw_combo.currentData() if grade_sw_combo else None,
                )
            )

        try:
            save_matrix(self._config.database, cell_updates, self._user.empl_id)
            save_employee_grades(self._config.database, grade_updates, self._user.empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "저장", "저장되었습니다.")
        self._load_data()

    # ------------------------------------------------------------------
    # 엑셀로 저장
    # ------------------------------------------------------------------
    def _export_to_excel(self) -> None:
        if not self._employee_rows:
            QMessageBox.information(self, "엑셀로 저장", "저장할 데이터가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "엑셀로 저장", "한국도로공사_투입인력관리.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        try:
            if self._wbs_radio.isChecked():
                self._write_wbs_excel(path)
            else:
                self._write_excel(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"엑셀 파일 저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "엑셀로 저장", f"저장이 완료되었습니다.\n{path}")

    def _write_wbs_excel(self, path: str) -> None:
        months = _month_range(self._projects)
        rows_spec = self._wbs_row_spec()
        total_cols = WBS_FIXED_COL_COUNT + len(months)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "투입인력 WBS"

        header_row = 1
        headers = WBS_FIXED_COLUMNS + [f"{y}.{m}월" for y, m in months]
        for col_idx, text in enumerate(headers, start=1):
            sheet.cell(row=header_row, column=col_idx, value=text)

        header_fill = PatternFill(start_color="1E2761", end_color="1E2761", fill_type="solid")
        bar_fill = PatternFill(start_color="E1EAFC", end_color="E1EAFC", fill_type="solid")

        for row_idx, (kind, name, role, start, end) in enumerate(rows_spec, start=1):
            excel_row = header_row + row_idx
            if kind == "header":
                sheet.cell(row=excel_row, column=1, value=name)
                sheet.merge_cells(
                    start_row=excel_row, start_column=1, end_row=excel_row, end_column=total_cols
                )
                sheet.cell(row=excel_row, column=1).fill = header_fill
                continue

            sheet.cell(row=excel_row, column=1, value=name)
            sheet.cell(row=excel_row, column=2, value=role)
            start_d = date.fromisoformat(start) if start else None
            end_d = date.fromisoformat(end) if end else None
            for offset, (y, m) in enumerate(months):
                if start_d and end_d and _month_overlaps(y, m, start_d, end_d):
                    sheet.cell(row=excel_row, column=WBS_FIXED_COL_COUNT + 1 + offset).fill = bar_fill

        sheet.column_dimensions["A"].width = 14
        sheet.column_dimensions["B"].width = 10
        for col_idx in range(WBS_FIXED_COL_COUNT + 1, total_cols + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 9

        workbook.save(path)

    def _write_excel(self, path: str) -> None:
        total_cols = FROZEN_COL_COUNT + SCROLL_FIXED_COL_COUNT + BLOCK_SIZE * len(self._projects)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "투입인력관리"

        meta_labels = ["사업명", "발주기관", "계약기간", "총 투입기간(일)"]
        for meta_row, label in enumerate(meta_labels, start=1):
            sheet.cell(row=meta_row, column=1, value=label)
            sheet.merge_cells(
                start_row=meta_row, start_column=1, end_row=meta_row, end_column=FROZEN_COL_COUNT
            )

        for block_idx, project in enumerate(self._projects):
            start_col = FROZEN_COL_COUNT + SCROLL_FIXED_COL_COUNT + block_idx * BLOCK_SIZE + 1
            end_col = start_col + BLOCK_SIZE - 1
            values = [
                project.prj_name,
                project.client_name,
                f"{project.start_date} ~ {project.end_date}",
                f"{project.total_days}일",
            ]
            for offset, value in enumerate(values, start=1):
                sheet.cell(row=offset, column=start_col, value=value)
                sheet.merge_cells(
                    start_row=offset, start_column=start_col, end_row=offset, end_column=end_col
                )

        header_row = len(meta_labels) + 1
        headers = (
            [label.replace("\n", " ") for label in FROZEN_COLUMNS]
            + [label.replace("\n", " ") for label in SCROLL_FIXED_COLUMNS]
        )
        for _ in self._projects:
            headers.extend(BLOCK_LABELS)
        for col_idx, text in enumerate(headers, start=1):
            sheet.cell(row=header_row, column=col_idx, value=text)

        for row_idx, employee in enumerate(self._employee_rows):
            excel_row = header_row + 1 + row_idx
            grade_external_combo = self._data_table.cellWidget(row_idx, 1)
            grade_sw_combo = self._data_table.cellWidget(row_idx, 2)
            fixed_values = [
                employee.seq,
                employee.name,
                employee.join_date,
                employee.dept,
                employee.position,
                grade_external_combo.currentText() if grade_external_combo and grade_external_combo.currentData() else "",
                grade_sw_combo.currentText() if grade_sw_combo and grade_sw_combo.currentData() else "",
                "O" if employee.participates else "",
                "O" if employee.is_pm_or_pl else "",
            ]
            for col_idx, value in enumerate(fixed_values, start=1):
                sheet.cell(row=excel_row, column=col_idx, value=value)

            for block_idx, project in enumerate(self._projects):
                cell = self._read_current_cell(row_idx, block_idx)
                start_col = FROZEN_COL_COUNT + SCROLL_FIXED_COL_COUNT + block_idx * BLOCK_SIZE + 1
                row_values = [
                    "O" if cell.participate else "",
                    cell.role_name,
                    "O" if cell.resident else "",
                    "O" if cell.non_resident else "",
                    cell.remark,
                ]
                for offset, value in enumerate(row_values):
                    sheet.cell(row=excel_row, column=start_col + offset, value=value)

        for col_idx in range(1, total_cols + 1):
            sheet.column_dimensions[sheet.cell(row=header_row, column=col_idx).column_letter].width = 14

        workbook.save(path)
