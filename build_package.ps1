# build_package.ps1
# 인터넷 되는 빌드 PC에서 실행 → 배포용 패키지 생성
#
# 사용법:
#   .\build_package.ps1
#   .\build_package.ps1 -Version "1.1.0"
#   .\build_package.ps1 -SkipTauriBuild   # Tauri 빌드 생략 (이미 빌드된 경우)

param(
    [string]$Version = "1.0.0",
    [switch]$SkipTauriBuild
)

$ErrorActionPreference = "Stop"
$Root    = $PSScriptRoot
$Dist    = "$Root\dist\Confulence_v$Version"
$Python  = "3.11.9"
$PythonUrl = "https://www.python.org/ftp/python/$Python/python-$Python-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

Write-Host "`n=== Confulence v$Version 패키지 빌드 ===" -ForegroundColor Cyan

# ── 0. dist 폴더 초기화 ───────────────────────────────────────────────────────
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
New-Item -ItemType Directory -Force $Dist | Out-Null
Write-Host "[1/6] dist 폴더 초기화: $Dist"

# ── 1. 포터블 Python 설치 ─────────────────────────────────────────────────────
Write-Host "[2/6] Python $Python 포터블 다운로드 중..."
$PythonZip = "$env:TEMP\python-embed.zip"
Invoke-WebRequest $PythonUrl -OutFile $PythonZip
Expand-Archive $PythonZip -DestinationPath "$Dist\python" -Force
Remove-Item $PythonZip

# embeddable Python에서 pip 및 site-packages 활성화
$pth = Get-ChildItem "$Dist\python" | Where-Object { $_.Name -like '*._pth' } | Select-Object -First 1 -ExpandProperty FullName
if (-not $pth) { $pth = "$Dist\python\python311._pth" }
Write-Host "  ._pth 파일: $pth"
$pthContent = (Get-Content $pth -Raw) -replace '#import site', 'import site'
[System.IO.File]::WriteAllText($pth, $pthContent, [System.Text.UTF8Encoding]::new($false))

Write-Host "  pip 설치 중..."
$GetPip = "$env:TEMP\get-pip.py"
Invoke-WebRequest $GetPipUrl -OutFile $GetPip
& "$Dist\python\python.exe" $GetPip --no-warn-script-location
Remove-Item $GetPip

# ── 2. 패키지 설치 ────────────────────────────────────────────────────────────
Write-Host "[3/6] Python 패키지 설치 중 (시간이 걸릴 수 있습니다)..."
& "$Dist\python\python.exe" -m pip install `
    -r "$Root\requirements.txt" `
    --no-warn-script-location `
    -q
Write-Host "  패키지 설치 완료"

# ── 3. 모델 다운로드 ──────────────────────────────────────────────────────────
Write-Host "[4/6] 임베딩 모델 다운로드 중..."
New-Item -ItemType Directory -Force "$Dist\models" | Out-Null

$DownloadScript = @"
import os
os.environ['HF_HOME'] = r'$Dist\models'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = r'$Dist\models'

print('  ko-sroberta-multitask 다운로드 중...')
from sentence_transformers import SentenceTransformer
SentenceTransformer('jhgan/ko-sroberta-multitask')
print('  완료')
"@
$DownloadScript | & "$Dist\python\python.exe" -

# ── 4. 앱 파일 복사 ───────────────────────────────────────────────────────────
Write-Host "[5/6] 앱 파일 복사 중..."

# Tauri 앱 빌드 및 복사
if (-not $SkipTauriBuild) {
    Write-Host "  Tauri 앱 빌드 중..."
    Push-Location "$Root\app"
    npm run tauri build
    Pop-Location
}

$ExePath = "$Root\app\src-tauri\target\release\Confulence.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Confulence.exe 를 찾을 수 없습니다. 먼저 'npm run tauri build' 를 실행하세요."
}
Copy-Item $ExePath "$Dist\Confulence.exe"

# Python 스크립트 및 콘텐츠 복사
Copy-Item "$Root\backend"  "$Dist\backend"  -Recurse
Copy-Item "$Root\content"  "$Dist\content"  -Recurse
Copy-Item "$Root\.env.example" "$Dist\.env"

# vector_db, AppData 폴더 미리 생성 (앱이 여기에 데이터 저장)
New-Item -ItemType Directory -Force "$Dist\vector_db" | Out-Null

# ── 5. 압축 ──────────────────────────────────────────────────────────────────
Write-Host "[6/6] ZIP 압축 중..."
$ZipPath = "$Root\dist\Confulence_v$Version.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$Dist\*" -DestinationPath $ZipPath
$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 0)

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Write-Host "폴더: $Dist"
Write-Host "ZIP : $ZipPath ($SizeMB MB)"
Write-Host ""
Write-Host "배포 방법:"
Write-Host "  1. ZIP을 대상 PC로 복사"
Write-Host "  2. 압축 해제"
Write-Host "  3. Confulence.exe 실행"
Write-Host "  4. 앱에서 압축 해제한 폴더를 '프로젝트 폴더'로 선택"
