from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.config import AppConfig
from app.updater import (
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckError,
    apply_update_and_restart,
    download_asset,
    extract_update,
    get_latest_release,
    is_newer,
    is_running_frozen,
)
from app.version import APP_VERSION


class _CheckWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, repo: str, token: str):
        super().__init__()
        self._repo = repo
        self._token = token

    def run(self) -> None:
        try:
            info = get_latest_release(self._repo, self._token)
        except UpdateCheckError as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - 예상 못한 오류도 그대로 안내
            self.error.emit(str(exc))
            return
        self.finished.emit(info)


class _DownloadWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, asset: ReleaseAsset, dest_path: Path, token: str):
        super().__init__()
        self._asset = asset
        self._dest_path = dest_path
        self._token = token

    def run(self) -> None:
        try:
            download_asset(
                self._asset, self._dest_path, self._token, progress_cb=self.progress.emit
            )
        except UpdateCheckError as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
            return
        self.finished.emit(str(self._dest_path))


class UpdateDialog(QDialog):
    def __init__(self, app_config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = app_config
        self._latest: ReleaseInfo | None = None
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        self.setWindowTitle("프로그램 업데이트")
        self.resize(560, 480)

        title_label = QLabel("프로그램 업데이트")
        title_label.setProperty("role", "title")

        self._version_label = QLabel(f"현재 버전: v{APP_VERSION}")
        self._version_label.setProperty("role", "secondary")

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "secondary")
        self._status_label.setWordWrap(True)

        self._check_button = QPushButton("업데이트 확인")
        self._check_button.clicked.connect(self._on_check)

        self._notes_view = QTextEdit()
        self._notes_view.setReadOnly(True)
        self._notes_view.setPlaceholderText("업데이트 확인을 누르면 릴리즈 정보가 여기에 표시됩니다.")

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)

        self._update_button = QPushButton("업데이트 설치 후 재시작")
        self._update_button.setEnabled(False)
        self._update_button.clicked.connect(self._on_update)

        close_button = QPushButton("닫기")
        close_button.setProperty("variant", "outline")
        close_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(self._check_button)
        button_row.addStretch()
        button_row.addWidget(close_button)
        button_row.addWidget(self._update_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title_label)
        layout.addWidget(self._version_label)
        layout.addWidget(self._status_label)
        layout.addWidget(self._notes_view, 1)
        layout.addWidget(self._progress_bar)
        layout.addLayout(button_row)
        self.setLayout(layout)

        if not is_running_frozen():
            self._status_label.setText(
                "개발 모드(소스코드 직접 실행)에서는 자동 업데이트를 사용할 수 없습니다. "
                "git pull로 갱신해 주세요."
            )
            self._check_button.setEnabled(False)

    # ------------------------------------------------------------------
    def _run_in_thread(self, worker: QObject, on_finished, on_error) -> None:
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.finished.connect(self._thread.quit)
        worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None

    # ------------------------------------------------------------------
    def _on_check(self) -> None:
        self._check_button.setEnabled(False)
        self._update_button.setEnabled(False)
        self._status_label.setText("업데이트 확인 중...")
        worker = _CheckWorker(self._config.update.repo, self._config.update.token)
        self._run_in_thread(worker, self._on_check_finished, self._on_check_error)

    def _on_check_error(self, message: str) -> None:
        self._check_button.setEnabled(True)
        self._status_label.setText(f"업데이트 확인에 실패했습니다.\n{message}")

    def _on_check_finished(self, info: ReleaseInfo) -> None:
        self._check_button.setEnabled(True)
        self._latest = info

        if not info.version:
            self._status_label.setText("릴리즈 정보를 확인했지만 버전 태그를 읽지 못했습니다.")
            return

        self._notes_view.setPlainText(info.notes or "(릴리즈 노트가 없습니다.)")

        if is_newer(APP_VERSION, info.version):
            if info.asset is None:
                self._status_label.setText(
                    f"새 버전 v{info.version}이 있지만, 첨부된 설치 파일(zip)을 찾지 못했습니다."
                )
                return
            self._status_label.setText(f"새 버전 v{info.version}이 있습니다. 업데이트할 수 있습니다.")
            self._update_button.setEnabled(True)
        else:
            self._status_label.setText("이미 최신 버전입니다.")

    # ------------------------------------------------------------------
    def _on_update(self) -> None:
        if self._latest is None or self._latest.asset is None:
            return
        reply = QMessageBox.question(
            self,
            "업데이트",
            f"v{self._latest.version}으로 업데이트합니다. 프로그램이 재시작됩니다.\n계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        import tempfile

        dest_path = Path(tempfile.gettempdir()) / self._latest.asset.name
        self._check_button.setEnabled(False)
        self._update_button.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._status_label.setText("다운로드 중...")

        worker = _DownloadWorker(self._latest.asset, dest_path, self._config.update.token)
        worker.progress.connect(self._on_download_progress)
        self._run_in_thread(worker, self._on_download_finished, self._on_download_error)

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(downloaded)
        self._status_label.setText(f"다운로드 중... {downloaded / 1_000_000:.1f}MB")

    def _on_download_error(self, message: str) -> None:
        self._progress_bar.setVisible(False)
        self._check_button.setEnabled(True)
        self._update_button.setEnabled(True)
        QMessageBox.critical(self, "업데이트 실패", f"다운로드에 실패했습니다.\n{message}")

    def _on_download_finished(self, path: str) -> None:
        self._status_label.setText("압축 해제 중...")
        try:
            staging_dir = extract_update(Path(path))
        except UpdateCheckError as exc:
            self._progress_bar.setVisible(False)
            self._check_button.setEnabled(True)
            self._update_button.setEnabled(True)
            QMessageBox.critical(self, "업데이트 실패", str(exc))
            return

        self._status_label.setText("설치 중... 잠시 후 프로그램이 재시작됩니다.")
        try:
            apply_update_and_restart(staging_dir)
        except UpdateCheckError as exc:
            self._progress_bar.setVisible(False)
            self._check_button.setEnabled(True)
            self._update_button.setEnabled(True)
            QMessageBox.critical(self, "업데이트 실패", str(exc))
            return

        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()
