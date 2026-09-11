from collections import Counter
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
)
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from app.auth import AuthenticatedUser
from app.config import AppConfig
from app.queries.project_manpower import (
    ParticipationRow,
    ProjectMeta,
    add_participant,
    ensure_table_exists,
    get_active_employees,
    get_employee_grades,
    get_grade_options,
    get_participation_rows,
    get_role_options,
    get_tracked_projects,
    participation_exists,
    remove_participant,
    save_employee_grades,
    save_participation_rows,
    search_employees,
    search_projects,
)
from app.ui.table_utils import NumericTableWidgetItem, enable_header_sorting
from app.ui.theme import POPUP_GRID_FONT_PX, POPUP_HEIGHT, POPUP_WIDTH, current_theme

_NO_ROLE_LABEL = "(선택 안 함)"
_NO_GRADE_LABEL = "(선택 안 함)"
_NO_RESIDENCE_LABEL = "(선택 안 함)"
_ROW_HEIGHT = 30

RESIDENCE_OPTIONS = ["상주", "비상주"]
RATE_OPTIONS = list(range(0, 101, 5))  # 0%, 5%, ..., 100%

# 목록(투입률) 보기에서 같은 사람이 2개 이상의 프로젝트에 중복 참여 중일 때 성명 칸을
# 분홍색으로 강조하기 위한 색상 (100% 초과 경고에 쓰는 빨간색과는 다른 색으로 구분)
_DUPLICATE_NAME_BG = "#FCE0EE"
_DUPLICATE_NAME_TEXT = "#B0266F"

# 목록 보기(첨부 엑셀 시트01 기준) 고정 컬럼. 월 컬럼 개수는 사용자가 고른 조회기간
# (시작 연/월 ~ 종료 연/월)에 따라 가변적이라 모듈 상수로 고정하지 않는다.
LIST_COLUMNS = ["순번", "사업명", "발주처", "사업기간", "성명", "상주/비상주", "역할", "투입률(합계)"]
LIST_FIXED_COL_COUNT = len(LIST_COLUMNS)

WBS_FIXED_COLUMNS = ["성명", "역할"]
WBS_FIXED_COL_COUNT = len(WBS_FIXED_COLUMNS)

PERSON_FIXED_COLUMNS = ["순번", "소속", "직위", "이름", "입사일"]
PERSON_FIXED_COL_COUNT = len(PERSON_FIXED_COLUMNS)


def _period_months(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> list[tuple[int, int]]:
    """조회기간(시작 연/월 ~ 종료 연/월)을 아우르는 (연,월) 목록을 만든다."""
    months: list[tuple[int, int]] = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _fitted_width(metrics: QFontMetrics, texts: list[str], padding: int, min_width: int, max_width: int) -> int:
    """텍스트 목록 중 가장 긴 것의 실제 렌더링 폭을 재서 컬럼 폭을 계산한다. "2026.11월"처럼
    연도가 붙어 길어진 헤더가 고정폭 컬럼에서 잘리지 않도록 한다."""
    widest = max((metrics.horizontalAdvance(t) for t in texts), default=0)
    return max(min_width, min(widest + padding, max_width))


def _build_choice_combo(options: list[str], no_choice_label: str, current: str | None) -> QComboBox:
    combo = QComboBox()
    combo.addItem(no_choice_label, None)
    selected_index = 0
    for idx, option in enumerate(options, start=1):
        combo.addItem(option, option)
        if option == current:
            selected_index = idx
    combo.setCurrentIndex(selected_index)
    return combo


def _build_code_combo(
    options: list[tuple[str, str]], no_choice_label: str, current_code: str | None
) -> QComboBox:
    combo = QComboBox()
    combo.addItem(no_choice_label, None)
    selected_index = 0
    for idx, (code, name) in enumerate(options, start=1):
        combo.addItem(name, code)
        if code == current_code:
            selected_index = idx
    combo.setCurrentIndex(selected_index)
    return combo


class _AddParticipantDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = app_config
        self.selected_prj_id: str | None = None
        self.selected_empl_id: str | None = None

        self.setWindowTitle("참여자 추가")
        self.resize(620, 600)

        project_label = QLabel("프로젝트 선택")
        project_label.setProperty("role", "secondary")
        self._project_search = QLineEdit()
        self._project_search.setPlaceholderText("프로젝트명, 발주기관, 코드로 검색 (예: 한국도로공사)")
        self._project_search.textChanged.connect(self._on_project_search_changed)
        self._project_list = QListWidget()
        self._project_list.setMaximumHeight(200)
        self._project_list.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")

        employee_label = QLabel("직원 선택")
        employee_label.setProperty("role", "secondary")
        self._employee_search = QLineEdit()
        self._employee_search.setPlaceholderText("이름으로 검색")
        self._employee_search.textChanged.connect(self._on_employee_search_changed)
        self._employee_list = QListWidget()
        self._employee_list.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")

        add_button = QPushButton("추가")
        add_button.clicked.connect(self._confirm)
        cancel_button = QPushButton("취소")
        cancel_button.setProperty("variant", "outline")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(add_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(project_label)
        layout.addWidget(self._project_search)
        layout.addWidget(self._project_list)
        layout.addWidget(employee_label)
        layout.addWidget(self._employee_search)
        layout.addWidget(self._employee_list)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self._project_search.setText("한국도로공사")
        self._on_project_search_changed("한국도로공사")
        self._on_employee_search_changed("")

    def _on_project_search_changed(self, keyword: str) -> None:
        keyword = keyword.strip()
        self._project_list.clear()
        if not keyword:
            return
        try:
            results = search_projects(self._config.database, keyword)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "검색 실패", f"프로젝트 검색에 실패했습니다.\n{exc}")
            return
        for prj_id, prj_name, client_name in results:
            item = QListWidgetItem(f"[{prj_id}] {prj_name}  ·  {client_name}")
            item.setData(Qt.ItemDataRole.UserRole, prj_id)
            self._project_list.addItem(item)

    def _on_employee_search_changed(self, keyword: str) -> None:
        self._employee_list.clear()
        try:
            results = search_employees(self._config.database, keyword.strip())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "검색 실패", f"직원 검색에 실패했습니다.\n{exc}")
            return
        for empl_id, name, dept in results:
            item = QListWidgetItem(f"{name}  ·  {dept}")
            item.setData(Qt.ItemDataRole.UserRole, empl_id)
            self._employee_list.addItem(item)

    def _confirm(self) -> None:
        project_item = self._project_list.currentItem()
        employee_item = self._employee_list.currentItem()
        if project_item is None or employee_item is None:
            QMessageBox.warning(self, "참여자 추가", "프로젝트와 직원을 모두 선택해 주세요.")
            return
        self.selected_prj_id = project_item.data(Qt.ItemDataRole.UserRole)
        self.selected_empl_id = employee_item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class _EmployeeGradeDialog(QDialog):
    """직원별 기술등급(대외/제안서, S/W자격증) 관리. 예전엔 매트릭스 보기의 컬럼이었으나,
    입력화면을 참여 목록형으로 바꾸면서 별도 화면으로 분리했다."""

    def __init__(self, app_config: AppConfig, current_empl_id: str, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._current_empl_id = current_empl_id
        self._employees = []
        self._grade_options: list[tuple[str, str]] = []

        self.setWindowTitle("기술등급 관리")
        self.resize(640, 640)

        title = QLabel("기술등급 관리")
        title.setProperty("role", "title")

        save_button = QPushButton("저장")
        save_button.clicked.connect(self._on_save)

        header_row = QHBoxLayout()
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(save_button)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["성명", "부서", "기술등급\n(대외/제안서)", "기술등급\n(S/W자격증)"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._table.setColumnWidth(0, 90)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 150)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header_row)
        layout.addWidget(self._table)
        self.setLayout(layout)

        self._load()

    def _load(self) -> None:
        try:
            self._employees = get_active_employees(self._config.database)
            self._grade_options = get_grade_options(self._config.database)
            grades = get_employee_grades(self._config.database)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "조회 실패", f"기술등급 정보 조회에 실패했습니다.\n{exc}")
            return

        self._table.setRowCount(len(self._employees))
        for row_idx, employee in enumerate(self._employees):
            name_item = QTableWidgetItem(employee.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row_idx, 0, name_item)

            dept_item = QTableWidgetItem(employee.dept)
            dept_item.setFlags(dept_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row_idx, 1, dept_item)

            grade_external_div, grade_sw_div = grades.get(employee.empl_id, (None, None))
            self._table.setCellWidget(
                row_idx, 2, _build_code_combo(self._grade_options, _NO_GRADE_LABEL, grade_external_div)
            )
            self._table.setCellWidget(
                row_idx, 3, _build_code_combo(self._grade_options, _NO_GRADE_LABEL, grade_sw_div)
            )
            self._table.setRowHeight(row_idx, _ROW_HEIGHT)

    def _on_save(self) -> None:
        updates = []
        for row_idx, employee in enumerate(self._employees):
            grade_external_combo = self._table.cellWidget(row_idx, 2)
            grade_sw_combo = self._table.cellWidget(row_idx, 3)
            updates.append(
                (
                    employee.empl_id,
                    grade_external_combo.currentData() if grade_external_combo else None,
                    grade_sw_combo.currentData() if grade_sw_combo else None,
                )
            )
        try:
            save_employee_grades(self._config.database, updates, self._current_empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"저장에 실패했습니다.\n{exc}")
            return
        QMessageBox.information(self, "저장", "저장되었습니다.")


class ProjectManpowerDialog(QDialog):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._user = user
        self._role_options: list[tuple[str, str]] = []
        self._participation_rows: list[ParticipationRow] = []
        self._active_employees = []
        self._projects: list[ProjectMeta] = []
        self._month_combo_refs: list[list[QComboBox]] = []
        self._period_months_list: list[tuple[int, int]] = []
        current_year = date.today().year
        self._start_year, self._start_month = current_year, 1
        self._end_year, self._end_month = current_year, 12

        self.setWindowTitle("한국도로공사 투입인력관리")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(POPUP_WIDTH, POPUP_HEIGHT)

        title_label = QLabel("한국도로공사 투입인력관리")
        title_label.setProperty("role", "title")

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")

        self._list_radio = QRadioButton("목록(투입률) 보기")
        self._list_radio.setChecked(True)
        self._wbs_radio = QRadioButton("WBS(월별) 보기")
        self._person_radio = QRadioButton("사람기준 보기")
        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.addButton(self._list_radio)
        self._view_mode_group.addButton(self._wbs_radio)
        self._view_mode_group.addButton(self._person_radio)
        self._list_radio.toggled.connect(self._on_view_mode_changed)
        self._wbs_radio.toggled.connect(self._on_view_mode_changed)
        self._person_radio.toggled.connect(self._on_view_mode_changed)

        def _build_year_combo() -> QComboBox:
            combo = QComboBox()
            for year in range(current_year - 1, current_year + 4):
                combo.addItem(f"{year}년", year)
            return combo

        def _build_month_combo() -> QComboBox:
            combo = QComboBox()
            for month in range(1, 13):
                combo.addItem(f"{month}월", month)
            return combo

        self._start_year_combo = _build_year_combo()
        self._start_year_combo.setCurrentIndex(self._start_year_combo.findData(self._start_year))
        self._start_month_combo = _build_month_combo()
        self._start_month_combo.setCurrentIndex(self._start_month_combo.findData(self._start_month))
        self._end_year_combo = _build_year_combo()
        self._end_year_combo.setCurrentIndex(self._end_year_combo.findData(self._end_year))
        self._end_month_combo = _build_month_combo()
        self._end_month_combo.setCurrentIndex(self._end_month_combo.findData(self._end_month))

        search_period_button = QPushButton("조회")
        search_period_button.setProperty("variant", "secondary")
        search_period_button.clicked.connect(self._on_search_period)

        refresh_button = QPushButton("새로고침")
        refresh_button.setProperty("variant", "secondary")
        refresh_button.clicked.connect(self._load_data)

        add_participant_button = QPushButton("+ 참여자 추가")
        add_participant_button.setProperty("variant", "secondary")
        add_participant_button.clicked.connect(self._on_add_participant)

        grade_button = QPushButton("기술등급 관리")
        grade_button.setProperty("variant", "secondary")
        grade_button.clicked.connect(self._on_manage_grades)

        export_button = QPushButton("엑셀로 저장")
        export_button.setProperty("variant", "secondary")
        export_button.clicked.connect(self._export_to_excel)

        self._save_button = QPushButton("저장")
        self._save_button.clicked.connect(self._on_save)

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addSpacing(20)
        header_row.addWidget(self._list_radio)
        header_row.addWidget(self._wbs_radio)
        header_row.addWidget(self._person_radio)
        header_row.addSpacing(12)
        header_row.addWidget(QLabel("조회기간:"))
        header_row.addWidget(self._start_year_combo)
        header_row.addWidget(self._start_month_combo)
        header_row.addWidget(QLabel("~"))
        header_row.addWidget(self._end_year_combo)
        header_row.addWidget(self._end_month_combo)
        header_row.addWidget(search_period_button)
        header_row.addStretch()
        header_row.addWidget(refresh_button)
        header_row.addWidget(add_participant_button)
        header_row.addWidget(grade_button)
        header_row.addWidget(export_button)
        header_row.addWidget(self._save_button)

        # 목록(투입률) 보기 — 첨부 엑셀 시트01과 동일: 한 행 = 직원 1명의 프로젝트 1건 참여
        self._list_table = QTableWidget()
        self._list_table.verticalHeader().setVisible(False)
        self._list_table.setAlternatingRowColors(True)
        self._list_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._list_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._list_table.horizontalHeader().setStretchLastSection(True)
        self._list_table.setMinimumHeight(560)
        self._list_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_table.customContextMenuRequested.connect(self._on_row_context_menu)
        self._list_table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        # 헤더 클릭 정렬은 넣지 않는다 — 이 표는 콤보박스가 셀 위젯으로 꽂혀 있고
        # "저장" 버튼이 화면 행 순서(row_idx)로 원본 데이터를 찾아가는데, 정렬로
        # 행 순서가 바뀌면 엉뚱한 행에 저장되는 사고로 이어진다.

        # WBS(월별) 보기 — 프로젝트별 헤더 행 + 참여 직원의 계약기간을 월별 막대로 표시
        self._wbs_table = QTableWidget()
        self._wbs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._wbs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._wbs_table.verticalHeader().setVisible(False)
        self._wbs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._wbs_table.setMinimumHeight(560)
        self._wbs_table.setAlternatingRowColors(True)
        self._wbs_table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        # 헤더 클릭 정렬 없음 — 프로젝트명 헤더 행 밑에 그 프로젝트 참여자 행들이
        # 묶여 있는 구조라, 정렬하면 헤더 행과 데이터 행이 뒤섞여 의미가 없어진다.

        # 사람기준 보기 — 직원별로 참여 중인 프로젝트마다 한 행, 계약기간을 월별
        # 막대로 표시한다("프로젝트 현황(사람기준).xlsx" 레이아웃 참조).
        self._person_table = QTableWidget()
        self._person_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._person_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._person_table.verticalHeader().setVisible(False)
        self._person_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._person_table.setMinimumHeight(560)
        self._person_table.setAlternatingRowColors(True)
        self._person_table.setStyleSheet(f"font-size: {POPUP_GRID_FONT_PX}px;")
        enable_header_sorting(self._person_table)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._list_table)
        self._view_stack.addWidget(self._wbs_table)
        self._view_stack.addWidget(self._person_table)

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

    def _on_view_mode_changed(self, checked: bool) -> None:
        if not checked:
            return
        if self._list_radio.isChecked():
            index = 0
        elif self._wbs_radio.isChecked():
            index = 1
        else:
            index = 2
        self._view_stack.setCurrentIndex(index)
        self._save_button.setEnabled(index == 0)

    def _on_search_period(self) -> None:
        start_year = self._start_year_combo.currentData()
        start_month = self._start_month_combo.currentData()
        end_year = self._end_year_combo.currentData()
        end_month = self._end_month_combo.currentData()
        if (start_year, start_month) > (end_year, end_month):
            QMessageBox.warning(self, "조회기간", "시작 연월이 종료 연월보다 늦을 수 없습니다.")
            return

        self._start_year, self._start_month = start_year, start_month
        self._end_year, self._end_month = end_year, end_month
        self._load_data()

    # ------------------------------------------------------------------
    # 데이터 로드
    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        self._period_months_list = _period_months(
            self._start_year, self._start_month, self._end_year, self._end_month
        )
        try:
            self._role_options = get_role_options(self._config.database)
            self._participation_rows = get_participation_rows(
                self._config.database, self._start_year, self._start_month, self._end_year, self._end_month
            )
            self._active_employees = get_active_employees(self._config.database)
            self._projects = get_tracked_projects(self._config.database)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "조회 실패", f"투입인력 정보 조회에 실패했습니다.\n{exc}")
            return

        self._build_list_table()
        self._build_wbs_table()
        self._build_person_table()
        self._status_label.setText(
            f"참여 {len(self._participation_rows)}건 · 프로젝트 {len(self._projects)}건 · "
            f"{self._start_year}.{self._start_month:02d} ~ {self._end_year}.{self._end_month:02d} 기준"
        )

    # ------------------------------------------------------------------
    # 목록(투입률) 보기
    # ------------------------------------------------------------------
    def _compute_list_column_widths(
        self, rows: list[ParticipationRow], month_headers: list[str]
    ) -> list[int]:
        """헤더 텍스트/드롭다운 옵션 중 가장 긴 것에 맞춰 컬럼 폭을 계산한다. 조회기간이
        연도를 걸치면 월 헤더가 "2026.11월"처럼 길어지므로, 고정폭 대신 실제 내용
        길이를 재서 잘리지 않게 한다."""
        cell_metrics = QFontMetrics(self._list_table.font())
        header_metrics = QFontMetrics(self._list_table.horizontalHeader().font())

        def widest(texts: list[str], header_text: str, padding: int, min_width: int, max_width: int) -> int:
            candidates = [cell_metrics.horizontalAdvance(t) for t in texts]
            candidates.append(header_metrics.horizontalAdvance(header_text))
            return max(min_width, min(max(candidates, default=0) + padding, max_width))

        period_texts = [f"{p.start_date} ~ {p.end_date}" for p in rows] or ["9999-99-99 ~ 9999-99-99"]
        client_texts = [p.client_name for p in rows] or ["발주처"]
        name_texts = [p.empl_name for p in rows] or ["성명"]
        role_texts = [_NO_ROLE_LABEL] + [name for _, name in self._role_options]
        resdng_texts = [_NO_RESIDENCE_LABEL] + RESIDENCE_OPTIONS
        month_option_texts = [f"{value}%" for value in RATE_OPTIONS]
        widest_month_header = max(month_headers, key=len, default="2026.12월")

        return [
            widest(["999"], "순번", 24, 46, 70),
            260,  # 사업명
            widest(client_texts, "발주처", 24, 90, 220),
            widest(period_texts, "사업기간", 28, 150, 220),
            widest(name_texts, "성명", 24, 60, 120),
            widest(resdng_texts, "상주/비상주", 40, 100, 170),  # +콤보 드롭다운 화살표 여유
            widest(role_texts, "역할", 40, 100, 190),
            widest(["100.0%"], "투입률(합계)", 24, 100, 140),
            widest(month_option_texts, widest_month_header, 34, 65, 115),
        ]

    def _build_list_table(self) -> None:
        rows = self._participation_rows
        months = self._period_months_list
        remark_col = LIST_FIXED_COL_COUNT + len(months)

        self._list_table.clear()
        self._list_table.setColumnCount(remark_col + 1)
        month_headers = [f"{y}.{m}월" for y, m in months]
        headers = list(LIST_COLUMNS) + month_headers + ["비고"]
        self._list_table.setHorizontalHeaderLabels(headers)

        widths = self._compute_list_column_widths(rows, month_headers)
        for col_idx, width in enumerate(widths[:LIST_FIXED_COL_COUNT]):
            self._list_table.setColumnWidth(col_idx, width)
        for col in range(LIST_FIXED_COL_COUNT, remark_col):
            self._list_table.setColumnWidth(col, widths[LIST_FIXED_COL_COUNT])
        self._list_table.setColumnWidth(remark_col, 180)

        self._list_table.setRowCount(len(rows))
        self._month_combo_refs = []

        empl_project_counts = Counter(prow.empl_id for prow in rows)

        for row_idx, prow in enumerate(rows):
            self._list_table.setRowHeight(row_idx, _ROW_HEIGHT)

            readonly_values = {
                0: str(row_idx + 1),
                1: prow.prj_name,
                2: prow.client_name,
                3: f"{prow.start_date} ~ {prow.end_date}",
                4: prow.empl_name,
            }
            for col_idx, text in readonly_values.items():
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 4 and empl_project_counts[prow.empl_id] > 1:
                    # 같은 사람이 여러 프로젝트에 중복 참여 중임을 눈에 띄게 표시
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor(_DUPLICATE_NAME_BG))
                    item.setForeground(QColor(_DUPLICATE_NAME_TEXT))
                self._list_table.setItem(row_idx, col_idx, item)

            resdng_combo = _build_choice_combo(RESIDENCE_OPTIONS, _NO_RESIDENCE_LABEL, prow.resdng_div)
            self._list_table.setCellWidget(row_idx, 5, resdng_combo)

            role_combo = _build_code_combo(self._role_options, _NO_ROLE_LABEL, prow.role_div)
            self._list_table.setCellWidget(row_idx, 6, role_combo)

            total_item = QTableWidgetItem("")
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setBold(True)
            total_item.setFont(font)
            self._list_table.setItem(row_idx, 7, total_item)

            month_combos: list[QComboBox] = []
            for offset, (year, month) in enumerate(months):
                yyyymm = f"{year:04d}{month:02d}"
                percent = prow.monthly_rates.get(yyyymm, 0)
                combo = QComboBox()
                for value in RATE_OPTIONS:
                    combo.addItem(f"{value}%", value)
                combo.setCurrentIndex(RATE_OPTIONS.index(percent) if percent in RATE_OPTIONS else 0)
                self._apply_rate_combo_style(combo)
                combo.currentIndexChanged.connect(
                    lambda _idx, r=row_idx, c=combo: self._on_month_rate_changed(r, c)
                )
                self._list_table.setCellWidget(row_idx, LIST_FIXED_COL_COUNT + offset, combo)
                month_combos.append(combo)
            self._month_combo_refs.append(month_combos)

            remark_item = QTableWidgetItem(prow.remark)
            self._list_table.setItem(row_idx, remark_col, remark_item)

            self._recompute_total(row_idx)

    def _apply_rate_combo_style(self, combo: QComboBox) -> None:
        """월별 투입률 드롭다운이 0%일 때 흐린 회색 글자로 표시해 실제 투입 중인 달과
        구분되게 한다."""
        if combo.currentData() == 0:
            theme = current_theme()
            combo.setStyleSheet(f"QComboBox {{ color: {theme.text_secondary}; }}")
        else:
            combo.setStyleSheet("")

    def _on_month_rate_changed(self, row_idx: int, combo: QComboBox) -> None:
        self._apply_rate_combo_style(combo)
        self._recompute_total(row_idx)

    def _recompute_total(self, row_idx: int) -> None:
        if row_idx >= len(self._month_combo_refs):
            return
        combos = self._month_combo_refs[row_idx]
        values = [combo.currentData() for combo in combos]
        avg = sum(values) / len(values) if values else 0
        item = self._list_table.item(row_idx, 7)
        if item:
            item.setText(f"{avg:.1f}%")
            theme = current_theme()
            item.setForeground(QColor(theme.text_secondary if avg == 0 else theme.text_primary))

    def _read_current_row(
        self, row_idx: int
    ) -> tuple[str | None, str | None, str, dict[str, int]]:
        resdng_combo = self._list_table.cellWidget(row_idx, 5)
        role_combo = self._list_table.cellWidget(row_idx, 6)
        remark_col = LIST_FIXED_COL_COUNT + len(self._period_months_list)
        remark_item = self._list_table.item(row_idx, remark_col)
        monthly = {
            f"{year:04d}{month:02d}": combo.currentData()
            for (year, month), combo in zip(self._period_months_list, self._month_combo_refs[row_idx])
        }
        return (
            resdng_combo.currentData() if resdng_combo else None,
            role_combo.currentData() if role_combo else None,
            remark_item.text().strip() if remark_item else "",
            monthly,
        )

    # ------------------------------------------------------------------
    # 참여자 추가 / 삭제
    # ------------------------------------------------------------------
    def _on_add_participant(self) -> None:
        dialog = _AddParticipantDialog(self._config, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.selected_prj_id or not dialog.selected_empl_id:
            return

        try:
            already_exists = participation_exists(
                self._config.database, dialog.selected_prj_id, dialog.selected_empl_id
            )
            if already_exists:
                QMessageBox.information(self, "참여자 추가", "이미 참여 중인 직원입니다.")
                return
            add_participant(
                self._config.database, dialog.selected_prj_id, dialog.selected_empl_id, self._user.empl_id
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "추가 실패", f"참여자 추가에 실패했습니다.\n{exc}")
            return

        self._load_data()

    def _on_row_context_menu(self, pos) -> None:
        row = self._list_table.rowAt(pos.y())
        if row < 0 or row >= len(self._participation_rows):
            return
        prow = self._participation_rows[row]

        menu = QMenu(self)
        delete_action = menu.addAction(f"{prow.empl_name} - '{prow.prj_name}' 참여 삭제")
        chosen = menu.exec(self._list_table.viewport().mapToGlobal(pos))
        if chosen == delete_action:
            self._on_delete_participant(prow)

    def _on_delete_participant(self, prow: ParticipationRow) -> None:
        reply = QMessageBox.question(
            self,
            "참여 삭제",
            f"'{prow.empl_name}'님의 '{prow.prj_name}' 참여 정보를 삭제할까요?\n"
            "저장된 월별 투입률 데이터도 함께 삭제됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            remove_participant(self._config.database, prow.prj_id, prow.empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "삭제 실패", f"참여 삭제에 실패했습니다.\n{exc}")
            return

        self._load_data()

    # ------------------------------------------------------------------
    # 기술등급 관리
    # ------------------------------------------------------------------
    def _on_manage_grades(self) -> None:
        dialog = _EmployeeGradeDialog(self._config, self._user.empl_id, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # 저장
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        if not self._participation_rows:
            QMessageBox.information(self, "저장", "저장할 데이터가 없습니다.")
            return

        updates = []
        for row_idx, prow in enumerate(self._participation_rows):
            resdng_div, role_div, remark, monthly = self._read_current_row(row_idx)
            updates.append((prow.prj_id, prow.empl_id, role_div, resdng_div, remark, monthly))

        try:
            save_participation_rows(self._config.database, updates, self._user.empl_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "저장", "저장되었습니다.")
        self._load_data()

    # ------------------------------------------------------------------
    # WBS(월별) 보기 — 프로젝트명 헤더 행 다음에 참여 직원(성명/역할) 행이 이어지고,
    # 그 직원의 실제 입력된 월별 투입률이 5% 이상인 달만 색칠된 막대로 표시한다
    # (계약기간이 아니라 목록 보기에서 실제로 입력한 투입률 기준).
    # ------------------------------------------------------------------
    _WBS_MIN_RATE = 5

    def _wbs_row_spec(self) -> list[tuple[str, str, str, dict[str, int]]]:
        """(kind, 텍스트/성명, 역할, 월별투입률) 목록. kind는 'header' 또는 'data'."""
        rows: list[tuple[str, str, str, dict[str, int]]] = []
        members_by_project: dict[str, list[ParticipationRow]] = {}
        project_order: list[str] = []
        for prow in self._participation_rows:
            if prow.prj_id not in members_by_project:
                members_by_project[prow.prj_id] = []
                project_order.append(prow.prj_id)
            members_by_project[prow.prj_id].append(prow)

        for prj_id in project_order:
            members = members_by_project[prj_id]
            rows.append(("header", members[0].prj_name, "", {}))
            for prow in members:
                rows.append(("data", prow.empl_name, prow.role_name, prow.monthly_rates))
        return rows

    def _build_wbs_table(self) -> None:
        theme = current_theme()
        months = self._period_months_list
        rows_spec = self._wbs_row_spec()
        month_headers = [f"{y}.{m}월" for y, m in months]

        self._wbs_table.clear()
        self._wbs_table.setColumnCount(WBS_FIXED_COL_COUNT + len(months))
        self._wbs_table.setHorizontalHeaderLabels(WBS_FIXED_COLUMNS + month_headers)
        self._wbs_table.setColumnWidth(0, 90)
        self._wbs_table.setColumnWidth(1, 90)
        header_metrics = QFontMetrics(self._wbs_table.horizontalHeader().font())
        month_width = _fitted_width(header_metrics, month_headers or ["2026.12월"], 24, 55, 100)
        for col in range(WBS_FIXED_COL_COUNT, WBS_FIXED_COL_COUNT + len(months)):
            self._wbs_table.setColumnWidth(col, month_width)

        self._wbs_table.setRowCount(len(rows_spec))
        for row_idx, (kind, name, role, monthly_rates) in enumerate(rows_spec):
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

            for offset, (y, m) in enumerate(months):
                rate = monthly_rates.get(f"{y:04d}{m:02d}", 0)
                bar_item = QTableWidgetItem(f"{rate}%")
                bar_item.setFlags(bar_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                bar_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if rate >= self._WBS_MIN_RATE:
                    bar_font = QFont()
                    bar_font.setBold(True)
                    bar_item.setFont(bar_font)
                    bar_item.setBackground(QColor(theme.accent))
                    bar_item.setForeground(QColor(theme.accent_text))
                elif rate == 0:
                    bar_item.setForeground(QColor(theme.text_secondary))
                self._wbs_table.setItem(row_idx, WBS_FIXED_COL_COUNT + offset, bar_item)

    # ------------------------------------------------------------------
    # 사람기준 보기 — 직원별 한 행, 월별 투입률은 그 직원이 참여 중인 모든 프로젝트의
    # 투입률 합계(100%를 넘으면 중복 투입 경고로 강조). 첨부 엑셀
    # "02.인력별 투입현황" 시트 레이아웃을 그대로 따른다. 조회기간(목록 보기와 동일한
    # 시작~종료 연/월) 기준으로 집계한다.
    # ------------------------------------------------------------------
    def _person_summary_rows(self):
        """직원별 (부서/직위/입사일 + 월별 투입률 합계 리스트 + 평균 + 참여 프로젝트 수)."""
        monthly_sums_by_empl: dict[str, dict[str, int]] = {}
        project_ids_by_empl: dict[str, set] = {}
        for prow in self._participation_rows:
            month_sums = monthly_sums_by_empl.setdefault(prow.empl_id, {})
            for yyyymm, percent in prow.monthly_rates.items():
                month_sums[yyyymm] = month_sums.get(yyyymm, 0) + percent
            project_ids_by_empl.setdefault(prow.empl_id, set()).add(prow.prj_id)

        months = self._period_months_list
        rows = []
        for employee in self._active_employees:
            month_sums = monthly_sums_by_empl.get(employee.empl_id, {})
            monthly_values = [month_sums.get(f"{y:04d}{m:02d}", 0) for y, m in months]
            avg = sum(monthly_values) / len(monthly_values) if monthly_values else 0
            project_count = len(project_ids_by_empl.get(employee.empl_id, ()))
            rows.append((employee, monthly_values, avg, project_count))
        return rows

    def _set_person_percent_cell(self, row_idx: int, col_idx: int, value: float) -> None:
        """투입률(평균)/월별 투입률 % 칸. 100%를 넘으면 빨간색으로, 0%면 흐린 회색으로
        표시해 "투입 없음"과 "실제 투입 중"이 한눈에 구분되게 한다."""
        item = NumericTableWidgetItem(f"{round(value)}%")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        theme = current_theme()
        if value > 100:
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QColor(theme.destructive))
            item.setBackground(QColor(theme.destructive).lighter(175))
        elif value == 0:
            item.setForeground(QColor(theme.text_secondary))
        self._person_table.setItem(row_idx, col_idx, item)

    def _set_person_count_cell(self, row_idx: int, col_idx: int, count: int, warn: bool) -> None:
        item = NumericTableWidgetItem(str(count))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        theme = current_theme()
        if warn:
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QColor(theme.destructive))
            item.setBackground(QColor(theme.destructive).lighter(175))
        elif count == 0:
            item.setForeground(QColor(theme.text_secondary))
        self._person_table.setItem(row_idx, col_idx, item)

    def _build_person_table(self) -> None:
        months = self._period_months_list
        avg_col = PERSON_FIXED_COL_COUNT
        month_start_col = avg_col + 1
        count_col = month_start_col + len(months)
        rows_spec = self._person_summary_rows()
        month_headers = [f"{y}.{m}월" for y, m in months]

        self._person_table.setSortingEnabled(False)
        self._person_table.clear()
        self._person_table.setColumnCount(count_col + 1)
        headers = list(PERSON_FIXED_COLUMNS) + ["투입률"] + month_headers + ["투입사업수"]
        self._person_table.setHorizontalHeaderLabels(headers)

        widths = [50, 130, 90, 80, 90, 80]
        for col_idx, width in enumerate(widths):
            self._person_table.setColumnWidth(col_idx, width)
        header_metrics = QFontMetrics(self._person_table.horizontalHeader().font())
        cell_metrics = QFontMetrics(self._person_table.font())
        month_width = max(
            _fitted_width(header_metrics, month_headers or ["2026.12월"], 24, 55, 100),
            _fitted_width(cell_metrics, ["100%", "150%", "200%"], 24, 55, 100),
        )
        for col in range(month_start_col, count_col):
            self._person_table.setColumnWidth(col, month_width)
        self._person_table.setColumnWidth(count_col, 80)

        self._person_table.setRowCount(len(rows_spec))
        for row_idx, (employee, monthly_values, avg, project_count) in enumerate(rows_spec):
            self._person_table.setRowHeight(row_idx, _ROW_HEIGHT)
            has_overflow = any(value > 100 for value in monthly_values)

            info_values = [
                str(row_idx + 1),
                employee.dept,
                employee.position,
                employee.name,
                employee.join_date,
            ]
            for col_idx, text in enumerate(info_values):
                item = NumericTableWidgetItem(text) if col_idx == 0 else QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._person_table.setItem(row_idx, col_idx, item)

            self._set_person_percent_cell(row_idx, avg_col, avg)
            for offset, value in enumerate(monthly_values):
                self._set_person_percent_cell(row_idx, month_start_col + offset, value)
            self._set_person_count_cell(row_idx, count_col, project_count, has_overflow)
        self._person_table.setSortingEnabled(True)

    # ------------------------------------------------------------------
    # 엑셀로 저장
    # ------------------------------------------------------------------
    def _export_to_excel(self) -> None:
        if not self._participation_rows and not self._active_employees:
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
            elif self._person_radio.isChecked():
                self._write_person_excel(path)
            else:
                self._write_list_excel(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"엑셀 파일 저장에 실패했습니다.\n{exc}")
            return

        QMessageBox.information(self, "엑셀로 저장", f"저장이 완료되었습니다.\n{path}")

    def _write_list_excel(self, path: str) -> None:
        months = self._period_months_list
        month_count = len(months)
        total_col_count = LIST_FIXED_COL_COUNT + month_count + 1

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "투입인력관리"

        headers = list(LIST_COLUMNS) + [f"{y}.{m}월" for y, m in months] + ["비고"]
        for col_idx, text in enumerate(headers, start=1):
            sheet.cell(row=1, column=col_idx, value=text)

        zero_font = Font(color="9AA0A6")
        duplicate_fill = PatternFill(start_color="FCE0EE", end_color="FCE0EE", fill_type="solid")
        duplicate_font = Font(color="B0266F", bold=True)
        empl_project_counts = Counter(prow.empl_id for prow in self._participation_rows)

        for row_idx, prow in enumerate(self._participation_rows):
            resdng_div, role_div, remark, monthly = self._read_current_row(row_idx)
            role_name = dict(self._role_options).get(role_div, "") if role_div else ""
            month_fractions = [monthly.get(f"{y:04d}{m:02d}", 0) / 100 for y, m in months]
            avg = sum(month_fractions) / month_count if month_fractions else 0

            excel_row = row_idx + 2
            row_values = [
                row_idx + 1,
                prow.prj_name,
                prow.client_name,
                f"{prow.start_date} ~ {prow.end_date}",
                prow.empl_name,
                resdng_div or "",
                role_name,
                avg,
            ] + month_fractions + [remark]
            for col_idx, value in enumerate(row_values, start=1):
                cell = sheet.cell(row=excel_row, column=col_idx, value=value)
                if col_idx == 8 or LIST_FIXED_COL_COUNT < col_idx <= LIST_FIXED_COL_COUNT + month_count:
                    cell.number_format = "0%"
                    if value == 0:
                        cell.font = zero_font
                if col_idx == 5 and empl_project_counts[prow.empl_id] > 1:
                    cell.fill = duplicate_fill
                    cell.font = duplicate_font

        sheet.column_dimensions["A"].width = 6
        sheet.column_dimensions["B"].width = 40
        sheet.column_dimensions["C"].width = 16
        sheet.column_dimensions["D"].width = 22
        sheet.column_dimensions["E"].width = 10
        sheet.column_dimensions["F"].width = 12
        sheet.column_dimensions["G"].width = 12
        sheet.column_dimensions["H"].width = 10
        for col_idx in range(LIST_FIXED_COL_COUNT + 1, total_col_count + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 9

        workbook.save(path)

    def _write_wbs_excel(self, path: str) -> None:
        months = self._period_months_list
        rows_spec = self._wbs_row_spec()
        total_cols = WBS_FIXED_COL_COUNT + len(months)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "투입인력 WBS"

        header_row = 1
        headers = WBS_FIXED_COLUMNS + [f"{y}.{m}월" for y, m in months]
        for col_idx, text in enumerate(headers, start=1):
            sheet.cell(row=header_row, column=col_idx, value=text)

        header_fill = PatternFill(start_color="31379E", end_color="31379E", fill_type="solid")
        bar_fill = PatternFill(start_color="5678FF", end_color="5678FF", fill_type="solid")
        bar_font = Font(color="FFFFFF", bold=True)
        zero_font = Font(color="9AA0A6")

        for row_idx, (kind, name, role, monthly_rates) in enumerate(rows_spec, start=1):
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
            for offset, (y, m) in enumerate(months):
                rate = monthly_rates.get(f"{y:04d}{m:02d}", 0)
                cell = sheet.cell(row=excel_row, column=WBS_FIXED_COL_COUNT + 1 + offset, value=rate / 100)
                cell.number_format = "0%"
                if rate >= self._WBS_MIN_RATE:
                    cell.fill = bar_fill
                    cell.font = bar_font
                elif rate == 0:
                    cell.font = zero_font

        sheet.column_dimensions["A"].width = 14
        sheet.column_dimensions["B"].width = 10
        for col_idx in range(WBS_FIXED_COL_COUNT + 1, total_cols + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 9

        workbook.save(path)

    def _write_person_excel(self, path: str) -> None:
        months = self._period_months_list
        rows_spec = self._person_summary_rows()
        total_cols = PERSON_FIXED_COL_COUNT + 1 + len(months) + 1

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "사람기준 현황"

        headers = list(PERSON_FIXED_COLUMNS) + ["투입률"] + [f"{y}.{m}월" for y, m in months] + ["투입사업수"]
        for col_idx, text in enumerate(headers, start=1):
            sheet.cell(row=1, column=col_idx, value=text)

        warn_fill = PatternFill(start_color="FDE2E2", end_color="FDE2E2", fill_type="solid")
        warn_font = Font(color="C0392B", bold=True)
        zero_font = Font(color="9AA0A6")

        for row_idx, (employee, monthly_values, avg, project_count) in enumerate(rows_spec, start=1):
            excel_row = 1 + row_idx
            has_overflow = any(value > 100 for value in monthly_values)

            info_values = [row_idx, employee.dept, employee.position, employee.name, employee.join_date]
            for col_idx, value in enumerate(info_values, start=1):
                sheet.cell(row=excel_row, column=col_idx, value=value)

            avg_col = PERSON_FIXED_COL_COUNT + 1
            avg_cell = sheet.cell(row=excel_row, column=avg_col, value=round(avg) / 100)
            avg_cell.number_format = "0%"
            if avg > 100:
                avg_cell.fill = warn_fill
                avg_cell.font = warn_font
            elif avg == 0:
                avg_cell.font = zero_font

            for offset, value in enumerate(monthly_values):
                cell = sheet.cell(row=excel_row, column=avg_col + 1 + offset, value=value / 100)
                cell.number_format = "0%"
                if value > 100:
                    cell.fill = warn_fill
                    cell.font = warn_font
                elif value == 0:
                    cell.font = zero_font

            count_cell = sheet.cell(row=excel_row, column=total_cols, value=project_count)
            if has_overflow:
                count_cell.fill = warn_fill
                count_cell.font = warn_font
            elif project_count == 0:
                count_cell.font = zero_font

        sheet.column_dimensions["A"].width = 6
        sheet.column_dimensions["B"].width = 16
        sheet.column_dimensions["C"].width = 10
        sheet.column_dimensions["D"].width = 10
        sheet.column_dimensions["E"].width = 12
        for col_idx in range(PERSON_FIXED_COL_COUNT + 1, total_cols + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 9

        workbook.save(path)
