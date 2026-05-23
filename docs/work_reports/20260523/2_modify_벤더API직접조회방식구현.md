# 벤더 API 직접 조회 방식 구현

- 작업일: 2026-05-23
- 작업 유형: modify
- 담당: Claude

## 목표

"DB 업데이트" 버튼 클릭 시에만 NVIDIA/AMD 공식 API를 직접 조회하여 manifest.json을 자동 갱신한다.
원격 manifest 서버를 별도 운영할 필요 없이 새 드라이버 버전을 자동 감지한다.

## 변경 파일

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `core/vendor_api.py` | 신규 생성 | NVIDIA/AMD 벤더 API 조회 모듈 |
| `core/downloader.py` | 수정 | `download_driver_db()` 로직 변경 |
| `config/settings.json` | 수정 | `keep_versions: 2`, `remote_manifest_url` 제거 |
| `drivers/manifest.json` | 수정 | lts 버전 제거, 모든 드라이버 2개 이하로 정리 |

## 구현 내용

### core/vendor_api.py (신규)

벤더별 드라이버 버전 조회 함수를 제공한다.

**NVIDIA** (`fetch_nvidia_versions`):
- NVIDIA GFE(GeForce Experience) 서비스 API 사용
- 엔드포인트: `gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php`
- 파라미터: pfid(제품군 ID), osID=135(Win10/11 x64), isWHQL=1, dch=1, numberOfResults=2
- 응답 형식: JSON `{ "IDS": [{ "downloadInfo": { "Version": "...", "DownloadURL": "...", ... } }] }`
- Desktop pfid=816, Notebook pfid=851

**AMD** (`fetch_amd_versions`):
- AMD release-notes JSON 엔드포인트 사용: `www.amd.com/apps/optamd/release-notes.json`
- API에 다운로드 URL이 없을 경우 알려진 URL 패턴으로 재구성
- 다양한 필드명 패턴 대응 (version/Version/driverVersion 등)

**공통 동작**:
- API 실패 시 None 반환 → 기존 manifest 항목 유지 (graceful degradation)
- API가 1건만 반환 시 기존 manifest의 previous 버전을 보존
- Intel, Realtek: 공개 API 없어 정적 유지

**`update_manifest_versions`**:
- manifest 전체를 순회하며 벤더 API 호출
- 각 드라이버 최대 2개 버전(latest, previous)만 유지
- 변경 사항 목록 반환 (`driver_id: old_ver → new_ver`)

### core/downloader.py (수정)

`download_driver_db()` 실행 단계:

1. 네트워크 연결 확인 (`check_connectivity()`) — 오프라인이면 즉시 실패 반환
2. vendor_api.py의 `update_manifest_versions()` 호출 → manifest 갱신 저장
3. 갱신된 manifest 기준으로 미다운로드 파일 수집
4. 파일 다운로드

다운로드 상태 dict에 새 필드 추가:
- `phase`: `"vendor_api"` | `"downloading"` | `"idle"`
- `phase_label`: UI에 표시할 단계 설명 문자열
- `changes`: 벤더 API로 갱신된 항목 목록

### config/settings.json (수정)

- `remote_manifest_url` 제거 (벤더 API 직접 조회로 대체)
- `keep_versions`: 3 → 2

### drivers/manifest.json (수정)

- NVIDIA Desktop lts(560.94) 버전 제거
- NVIDIA Notebook lts(560.94) 버전 제거
- AMD lts(24.5.1) 버전 제거
- 전체 10개 드라이버 모두 2개 이하 버전으로 정리

## 동작 흐름 (변경 후)

```
사용자가 "DB 업데이트" 클릭
  → 네트워크 연결 확인
  → 오프라인: 오류 메시지 표시 후 종료
  → 온라인:
      NVIDIA Desktop API 조회 → manifest 갱신
      NVIDIA Notebook API 조회 → manifest 갱신
      AMD Radeon API 조회 → manifest 갱신
      Intel/Realtek: 정적 유지 (2개 초과분만 제거)
  → 갱신된 manifest를 drivers/manifest.json에 저장
  → 미다운로드 드라이버 파일 다운로드
  → 완료 후 스캔 재실행
```

## 핵심 설계 원칙

- 오프라인 우선: 코어 기능(하드웨어 스캔, 버전 비교, 설치)은 네트워크 불필요
- 네트워크는 명시적 사용자 요청(DB 업데이트, 드라이버 다운로드) 시에만 사용
- 벤더 API 실패 시 graceful degradation — 기존 manifest 데이터 보존
- 버전 2개(latest, previous) 정책 — manifest 경량화 및 롤백 옵션 유지
