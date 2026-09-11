@echo off
REM Windows 실행파일 빌드 스크립트. 반드시 Windows PC에서 실행해야 합니다
REM (PyInstaller는 크로스 컴파일을 지원하지 않습니다).
setlocal

set APP_NAME=UTGW경영관리
set PROJECT_DIR=%~dp0

cd /d "%PROJECT_DIR%"

REM Windows에서 "python" 명령이 실제 파이썬 대신 스토어로 연결되는 빈 알림으로
REM 잡혀있는 경우가 많아서(App Execution Alias), 있으면 "py" 런처를 우선 사용한다.
where py >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=py
) else (
    set PY_CMD=python
)
echo 사용할 파이썬 명령: %PY_CMD%

echo 1) 의존성 설치...
%PY_CMD% -m pip install --quiet -r requirements.txt
%PY_CMD% -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo pip 설치에 실패했습니다. %PY_CMD%이 PATH에 있는지 확인해주세요.
    pause
    exit /b 1
)

echo 2) PyInstaller 빌드 (--onedir: exe + 종속 DLL을 폴더에 그대로 둔다)...
REM --onefile은 실행할 때마다 %%TEMP%%에 자기 자신을 압축해제하고 그 안에서
REM python3xx.dll을 로드하는 방식이라, 그 추출 과정이 백신 실시간 검사에 걸리면
REM "Failed to load Python DLL ... LoadLibrary: 지정된 모듈을 찾을 수 없습니다"
REM 오류로 이어진다(특히 업데이트 직후 막 내려받은/이동된 exe에서 자주 발생).
REM --onedir는 실행 시점에 압축해제가 없어서 이 문제 자체가 없다.
%PY_CMD% -m PyInstaller --onedir --windowed --name "%APP_NAME%" --noconfirm ^
    --icon "%PROJECT_DIR%app\resources\app_icon.ico" ^
    run_app.py
if errorlevel 1 (
    echo 빌드에 실패했습니다.
    pause
    exit /b 1
)

echo 3) config.ini를 exe와 같은 폴더(dist\%APP_NAME%\)에 배치...
REM dist 폴더는 빌드할 때마다 통째로 새로 만들어지므로 매번 다시 복사한다.
if exist "%PROJECT_DIR%config.ini" (
    copy "%PROJECT_DIR%config.ini" "%PROJECT_DIR%dist\%APP_NAME%\config.ini" >nul
    echo config.ini를 dist\%APP_NAME%\ 로 복사했습니다.
) else (
    echo 경고: config.ini가 없습니다. config.ini.example을 복사해서 만들어주세요.
)

echo 4) 배포/업데이트용 zip 생성 (GitHub Release 첨부파일 - app/updater.py가 이 zip을
echo    내려받아 설치 폴더 전체를 갱신한다)...
if exist "%PROJECT_DIR%dist\%APP_NAME%.zip" del "%PROJECT_DIR%dist\%APP_NAME%.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%PROJECT_DIR%dist\%APP_NAME%\*' -DestinationPath '%PROJECT_DIR%dist\%APP_NAME%.zip' -Force"
if errorlevel 1 (
    echo 경고: 배포용 zip 생성에 실패했습니다. GitHub 릴리즈에는 이 zip을 올려야 합니다.
)

echo.
echo 완료: %PROJECT_DIR%dist\%APP_NAME%\%APP_NAME%.exe
echo (폴더 전체를 그대로 옮겨야 동작합니다 - exe 파일 하나만 복사하면 실행되지 않습니다)
echo 배포/업데이트용 zip: %PROJECT_DIR%dist\%APP_NAME%.zip
pause
