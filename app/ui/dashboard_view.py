from datetime import date

from PySide6.QtCharts import (
    QAbstractBarSeries,
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.auth import AuthenticatedUser
from app.config import AppConfig
from app.queries.dashboard import CashFlowStatus, SalesStatus, get_cash_flow_status, get_sales_status
from app.ui.theme import current_theme

REFRESH_INTERVAL_MS = 10_000


def _format_won(value: int) -> str:
    return f"{value:,}원"


def _won_to_million(value: int) -> int:
    """Qt 차트의 막대 라벨은 값이 크면 지수표기(예: 5.43989e+08)로 바뀌어버려서,
    막대 높이/라벨용 값은 백만원 단위로 줄여서 넘긴다. 정확한 원 단위 금액은
    차트 아래 상세 텍스트(_format_won)에 그대로 표시한다."""
    return round(value / 1_000_000)


def _wrap_category_label(text: str, limit: int = 5) -> str:
    """차트 x축 카테고리 라벨이 limit자를 넘으면 말줄임표 대신 다음 줄로 넘긴다.
    공백이 있으면 그 자리에서, 없으면 앞의 숫자(연도 등) 뒤에서 끊어서 단어 중간이
    잘리지 않게 한다."""
    if len(text) <= limit:
        return text
    space_idx = text.find(" ")
    if 0 < space_idx <= limit + 1:
        return text[:space_idx] + "\n" + text[space_idx + 1 :]
    digit_run = len(text) - len(text.lstrip("0123456789"))
    if 0 < digit_run < len(text):
        return text[:digit_run] + "\n" + text[digit_run:]
    return text[:limit] + "\n" + text[limit:]


class _DashboardWorker(QObject):
    finished = Signal(object, object)
    error = Signal(str)

    def __init__(self, app_config: AppConfig, year: int):
        super().__init__()
        self._app_config = app_config
        self._year = year

    def run(self) -> None:
        try:
            target = self._app_config.sales_targets.get(self._year, 0)
            sales = get_sales_status(self._app_config.database, self._year, target)
            cash_flow = get_cash_flow_status(self._app_config.database, self._year)
        except Exception as exc:  # noqa: BLE001 - 상태바에 그대로 노출
            self.error.emit(str(exc))
            return
        self.finished.emit(sales, cash_flow)


class DashboardView(QWidget):
    def __init__(self, app_config: AppConfig, user: AuthenticatedUser, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._user = user
        self._year = date.today().year
        self._thread: QThread | None = None
        self._worker: _DashboardWorker | None = None

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")

        self._sales_chart_view = self._build_empty_chart_view("매출현황")
        self._sales_detail_label = self._build_detail_label()
        self._cash_flow_chart_view = self._build_empty_chart_view("입출금 현황")
        self._cash_flow_detail_label = self._build_detail_label()

        sales_container = self._build_card(self._sales_chart_view, self._sales_detail_label)
        cash_flow_container = self._build_card(self._cash_flow_chart_view, self._cash_flow_detail_label)

        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(16)
        # 매출현황은 막대 2개뿐이라 좁게, 입출금 현황은 막대 8개라 넓게 배정한다.
        charts_layout.addWidget(sales_container, 1)
        charts_layout.addWidget(cash_flow_container, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self._status_label)
        layout.addLayout(charts_layout)
        self.setLayout(layout)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    @staticmethod
    def _build_card(chart_view: QChartView, detail_label: QLabel) -> QWidget:
        container = QWidget()
        container.setProperty("role", "card")
        box = QVBoxLayout()
        box.setContentsMargins(16, 16, 16, 12)
        box.setSpacing(8)
        box.addWidget(chart_view)
        box.addWidget(detail_label)
        container.setLayout(box)
        return container

    @staticmethod
    def _build_empty_chart_view(title: str) -> QChartView:
        chart = QChart()
        chart.setTitle(title)
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background: transparent;")
        return view

    @staticmethod
    def _style_chart(chart: QChart, axis_x, axis_y) -> None:
        """카드 배경과 어울리도록, 현재 라이트/다크 테마에 맞는 배경·글자색을 적용한다."""
        theme = current_theme()
        chart.setBackgroundBrush(QColor(theme.chart_bg))
        chart.setBackgroundRoundness(0)
        chart.setTitleBrush(QColor(theme.chart_text))
        axis_x.setLabelsColor(QColor(theme.chart_text))
        axis_y.setLabelsColor(QColor(theme.chart_text))
        return QColor(theme.chart_text)

    @staticmethod
    def _build_detail_label() -> QLabel:
        label = QLabel("")
        label.setProperty("role", "secondary")
        label.setStyleSheet("font-size: 12px;")
        label.setWordWrap(True)
        return label

    def refresh(self) -> None:
        if self._thread is not None:
            return  # 이전 조회가 아직 진행 중이면 이번 틱은 건너뜀

        self._thread = QThread(self)
        self._worker = _DashboardWorker(self._config, self._year)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data_ready)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """앱 종료 시 백그라운드 조회 스레드가 살아있는 채로 파괴되지 않도록 정리한다."""
        self._timer.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()

    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"데이터 조회 실패: {message}")

    def _on_data_ready(self, sales: SalesStatus, cash_flow: CashFlowStatus) -> None:
        self._render_sales_chart(sales)
        self._render_cash_flow_chart(cash_flow)
        now = date.today().isoformat()
        self._status_label.setText(f"마지막 갱신: {now} (10초 주기 자동 갱신)")

    def _render_sales_chart(self, sales: SalesStatus) -> None:
        chart = QChart()
        chart.setTitle(f"{sales.year}년 매출현황 (단위: 백만원)")
        chart.legend().hide()

        target_m = _won_to_million(sales.target)
        actual_m = _won_to_million(sales.actual)

        bar_set = QBarSet("금액")
        bar_set.append([target_m, actual_m])

        series = QBarSeries()
        series.append(bar_set)
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value")
        series.setLabelsPosition(QAbstractBarSeries.LabelsPosition.LabelsOutsideEnd)
        chart.addSeries(series)

        categories = [
            _wrap_category_label(f"{sales.year}매출 목표"),
            _wrap_category_label(f"{sales.year}매출"),
        ]
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%,.0f")
        max_value = max(target_m, actual_m, 1)
        axis_y.setRange(0, max_value * 1.25)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        label_color = self._style_chart(chart, axis_x, axis_y)
        bar_set.setLabelColor(label_color)

        self._sales_chart_view.setChart(chart)
        self._sales_detail_label.setText(
            f"매출목표: {_format_won(sales.target)}   /   매출실적: {_format_won(sales.actual)}"
        )

    def _render_cash_flow_chart(self, cash_flow: CashFlowStatus) -> None:
        chart = QChart()
        chart.setTitle("입출금 현황 (단위: 백만원)")
        chart.legend().hide()

        categories = [
            _wrap_category_label(label)
            for label in [
                "매출 종결",
                "매입 종결",
                "매출 영업확인중",
                "매입 영업확인중",
                "계산서 발행중",
                "입금대기중",
                "계산서 수령중",
                "지급대기중",
            ]
        ]
        values = [
            _won_to_million(cash_flow.sales_closed),
            _won_to_million(cash_flow.purchase_closed),
            _won_to_million(cash_flow.sales_confirming),
            _won_to_million(cash_flow.purchase_confirming),
            _won_to_million(cash_flow.sales_issuing),
            _won_to_million(cash_flow.sales_pending),
            _won_to_million(cash_flow.purchase_receiving),
            _won_to_million(cash_flow.purchase_pending),
        ]
        bar_set = QBarSet("금액")
        bar_set.append(values)

        series = QBarSeries()
        series.append(bar_set)
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value")
        series.setLabelsPosition(QAbstractBarSeries.LabelsPosition.LabelsOutsideEnd)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%,.0f")
        axis_y.setRange(0, max(values + [1]) * 1.25)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        label_color = self._style_chart(chart, axis_x, axis_y)
        bar_set.setLabelColor(label_color)

        self._cash_flow_chart_view.setChart(chart)
        self._cash_flow_detail_label.setText(
            f"매출종결: {_format_won(cash_flow.sales_closed)}   /   "
            f"매입종결: {_format_won(cash_flow.purchase_closed)}   /   "
            f"매출영업확인중: {_format_won(cash_flow.sales_confirming)}   /   "
            f"매입영업확인중: {_format_won(cash_flow.purchase_confirming)}   /   "
            f"계산서발행중: {_format_won(cash_flow.sales_issuing)}   /   "
            f"입금대기중: {_format_won(cash_flow.sales_pending)}   /   "
            f"계산서수령중: {_format_won(cash_flow.purchase_receiving)}   /   "
            f"지급대기중: {_format_won(cash_flow.purchase_pending)}"
        )
