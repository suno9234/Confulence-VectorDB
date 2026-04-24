# VPN 설정 가이드

재택근무 또는 외부에서 사내 시스템(git.nexusai.internal, jira.nexusai.internal 등)에 접근하려면 VPN 연결이 필수입니다.

## VPN 정보

| 항목 | 값 |
|------|-----|
| 서버 주소 | vpn.nexusai.internal (외부: vpn.nexusai.co.kr) |
| 프로토콜 | WireGuard |
| 포트 | UDP 51820 |
| DNS (VPN 연결 시) | 192.168.1.5 |
| IP 할당 범위 | 10.0.0.100 – 10.0.0.254 (개인별 고정 할당) |

## 설치 방법 (macOS 기준)

### 1단계: WireGuard 클라이언트 설치
```
brew install wireguard-tools
```
또는 App Store에서 "WireGuard" 검색 후 설치

### 2단계: 설정 파일 발급
- IT지원팀 박준혁(jh.park2@nexusai.co.kr)에게 요청
- 본인 노트북 공개 키를 함께 전달 (아래 명령어로 생성)
```bash
wg genkey | tee privatekey | wg pubkey > publickey
cat publickey
```

### 3단계: 설정 파일 적용
- 발급받은 `.conf` 파일을 WireGuard 앱에 Import
- macOS: WireGuard 앱 → (+) → Import from File

### 4단계: 연결 확인
```bash
ping 192.168.1.5
curl http://git.nexusai.internal
```

## Windows 설정

1. wireguard.com에서 WireGuard for Windows 다운로드 설치
2. IT지원팀에서 발급받은 `.conf` 파일 Import
3. 터널 활성화 후 연결 상태 확인

## 주의사항

- VPN 연결 상태에서 개인 클라우드(구글 드라이브 등)에 회사 자료 업로드 금지
- 공용 Wi-Fi에서 VPN 없이 사내 시스템 접근 불가 (방화벽 차단)
- 해외 출장 시 VPN 연결 필수 (일부 국가에서 WireGuard 포트 차단 사례 있음 → IT팀 사전 문의)
- VPN 연결 로그는 인프라팀에서 모니터링 중 (보안 감사 목적)

## 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| 연결은 되나 내부 DNS 안 됨 | WireGuard DNS 설정이 192.168.1.5 인지 확인 |
| 연결 자체가 안 됨 | 방화벽/공유기에서 UDP 51820 차단 여부 확인 |
| IP 충돌 | IT팀에 문의 (고정 IP 재할당 필요) |
