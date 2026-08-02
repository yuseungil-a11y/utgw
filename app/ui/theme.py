"""라이트/다크 모드를 지원하는 공용 디자인 토큰 + 전역 스타일시트.

카드형 패널, 둥근 버튼/입력창, 통일된 테이블 스타일 등 화면 전체에서 재사용하는
"최신 SaaS 대시보드" 톤의 컴포넌트 스타일을 한 곳에서 정의한다. 개별 화면은 색상을
직접 하드코딩하지 않고 이 모듈의 Theme 값을 참조한다.
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str  # 앱 전체 배경
    surface: str  # 카드/패널/입력창 배경
    surface_alt: str  # 살짝 다른 톤의 패널 (좌측 메뉴, 테이블 헤더)
    border: str
    text_primary: str
    text_secondary: str
    accent: str  # 브랜드 네이비 (버튼/상단바/선택 강조)
    accent_hover: str
    accent_pressed: str
    accent_text: str  # accent 배경 위 글자색
    hover: str  # 리스트/트리 항목 위에 마우스를 올렸을 때 배경
    chart_bg: str
    chart_text: str
    sales_badge_bg: str  # 매출 배지 배경
    sales_badge_text: str
    purchase_badge_bg: str  # 매입 배지 배경
    purchase_badge_text: str


LIGHT = Theme(
    name="light",
    bg="#F3F4F8",
    surface="#FFFFFF",
    surface_alt="#F5F6FA",
    border="#E3E5EC",
    text_primary="#1A1A2E",
    text_secondary="#70728C",
    accent="#1E2761",
    accent_hover="#293475",
    accent_pressed="#161C49",
    accent_text="#FFFFFF",
    hover="#E8ECFB",
    chart_bg="#FFFFFF",
    chart_text="#1A1A2E",
    sales_badge_bg="#E1EAFC",
    sales_badge_text="#1D4ED8",
    purchase_badge_bg="#FDECD8",
    purchase_badge_text="#B45309",
)

DARK = Theme(
    name="dark",
    bg="#1B1C24",
    surface="#25262F",
    surface_alt="#21222B",
    border="#34353F",
    text_primary="#F1F2F7",
    text_secondary="#9A9CB0",
    accent="#4356B0",
    accent_hover="#4F63C7",
    accent_pressed="#374799",
    accent_text="#FFFFFF",
    hover="#31334A",
    chart_bg="#25262F",
    chart_text="#F1F2F7",
    sales_badge_bg="#22314F",
    sales_badge_text="#8FB8FF",
    purchase_badge_bg="#4A3420",
    purchase_badge_text="#FFC98B",
)


def current_theme() -> Theme:
    scheme = QGuiApplication.styleHints().colorScheme()
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def build_app_qss(theme: Theme) -> str:
    return f"""
QWidget {{
    background-color: {theme.bg};
    color: {theme.text_primary};
    font-size: 13px;
}}
QToolTip {{
    background-color: {theme.surface};
    color: {theme.text_primary};
    border: 1px solid {theme.border};
}}
QLabel {{
    background: transparent;
}}
QLabel[role="title"] {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel[role="secondary"] {{
    color: {theme.text_secondary};
    font-size: 11px;
}}
QWidget[role="card"] {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: 14px;
}}
QPushButton {{
    background-color: {theme.accent};
    color: {theme.accent_text};
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {theme.accent_hover};
}}
QPushButton:pressed {{
    background-color: {theme.accent_pressed};
}}
QPushButton:disabled {{
    background-color: {theme.border};
    color: {theme.text_secondary};
}}
QPushButton[variant="secondary"] {{
    background-color: {theme.surface};
    color: {theme.text_primary};
    border: 1px solid {theme.border};
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {theme.hover};
}}
QPushButton[variant="secondary"]:pressed {{
    background-color: {theme.border};
}}
QLineEdit, QDateEdit {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: 8px;
    padding: 7px 10px;
    color: {theme.text_primary};
    selection-background-color: {theme.accent};
    selection-color: {theme.accent_text};
}}
QLineEdit:focus, QDateEdit:focus {{
    border: 1px solid {theme.accent};
}}
QCheckBox {{
    color: {theme.text_primary};
    spacing: 8px;
}}
QDialog {{
    background-color: {theme.bg};
}}
QTableWidget {{
    background-color: {theme.surface};
    alternate-background-color: {theme.surface_alt};
    gridline-color: {theme.border};
    border: 1px solid {theme.border};
    border-radius: 10px;
    color: {theme.text_primary};
}}
QTableWidget::item {{
    padding: 4px;
}}
QTableWidget::item:selected {{
    background-color: {theme.hover};
    color: {theme.text_primary};
}}
QHeaderView::section {{
    background-color: {theme.surface_alt};
    color: {theme.text_secondary};
    padding: 8px 6px;
    border: none;
    border-bottom: 1px solid {theme.border};
    font-weight: 600;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {theme.border};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {theme.border};
    border-radius: 5px;
    min-width: 24px;
}}
"""


def build_menu_tree_qss(theme: Theme) -> str:
    return f"""
QTreeWidget {{
    background-color: {theme.surface_alt};
    color: {theme.text_primary};
    border: none;
    outline: none;
    font-size: 13px;
}}
QTreeWidget::item {{
    height: 34px;
    padding-left: 4px;
    color: {theme.text_primary};
    border-radius: 8px;
}}
QTreeWidget::item:hover {{
    background-color: {theme.hover};
    color: {theme.text_primary};
}}
QTreeWidget::item:selected {{
    background-color: {theme.accent};
    color: {theme.accent_text};
}}
"""
