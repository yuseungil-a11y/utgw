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

echo 2) PyInstaller 빌드 (--onefile: exe 하나로 빌드, _internal 폴더 없음)...
%PY_CMD% -m PyInstaller --onefile --windowed --name "%APP_NAME%" --noconfirm ^
    --icon "%PROJECT_DIR%app\resources\app_icon.ico" ^
    run_app.py
if errorlevel 1 (
    echo 빌드에 실패했습니다.
    pause
    exit /b 1
)

echo 3) config.ini를 exe와 같은 폴더(dist\)에 배치...
REM dist 폴더는 빌드할 때마다 통째로 새로 만들어지므로 매번 다시 복사한다.
if exist "%PROJECT_DIR%config.ini" (
    copy "%PROJECT_DIR%config.ini" "%PROJECT_DIR%dist\config.ini" >nul
    echo config.ini를 dist\ 로 복사했습니다.
) else (
    echo 경고: config.ini가 없습니다. config.ini.example을 복사해서 만들어주세요.
)

echo.
echo 완료: %PROJECT_DIR%dist\%APP_NAME%.exe
echo (exe와 config.ini를 같이 복사/이동하면 어디로 옮겨도 그대로 동작합니다)
pause
