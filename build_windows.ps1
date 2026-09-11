# Windows 실행파일 빌드 스크립트 (PowerShell).
#
# 원래는 build_windows.bat 하나로 다 했는데, 배치파일이 한글 텍스트를 다룰 때
# 두 가지 문제가 반복됐다:
#   1. 콘솔 활성 코드페이지와 파일 인코딩이 안 맞으면 UTGW경영관리 같은 한글
#      변수/경로가 깨진 채로 만들어짐(환경마다 활성 코드페이지가 달라서 재현이
#      들쭉날쭉함).
#   2. echo로 출력하는 한글 설명글에 여는 괄호 '('와 닫는 괄호 ')'가 서로 다른
#      줄에 걸쳐 있으면, cmd.exe가 그걸 if/for 블록의 시작으로 오인해서 이후
#      줄 전체의 파싱이 깨짐.
# PowerShell은 두 문제 다 없어서(유니코드를 코드페이지와 무관하게 다루고, 문자열/
# 주석 안의 괄호를 실행 흐름과 혼동하지 않는다) 실제 빌드 로직은 전부 여기로
# 옮겼다. build_windows.bat은 이 스크립트를 실행만 하는 얇은 진입점이다.

$ErrorActionPreference = "Stop"

$AppName = "UTGW경영관리"
$ProjectDir = $PSScriptRoot

Set-Location $ProjectDir

function Fail($message) {
    Write-Host $message -ForegroundColor Red
    exit 1
}

# Windows에서 "python" 명령이 실제 파이썬 대신 스토어로 연결되는 빈 알림으로
# 잡혀있는 경우가 많아서(App Execution Alias), 있으면 "py" 런처를 우선 사용한다.
$pyCmd = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
Write-Host "사용할 파이썬 명령: $pyCmd"

Write-Host "1) 의존성 설치..."
& $pyCmd -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip 설치에 실패했습니다. $pyCmd 이 PATH에 있는지 확인해주세요." }
& $pyCmd -m pip install --quiet pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "pip 설치에 실패했습니다. $pyCmd 이 PATH에 있는지 확인해주세요." }

Write-Host "2) PyInstaller 빌드 (--onedir: exe + 종속 DLL을 폴더에 그대로 둔다)..."
# --onefile은 실행할 때마다 %TEMP%에 자기 자신을 압축해제하고 그 안에서
# python3xx.dll을 로드하는 방식이라, 그 추출 과정이 백신 실시간 검사에 걸리면
# "Failed to load Python DLL ... LoadLibrary: 지정된 모듈을 찾을 수 없습니다"
# 오류로 이어진다(특히 업데이트 직후 막 내려받은/이동된 exe에서 자주 발생).
# --onedir는 실행 시점에 압축해제가 없어서 이 문제 자체가 없다.
& $pyCmd -m PyInstaller --onedir --windowed --name "$AppName" --noconfirm `
    --icon "$ProjectDir\app\resources\app_icon.ico" `
    run_app.py
if ($LASTEXITCODE -ne 0) { Fail "빌드에 실패했습니다." }

$distAppDir = Join-Path $ProjectDir "dist\$AppName"

Write-Host "3) config.ini를 exe와 같은 폴더($distAppDir)에 배치..."
# dist 폴더는 빌드할 때마다 통째로 새로 만들어지므로 매번 다시 복사한다.
$configPath = Join-Path $ProjectDir "config.ini"
if (Test-Path $configPath) {
    Copy-Item -LiteralPath $configPath -Destination (Join-Path $distAppDir "config.ini") -Force
    Write-Host "config.ini를 $distAppDir 로 복사했습니다."
} else {
    Write-Host "경고: config.ini가 없습니다. config.ini.example을 복사해서 만들어주세요." -ForegroundColor Yellow
}

Write-Host "4) 배포/업데이트용 zip 생성..."
Write-Host "   GitHub Release 첨부파일 - app/updater.py가 이 zip을 내려받아 설치 폴더 전체를 갱신한다."
$zipPath = Join-Path $ProjectDir "dist\$AppName.zip"
if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
try {
    Compress-Archive -Path (Join-Path $distAppDir "*") -DestinationPath $zipPath -Force
} catch {
    Write-Host "경고: 배포용 zip 생성에 실패했습니다. GitHub 릴리즈에는 이 zip을 올려야 합니다." -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

Write-Host ""
Write-Host "완료: $distAppDir\$AppName.exe" -ForegroundColor Green
Write-Host "(폴더 전체를 그대로 옮겨야 동작합니다 - exe 파일 하나만 복사하면 실행되지 않습니다)"
Write-Host "배포/업데이트용 zip: $zipPath" -ForegroundColor Green
