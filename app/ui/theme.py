"""공용 디자인 토큰 + 전역 스타일시트.

`그룹웨어_디자인_기획_가이드.pptx`(신규 웹사이트 리뉴얼 디자인을 그룹웨어에 일관되게
적용하기 위한 가이드)의 컬러 · 타이포그래피 · Radius 스케일 · 버튼 4종 · 테이블 규칙을
그대로 옮긴 것이다. 개별 화면은 색상/치수를 직접 하드코딩하지 않고 이 모듈의 값을
참조한다.

가이드는 다크모드를 별도로 다루지 않지만, 이 앱은 OS 다크/라이트 모드를 이미 지원하고
있어 DARK 테마는 같은 브랜드 컬러 계열(Primary Muted #8A90FC 등)로 다크 배경에 맞게
파생시켰다.
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

# Radius 스케일 (가이드 슬라이드 6)
RADIUS_XS = 2  # 칩 · 태그
RADIUS_SM = 4  # 인풋 · 소형 버튼
RADIUS_MD = 6  # 버튼(기본)
RADIUS_LG = 8  # 카드
RADIUS_XL = 12  # 모달 · 대형 카드

# 타이포그래피 스케일 (가이드 슬라이드 5). Pretendard/맑은 고딕은 macOS 기본 설치
# 폰트가 아니라서 QSS font-family로 강제 지정하지 않는다 - Qt가 없는 폰트 이름을
# 해석하다가 일부 위젯(QComboBox 팝업 등)에서 글자가 깨지는 렌더링 버그가 있었다.
# OS 기본 시스템 폰트(맥: 산돌고딕Neo/SF, 윈도우: 맑은 고딕)를 그대로 사용한다.
DISPLAY_PT = 44
TITLE_PT = 28
SECTION_PT = 17
BODY_PT = 13.5
CAPTION_PT = 11


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str  # 앱 전체 배경 (화이트 베이스)
    surface: str  # 카드/패널/입력창 배경
    surface_alt: str  # Primary Subtle 톤 (테이블 헤더, 좌측 메뉴 배경)
    border: str
    text_primary: str  # Ink
    text_secondary: str
    accent: str  # Primary — 버튼 · 링크 · 강조
    accent_hover: str
    accent_pressed: str
    accent_text: str  # accent 배경 위 글자색
    header_bg: str  # Primary Accent — 다크 섹션 · 상단바
    header_text: str
    secondary_bg: str  # Secondary 버튼 배경 (Primary Subtle)
    secondary_text: str  # Secondary 버튼 글자색 (Primary)
    destructive: str
    destructive_hover: str
    destructive_pressed: str
    destructive_text: str
    success: str
    hover: str  # 리스트/트리/테이블 행 위에 마우스를 올렸을 때 배경
    chart_bg: str
    chart_text: str
    sales_text: str  # 매출 상태 텍스트 컬러 (배지 대신 컬러 텍스트만 사용)
    purchase_text: str  # 매입 상태 텍스트 컬러


LIGHT = Theme(
    name="light",
    bg="#FFFFFF",
    surface="#FFFFFF",
    surface_alt="#EBEDFF",  # Primary Subtle
    border="#D4DAE6",
    text_primary="#111111",  # Ink
    text_secondary="#5B5F73",
    accent="#5678FF",  # Primary
    accent_hover="#4F6EEB",
    accent_pressed="#4865D6",
    accent_text="#FFFFFF",
    header_bg="#31379E",  # Primary Accent
    header_text="#FFFFFF",
    secondary_bg="#EBEDFF",  # Primary Subtle
    secondary_text="#31379E",  # Primary Accent
    destructive="#D64338",
    destructive_hover="#C53E34",
    destructive_pressed="#B4382F",
    destructive_text="#FFFFFF",
    success="#248FF4",
    hover="#F3F4FF",
    chart_bg="#FFFFFF",
    chart_text="#111111",
    sales_text="#5678FF",  # Primary
    purchase_text="#31379E",  # Primary Accent
)

DARK = Theme(
    name="dark",
    bg="#1B1C24",
    surface="#25262F",
    surface_alt="#21222B",
    border="#34353F",
    text_primary="#F1F2F7",
    text_secondary="#9A9CB0",
    accent="#8A90FC",  # Primary Muted (다크 배경에서 더 잘 읽힘)
    accent_hover="#9DA3FF",
    accent_pressed="#6F76D6",
    accent_text="#12131A",
    header_bg="#3A41B0",
    header_text="#FFFFFF",
    secondary_bg="#2C2E45",
    secondary_text="#AEB3FF",
    destructive="#E5564A",
    destructive_hover="#EF6B60",
    destructive_pressed="#C94A3F",
    destructive_text="#FFFFFF",
    success="#4FA8F6",
    hover="#31334A",
    chart_bg="#25262F",
    chart_text="#F1F2F7",
    sales_text="#8A90FC",
    purchase_text="#6C9BFF",
)


def current_theme() -> Theme:
    scheme = QGuiApplication.styleHints().colorScheme()
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def build_app_qss(theme: Theme) -> str:
    return f"""
QWidget {{
    background-color: {theme.bg};
    color: {theme.text_primary};
    font-size: {BODY_PT}pt;
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
    font-size: {SECTION_PT}pt;
    font-weight: 700;
}}
QLabel[role="secondary"] {{
    color: {theme.text_secondary};
    font-size: {CAPTION_PT}pt;
}}
QWidget[role="card"] {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {RADIUS_LG}px;
}}
QWidget[role="modal-card"] {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {RADIUS_XL}px;
}}
QPushButton {{
    background-color: {theme.accent};
    color: {theme.accent_text};
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 20px;
    min-height: 20px;
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
    background-color: {theme.secondary_bg};
    color: {theme.secondary_text};
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {theme.hover};
}}
QPushButton[variant="secondary"]:pressed {{
    background-color: {theme.border};
}}
QPushButton[variant="outline"] {{
    background-color: transparent;
    color: {theme.text_primary};
    border: 1px solid {theme.border};
}}
QPushButton[variant="outline"]:hover {{
    background-color: {theme.hover};
}}
QPushButton[variant="outline"]:pressed {{
    background-color: {theme.border};
}}
QPushButton[variant="destructive"] {{
    background-color: {theme.destructive};
    color: {theme.destructive_text};
}}
QPushButton[variant="destructive"]:hover {{
    background-color: {theme.destructive_hover};
}}
QPushButton[variant="destructive"]:pressed {{
    background-color: {theme.destructive_pressed};
}}
QLineEdit, QDateEdit {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {RADIUS_SM}px;
    padding: 7px 10px;
    color: {theme.text_primary};
    selection-background-color: {theme.accent};
    selection-color: {theme.accent_text};
}}
QLineEdit:focus, QDateEdit:focus {{
    border: 1px solid {theme.accent};
}}
QComboBox {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {RADIUS_SM}px;
    padding: 2px 8px;
    color: {theme.text_primary};
}}
QComboBox:focus {{
    border: 1px solid {theme.accent};
}}
QComboBox QAbstractItemView {{
    background-color: {theme.surface};
    color: {theme.text_primary};
    selection-background-color: {theme.accent};
    selection-color: {theme.accent_text};
    border: 1px solid {theme.border};
    outline: none;
}}
QCheckBox {{
    color: {theme.text_primary};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: {RADIUS_XS}px;
    border: 1px solid {theme.border};
    background-color: {theme.surface};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {theme.accent};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {theme.accent};
    background-color: {theme.accent};
}}
QRadioButton {{
    color: {theme.text_primary};
    spacing: 8px;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {theme.border};
    background-color: {theme.surface};
}}
QRadioButton::indicator:hover {{
    border: 1px solid {theme.accent};
}}
QRadioButton::indicator:checked {{
    border: 5px solid {theme.accent};
    background-color: {theme.surface};
}}
QDialog {{
    background-color: {theme.bg};
}}
QTableWidget {{
    background-color: {theme.surface};
    alternate-background-color: {theme.surface_alt};
    gridline-color: {theme.border};
    border: 1px solid {theme.border};
    border-radius: {RADIUS_LG}px;
    color: {theme.text_primary};
}}
QTableWidget::item {{
    padding: 4px;
}}
QTableWidget::item:hover {{
    background-color: {theme.hover};
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
    font-size: 12px;
}}
QTreeWidget::item {{
    min-height: 34px;
    padding: 4px 4px;
    color: {theme.text_primary};
    border-radius: {RADIUS_SM}px;
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
