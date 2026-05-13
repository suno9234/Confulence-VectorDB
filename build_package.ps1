# build_package.ps1
# 인터넷 되는 빌드 PC에서 실행 → 배포용 패키지 생성
#
# 사용법:
#   .\build_package.ps1                    # 버전 자동 증가, 이전 Python/모델 재사용
#   .\build_package.ps1 -Version "1.1.0"   # 버전 직접 지정
#   .\build_package.ps1 -SkipTauriBuild    # Tauri 빌드 생략 (Rust 코드 미변경 시)
#   .\build_package.ps1 -FreshPython       # Python/패키지 새로 설치 (requirements 변경 시)

param(
    [string]$Version = "",
    [switch]$SkipTauriBuild,
    [switch]$FreshPython
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

# 버전 자동 증가: dist 폴더에서 최신 버전 탐색 후 패치 +1
if (-not $Version) {
    $existing = Get-ChildItem "$Root\dist" -Directory -Filter "Confulence_v*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^Confulence_v(\d+)\.(\d+)\.(\d+)$' } |
        ForEach-Object {
            $null = $_.Name -match '^Confulence_v(\d+)\.(\d+)\.(\d+)$'
            [PSCustomObject]@{ Major=[int]$Matches[1]; Minor=[int]$Matches[2]; Patch=[int]$Matches[3] }
        } | Sort-Object Major, Minor, Patch | Select-Object -Last 1

    if ($existing) {
        $Version = "$($existing.Major).$($existing.Minor).$($existing.Patch + 1)"
        Write-Host "  이전 버전 감지: v$($existing.Major).$($existing.Minor).$($existing.Patch) → v$Version 으로 빌드" -ForegroundColor Yellow
    } else {
        $Version = "1.0.0"
    }
}

$Dist = "$Root\dist\Confulence_v$Version"
$Python  = "3.11.9"
$PythonUrl = "https://www.python.org/ftp/python/$Python/python-$Python-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

Write-Host "`n=== Confulence v$Version 패키지 빌드 ===" -ForegroundColor Cyan

# ── 0. dist 폴더 초기화 ───────────────────────────────────────────────────────
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
New-Item -ItemType Directory -Force $Dist | Out-Null
Write-Host "[1/5] dist 폴더 초기화: $Dist"

# ── 1. 포터블 Python 준비 ─────────────────────────────────────────────────────
Write-Host "[2/5] Python $Python 포터블 준비 중..."

$PrevPython = Get-ChildItem "$Root\dist" -Directory -Filter "Confulence_v*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "Confulence_v$Version" -and (Test-Path "$($_.FullName)\python\python.exe") } |
    Sort-Object LastWriteTime | Select-Object -Last 1

if ($PrevPython -and -not $FreshPython) {
    Write-Host "  이전 빌드에서 Python 복사 중: $($PrevPython.Name)\python ..."
    Copy-Item "$($PrevPython.FullName)\python" "$Dist\python" -Recurse -Force
    Write-Host "  Python 복사 완료 - 신규 패키지 확인 중..."
    & "$Dist\python\python.exe" -m pip install `
        -r "$Root\requirements.txt" `
        --no-warn-script-location `
        -q
    Write-Host "  패키지 업데이트 완료"
} else {
    if ($FreshPython) { Write-Host "  -FreshPython 지정됨 - 새로 설치합니다" }
    else              { Write-Host "  이전 빌드 없음 - 새로 설치합니다" }

    $PythonZip = "$env:TEMP\python-embed.zip"
    Invoke-WebRequest $PythonUrl -OutFile $PythonZip
    Expand-Archive $PythonZip -DestinationPath "$Dist\python" -Force
    Remove-Item $PythonZip

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

    Write-Host "  패키지 설치 중 (시간이 걸릴 수 있습니다)..."
    & "$Dist\python\python.exe" -m pip install `
        -r "$Root\requirements.txt" `
        --no-warn-script-location `
        -q
    Write-Host "  패키지 설치 완료"
}

# ── 2. 패키지 확인 완료 ──────────────────────────────────────────────────────
Write-Host "[3/5] Python 패키지 확인 완료"

# ── 3. 모델 복사 또는 다운로드 ───────────────────────────────────────────────
Write-Host "[4/5] 임베딩 모델 준비 중..."
New-Item -ItemType Directory -Force "$Dist\models" | Out-Null

$PrevModels = Get-ChildItem "$Root\dist" -Directory -Filter "Confulence_v*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "Confulence_v$Version" -and (Test-Path "$($_.FullName)\models") } |
    Sort-Object LastWriteTime | Select-Object -Last 1

if ($PrevModels) {
    Write-Host "  이전 빌드에서 모델 복사 중: $($PrevModels.Name)\models ..."
    Copy-Item "$($PrevModels.FullName)\models\*" "$Dist\models" -Recurse -Force
    Write-Host "  모델 복사 완료"
} else {
    Write-Host "  이전 빌드 없음 - HuggingFace에서 다운로드 중..."
    $DownloadScript = @"
import os
os.environ['HF_HOME'] = r'$Dist\models'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = r'$Dist\models'

print('  ko-sroberta-multitask 다운로드 중...')
from sentence_transformers import SentenceTransformer
SentenceTransformer('jhgan/ko-sroberta-multitask')
print('  완료')

print('  mmarco-mMiniLMv2 리랭커 다운로드 중...')
from sentence_transformers import CrossEncoder
CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')
print('  완료')
"@
    $DownloadScript | & "$Dist\python\python.exe" -
}

# ── 4. 앱 파일 복사 ───────────────────────────────────────────────────────────
Write-Host "[5/5] 앱 파일 복사 중..."

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

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Write-Host "폴더: $Dist"
Write-Host ""
Write-Host "배포 방법:"
Write-Host "  1. $Dist 폴더를 압축해서 대상 PC로 복사"
Write-Host "  2. 압축 해제"
Write-Host "  3. Confulence.exe 실행"
Write-Host "  4. 앱에서 압축 해제한 폴더를 '프로젝트 폴더'로 선택"
