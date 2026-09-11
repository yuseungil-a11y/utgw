"""GitHub Release 기반 버전 체크 · 자동 업데이트.

Qdrant 데스크톱 앱 등이 쓰는 방식과 동일한 개념이다: GitHub Releases의 "최신 릴리즈"
정보(태그=버전, 첨부파일=설치 폴더 zip)를 확인해서, 로컬 버전보다 최신이면 내려받아
설치 폴더를 교체하고 재시작한다.

**빌드 방식 — onedir(폴더 배포), onefile 아님**: 처음엔 PyInstaller `--onefile`로
exe 하나만 배포했는데, onefile은 실행할 때마다 `%TEMP%`에 자기 자신을 압축해제하고
그 안에서 python3xx.dll을 로드하는 방식이라 그 추출 과정이 백신 실시간 검사에 걸리면
"Failed to load Python DLL ... LoadLibrary: 지정된 모듈을 찾을 수 없습니다" 오류로
이어졌다(특히 막 업데이트로 내려받은/이동된 exe에서 재현됨). `--onedir`로 바꿔서
실행 시점의 압축해제 자체를 없앴다(build_windows.bat 참고). 그 결과 배포 단위가
exe 파일 하나가 아니라 "exe + 종속 DLL이 들어있는 폴더"가 됐고, 이 모듈도 zip으로
묶인 그 폴더 전체를 내려받아 설치 폴더에 덮어쓰는 방식으로 동작한다.

**인증 관련**: 이 저장소(yuseungil-a11y/utgw)는 현재 공개 저장소라 토큰 없이도
동작한다. 나중에 다시 비공개로 돌리면 config.ini의 [update] 섹션에 이 저장소 콘텐츠만
읽을 수 있는 fine-grained PAT를 채우면 된다(별도 코드 수정 불필요).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = "yuseungil-a11y/utgw"
ZIP_ASSET_NAME = "UTGW경영관리.zip"
API_BASE = "https://api.github.com"
_MIN_VALID_ZIP_SIZE = 20_000_000  # 이보다 작으면 손상/잘린 다운로드로 간주
_MIN_VALID_EXE_SIZE = 5_000_000  # 압축 해제한 실행파일 최소 크기(정상은 약 80MB)


class UpdateCheckError(Exception):
    """버전 확인/다운로드/설치 과정에서 발생한 오류. 메시지를 그대로 사용자에게 보여준다."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    api_url: str  # GitHub API asset URL (비공개 저장소 다운로드에 필요)
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str  # 태그명에서 앞의 'v'를 뗀 값, 예: "1.3.0"
    tag_name: str
    notes: str
    published_at: str
    asset: ReleaseAsset | None


def parse_version(text: str) -> tuple[int, ...]:
    """"v1.2.0" / "1.2.0" 형태를 (1, 2, 0)으로 변환한다. 파싱 불가한 부분은 0으로 취급."""
    cleaned = text.strip().lstrip("vV")
    parts = []
    for token in cleaned.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_newer(current_version: str, candidate_version: str) -> bool:
    return parse_version(candidate_version) > parse_version(current_version)


def _request_json(url: str, token: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "UTGW-GroupwareApp-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateCheckError(
                f"버전 정보를 가져올 수 없습니다(404, {url}). 저장소가 비공개이거나, "
                "config.ini의 [update] token이 없거나 잘못됐거나, 아직 GitHub에 "
                "릴리즈(Release)가 하나도 등록되지 않았을 수 있습니다."
            ) from exc
        if exc.code == 401:
            raise UpdateCheckError(
                "인증에 실패했습니다(401). config.ini의 [update] token을 확인해 주세요."
            ) from exc
        raise UpdateCheckError(f"GitHub 응답 오류: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"GitHub에 연결할 수 없습니다.\n{exc.reason}") from exc


def get_latest_release(repo: str = DEFAULT_REPO, token: str = "") -> ReleaseInfo:
    """GitHub Releases의 최신 릴리즈 정보를 가져온다. draft/prerelease는 제외된다
    (/releases/latest 엔드포인트 자체가 그렇게 동작함)."""
    data = _request_json(f"{API_BASE}/repos/{repo}/releases/latest", token)

    asset = None
    for item in data.get("assets", []):
        if item.get("name") == ZIP_ASSET_NAME:
            asset = ReleaseAsset(
                name=item["name"], api_url=item["url"], size=int(item.get("size", 0))
            )
            break
    if asset is None:
        # 이름이 바뀌었을 수 있으니, zip 첨부파일이 하나뿐이면 그걸로 대체 사용
        zip_assets = [a for a in data.get("assets", []) if a.get("name", "").endswith(".zip")]
        if len(zip_assets) == 1:
            item = zip_assets[0]
            asset = ReleaseAsset(
                name=item["name"], api_url=item["url"], size=int(item.get("size", 0))
            )

    tag_name = data.get("tag_name", "")
    return ReleaseInfo(
        version=".".join(str(p) for p in parse_version(tag_name)) if tag_name else "",
        tag_name=tag_name,
        notes=data.get("body") or "",
        published_at=data.get("published_at") or "",
        asset=asset,
    )


def download_asset(
    asset: ReleaseAsset,
    dest_path: Path,
    token: str = "",
    progress_cb=None,
) -> None:
    """릴리즈 첨부파일(zip)을 dest_path에 내려받는다. progress_cb(downloaded, total)로
    진행률을 알려준다(total이 0이면 크기를 알 수 없다는 뜻)."""
    headers = {
        "Accept": "application/octet-stream",  # 비공개 저장소 첨부파일 다운로드에 필요
        "User-Agent": "UTGW-GroupwareApp-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(asset.api_url, headers=headers)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length") or asset.size or 0)
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except urllib.error.HTTPError as exc:
        tmp_path.unlink(missing_ok=True)
        raise UpdateCheckError(f"다운로드 실패: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        tmp_path.unlink(missing_ok=True)
        raise UpdateCheckError(f"다운로드 중 연결이 끊어졌습니다.\n{exc.reason}") from exc

    # 서버가 연결을 조기에 닫아도 resp.read()가 그냥 빈 바이트를 돌려주며 루프가
    # "정상 종료"된 것처럼 빠져나가는 경우가 있다 — 그 상태로 그냥 설치하면 잘린
    # 파일로 이어지므로, 크기가 다르면 반드시 오류로 처리하고 설치 파일로 옮기지 않는다.
    actual_size = tmp_path.stat().st_size
    if total > 0 and actual_size != total:
        tmp_path.unlink(missing_ok=True)
        raise UpdateCheckError(
            f"다운로드가 불완전합니다(예상 {total:,}바이트, 실제 {actual_size:,}바이트). "
            "네트워크 상태를 확인하고 다시 시도해 주세요."
        )
    if actual_size < _MIN_VALID_ZIP_SIZE:
        tmp_path.unlink(missing_ok=True)
        raise UpdateCheckError(
            f"다운로드된 파일이 너무 작습니다({actual_size:,}바이트). 릴리즈 첨부파일을 확인해 주세요."
        )
    tmp_path.replace(dest_path)


def extract_update(zip_path: Path) -> Path:
    """내려받은 배포 zip을 임시 스테이징 폴더에 풀고, 그 폴더 경로를 반환한다.
    zip은 빌드 스크립트가 `dist\\UTGW경영관리\\*`를 압축한 것이라, 최상위에 폴더
    없이 exe·DLL·리소스가 바로 들어있다(폴더를 한 겹 더 감싸지 않음)."""
    staging_dir = Path(tempfile.gettempdir()) / "utgw_update_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging_dir)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise UpdateCheckError("다운로드한 업데이트 파일이 손상되어 압축을 풀 수 없습니다.") from exc
    return staging_dir


def is_running_frozen() -> bool:
    """PyInstaller로 빌드된 exe로 실행 중인지 여부. 개발 모드(`py run_app.py`)에서는
    교체할 설치 폴더 자체가 없으므로 자동 업데이트를 지원하지 않는다."""
    return bool(getattr(sys, "frozen", False))


# 헬퍼 스크립트 자체는 순수 ASCII로 작성하고, 한글이 섞인 실제 경로(exe 파일명
# "UTGW경영관리.exe", 폴더명 등)는 전부 명령줄 인자로 전달한다 — 배치파일 리터럴에
# 한글을 직접 넣으면 콘솔 코드페이지에 따라 깨지는 문제가 있었다.
_RELAUNCH_HELPER = """
param(
    [Parameter(Mandatory=$true)][int]$ProcessId,
    [Parameter(Mandatory=$true)][string]$StagingDir,
    [Parameter(Mandatory=$true)][string]$TargetDir,
    [Parameter(Mandatory=$true)][string]$TargetExeName
)
while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
    Start-Sleep -Milliseconds 400
}
Start-Sleep -Milliseconds 300

# config.ini는 사용자의 DB 접속정보 등 설정 파일이라 새 배포본으로 덮어쓰지 않는다.
Get-ChildItem -LiteralPath $StagingDir -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($StagingDir.Length).TrimStart('\\')
    if ($relative -ieq 'config.ini') { return }
    $destPath = Join-Path $TargetDir $relative
    $destDir = Split-Path $destPath -Parent
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $_.FullName -Destination $destPath -Force
}

Remove-Item -LiteralPath $StagingDir -Recurse -Force
Start-Process -FilePath (Join-Path $TargetDir $TargetExeName)
Remove-Item -LiteralPath $PSCommandPath -Force
"""


def apply_update_and_restart(staging_dir: Path) -> None:
    """현재 실행 중인 exe가 종료되기를 기다렸다가, 압축 해제된 새 배포본
    (staging_dir)의 파일들을 설치 폴더에 덮어쓰고 재실행하는 PowerShell 헬퍼를
    분리 프로세스로 띄운다. 호출한 쪽은 이 함수 호출 직후 앱을 종료해야 한다
    (현재 exe 파일 잠금이 풀려야 교체가 가능하다). config.ini는 사용자 설정이라
    덮어쓰지 않고 보존한다."""
    if not is_running_frozen():
        raise UpdateCheckError("개발 모드에서는 자동 업데이트를 적용할 수 없습니다.")
    if sys.platform != "win32":
        raise UpdateCheckError("자동 업데이트는 현재 Windows에서만 지원합니다.")

    target_exe = Path(sys.executable).resolve()
    target_dir = target_exe.parent
    staged_exe = staging_dir / target_exe.name

    # download_asset이 zip 크기까지 확인하긴 하지만, 압축 해제 후 그 안에 정상
    # 크기의 실행파일이 실제로 있는지까지 마지막으로 한 번 더 걸러낸다 — 이 확인
    # 없이 손상된 배포본을 그대로 설치하면 "Failed to load Python DLL" 같은
    # 오류로 프로그램 자체가 실행되지 않게 된다.
    if not staged_exe.exists() or staged_exe.stat().st_size < _MIN_VALID_EXE_SIZE:
        raise UpdateCheckError(
            "내려받은 설치 파일이 손상된 것 같습니다(실행파일을 찾을 수 없음). "
            "업데이트를 다시 시도해 주세요."
        )

    helper_path = Path(tempfile.gettempdir()) / "utgw_update_relaunch.ps1"
    helper_path.write_text(_RELAUNCH_HELPER, encoding="utf-8")

    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(helper_path),
            "-ProcessId",
            str(os.getpid()),
            "-StagingDir",
            str(staging_dir.resolve()),
            "-TargetDir",
            str(target_dir),
            "-TargetExeName",
            target_exe.name,
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
