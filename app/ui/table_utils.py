"""그리드 헤더 클릭 정렬 공용 유틸.

`QTableWidget.setSortingEnabled(True)`만 켜면 헤더 클릭으로 오름차순/내림차순
정렬이 되긴 하는데, 기본 정렬은 셀에 표시된 텍스트를 그대로 문자열로
비교한다. 그래서 "1,234,567" 같은 천단위 콤마가 들어간 금액이나 "85%" 같은
값은 사전식으로 비교돼 크기 순서가 뒤죽박죽이 된다(예: "100"이 "99"보다
"1" < "9"라서 앞으로 온다). `NumericTableWidgetItem`은 텍스트에서 숫자만
뽑아 크기로 비교하고, 숫자로 못 바꾸는 값(빈칸, 순수 텍스트)은 문자열
비교로 그대로 폴백한다.

새 그리드를 만들 때는 금액/개수/시간 등 숫자 컬럼에 `QTableWidgetItem` 대신
이 클래스를 쓰고, 표를 만든 뒤 `enable_header_sorting(table)`을 호출하면
헤더 클릭 정렬이 바로 올바르게 동작한다.

주의: 아래 항목엔 일부러 정렬을 넣지 않았다 — 헤더를 클릭해 행 순서가
바뀌면 화면이 오히려 망가지기 때문이다.
- 편집 가능하고 "저장" 버튼이 있는 그리드(예: 투입인력관리 목록 보기): 저장 시
  화면 행 순서(row_idx)로 원본 데이터를 찾아가는데, 정렬로 행 순서가 바뀌면
  엉뚱한 행에 저장되는 사고로 이어진다.
  - 프로젝트별 원가/실행예산 헤더 행 밑에 소속 데이터 행이 묶여 있는 것처럼,
    "헤더 행 + 그 아래 데이터 행" 구조로 그룹을 표현하는 그리드: 정렬하면
    헤더 행과 데이터 행이 뒤섞여 그룹 구조 자체가 무의미해진다.
"""

import re

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

_NUMERIC_RE = re.compile(r"-?\d+\.?\d*")


class NumericTableWidgetItem(QTableWidgetItem):
    """콤마·%·단위가 섞인 숫자 텍스트도 크기 순으로 정렬되는 QTableWidgetItem."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # noqa: D105
        self_num = _extract_number(self.text())
        other_num = _extract_number(other.text())
        if self_num is not None and other_num is not None:
            return self_num < other_num
        return self.text() < other.text()


def _extract_number(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        return None
    match = _NUMERIC_RE.match(cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def enable_header_sorting(table: QTableWidget) -> None:
    """헤더를 클릭하면 그 컬럼 기준으로 오름차순/내림차순 정렬되게 한다."""
    table.setSortingEnabled(True)
