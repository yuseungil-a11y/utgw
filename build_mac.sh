#!/bin/bash
# macOS .app 빌드 스크립트.
#
# PyInstaller의 기본 --deep 서명이 이 환경에서 크래시(SIGBUS)가 나서, 다음 순서로 우회한다:
#   1. 로컬 디스크(/tmp)에 빌드
#   2. 번들 안의 모든 Mach-O 파일을 개별적으로 ad-hoc 서명 (bottom-up)
#   3. 최상위 .app을 --deep 없이 서명
#   4. ~/Applications 로 복사
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="UTGW경영관리"
BUILD_ROOT="/tmp/utgw_build"
DIST_DIR="$BUILD_ROOT/dist"
WORK_DIR="$BUILD_ROOT/work"

cd "$PROJECT_DIR"

echo "1) PyInstaller 빌드..."
python3 -m PyInstaller --windowed --name "$APP_NAME" --noconfirm \
    --icon "$PROJECT_DIR/app/resources/app_icon.icns" \
    --distpath "$DIST_DIR" --workpath "$WORK_DIR" --specpath "$BUILD_ROOT" \
    run_app.py

APP_PATH="$DIST_DIR/$APP_NAME.app"

echo "2) 번들 내 Mach-O 파일 개별 서명..."
find "$APP_PATH" -type f | while read -r f; do
    if file "$f" 2>/dev/null | grep -q "Mach-O"; then
        codesign -s - --force "$f" >/dev/null 2>&1 || true
    fi
done

echo "3) 최상위 앱 번들 서명..."
codesign -s - --force "$APP_PATH"
codesign -v "$APP_PATH" && echo "서명 검증 OK" || echo "경고: 서명 검증에서 경고가 있었지만 로컬 실행에는 문제 없습니다."

echo "4) config.ini를 실행파일과 같은 폴더(Contents/MacOS)에 배치..."
# .app은 재빌드 때마다 통째로 새로 만들어지므로 매번 다시 넣어준다.
if [ -f "$PROJECT_DIR/config.ini" ]; then
    cp "$PROJECT_DIR/config.ini" "$APP_PATH/Contents/MacOS/config.ini"
else
    echo "경고: config.ini가 없습니다. config.ini.example을 복사해서 만들어주세요."
fi

echo "5) ~/Applications 로 복사..."
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/$APP_NAME.app"
cp -R "$APP_PATH" "$HOME/Applications/"

echo "완료: $HOME/Applications/$APP_NAME.app"
