"""PPT `UTGW_UIUX.pptx` IA(슬라이드 4) 기준 좌측 메뉴 구조.

기존 웹 그룹웨어의 `tb_menu` 테이블과는 무관한, 이 경영관리 프로그램 전용 메뉴다.
"content_key"가 있는 항목만 실제 화면과 연결되고, 없는 항목은 "준비중"으로 표시한다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuItem:
    label: str
    content_key: str | None = None
    children: list["MenuItem"] = field(default_factory=list)


MENU_TREE: list[MenuItem] = [
    MenuItem(
        label="경영관리",
        children=[
            MenuItem(label="대시보드", content_key="dashboard"),
            MenuItem(label="매출/매입 현황", content_key="sales_purchase"),
            MenuItem(label="프로젝트 원가", content_key="project_cost"),
            MenuItem(label="한국도로공사 투입인력관리", content_key="project_manpower"),
            MenuItem(label="프로젝트 실행원가 비교", content_key="project_input_mm"),
            MenuItem(label="프로젝트 인력 투입", content_key="project_headcount"),
        ],
    ),
    MenuItem(
        label="운영관리",
        children=[
            MenuItem(label="정의중"),
            MenuItem(label="프로그램 업데이트", content_key="app_update"),
        ],
    ),
]
